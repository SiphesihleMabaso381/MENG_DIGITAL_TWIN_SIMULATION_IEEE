"""
Project launcher for the Hybrid Grid Digital Twin Simulation.

Default behavior:
- Runs the full IEEE13 feeder simulation

Optional behavior:
- Run lightweight demo flow with --demo
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

from example_simulation import main as run_demo
from example_simulation import example_ieee13_simulation
from example_simulation import example_ieee34_simulation
from example_simulation import example_ieee123_simulation
from example_simulation import example_with_realistic_profiles


def _run_deployment_readiness_assessment(results_df, digital_twin, output_dir: Path) -> None:
    """Assess the generated simulation outputs with the future-ready modules."""
    from src.data_quality import DataQualityManager
    from src.deployment_readiness import DeploymentReadinessEvaluator
    from src.explainability import ExplainabilityEngine
    from src.federated_learning import (
        FederatedAveragingAggregator,
        FederatedClient,
        FederatedLearningConfig,
    )
    from src.physics_informed import FeederPhysicsValidator

    if results_df is None or results_df.empty:
        print("Deployment readiness assessment skipped: no simulation rows available.")
        return

    assessment_data = results_df.copy()
    assessment_data["is_anomaly"] = (
        assessment_data.get("ntl_loss_kw", 0).fillna(0).gt(0)
        | assessment_data.get("tamper_flag", False).fillna(False).astype(bool)
        | assessment_data.get("missing_reading", False).fillna(False).astype(bool)
    ).astype(int)

    numeric_quality_columns = [
        column
        for column in ["energy_kwh", "actual_p_kw", "measured_p_kw", "ntl_loss_kw"]
        if column in assessment_data.columns
    ]
    quality_data = (
        assessment_data.groupby("timestamp", as_index=False)[numeric_quality_columns].sum()
        if "timestamp" in assessment_data.columns and numeric_quality_columns
        else assessment_data
    )
    quality = DataQualityManager().clean_and_validate(
        quality_data,
        required_columns=["timestamp", *numeric_quality_columns],
        timestamp_field="timestamp",
    )

    source_power = float(assessment_data.get("source_p_kw", 0).mean())
    actual_power = float(assessment_data.get("actual_total_kw", 0).mean())
    physics = FeederPhysicsValidator().evaluate(
        injected_power_by_node={"source": source_power, "feeder_load": -actual_power},
        voltage_by_node={"feeder_nominal": 230.0},
    )

    explainability_features = [
        column
        for column in ["actual_p_kw", "measured_p_kw", "energy_kwh", "ntl_loss_kw"]
        if column in assessment_data.columns
    ]
    explainability = ExplainabilityEngine().explain_feature_importance(
        assessment_data[[*explainability_features, "is_anomaly"]],
        target_column="is_anomaly",
        top_k=4,
    )

    client_frames = [
        assessment_data.iloc[indexes].copy()
        for indexes in np.array_split(np.arange(len(assessment_data)), 4)
        if len(indexes) > 0
    ]
    clients = [FederatedClient(f"feeder_client_{idx}", frame) for idx, frame in enumerate(client_frames, start=1)]
    client_states = [
        client.train_local_model(explainability_features, "is_anomaly")
        for client in clients
    ]
    federated = FederatedAveragingAggregator(
        FederatedLearningConfig(rounds=3, client_count=len(clients))
    ).aggregate(client_states)

    stats = digital_twin.get_summary_statistics()
    targets = digital_twin._get_realism_targets_for_profile()
    benchmark_metrics = {
        "technical_loss_pct_of_source": stats.get("technical_loss_pct_of_source", 0.0),
        "ntl_percentage": stats.get("ntl_percentage", 0.0),
        "communication_loss_rate_percent": stats.get("communication_loss_rate_percent", 0.0),
    }
    benchmark_scores = []
    for metric_name, value in benchmark_metrics.items():
        low, high = targets[metric_name]
        if low <= value <= high:
            benchmark_scores.append(100.0)
        else:
            distance = (low - value) if value < low else (value - high)
            benchmark_scores.append(max(0.0, 100.0 - distance * 10.0))
    benchmark_scores.append(float(stats.get("convergence_rate_percent", 0.0)))
    benchmark_score = float(np.mean(benchmark_scores))

    report = DeploymentReadinessEvaluator().evaluate(
        data_quality=quality,
        physics=physics,
        explainability=explainability,
        federated=federated,
        benchmark_score=benchmark_score,
    )
    report_path = output_dir / "deployment_readiness_report.json"
    report_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    print("\n[Step 11] Deployment Readiness Assessment:")
    print(f"  Readiness score: {report.readiness_score:.2f}/100")
    print(f"  Summary: {report.summary}")
    for check in report.checks:
        print(f"  - {check.name}: {check.score:.2f} ({check.status})")
    print(f"  Report exported to: {report_path}")


def _relocate_main_outputs(base_dir: Path, feeder: str = "IEEE13") -> None:
    """Move outputs generated through main.py into an isolated folder."""
    main_output_dir = base_dir / "results" / "main_ieee"
    main_output_dir.mkdir(parents=True, exist_ok=True)

    demo_profile = base_dir / "results" / "load_profiles.csv"
    if demo_profile.exists():
        demo_dst = main_output_dir / "load_profiles.csv"
        if demo_dst.exists():
            demo_dst.unlink()
        shutil.move(str(demo_profile), str(demo_dst))

    feeder_src = base_dir / "results" / f"{feeder.lower()}_example"
    if feeder_src.exists():
        for src_file in feeder_src.iterdir():
            if src_file.is_file():
                dst_file = main_output_dir / src_file.name
                if dst_file.exists():
                    dst_file.unlink()
                shutil.move(str(src_file), str(dst_file))

        try:
            feeder_src.rmdir()
        except OSError:
            pass


def _show_dashboard(base_dir: Path) -> None:
    """Render dashboard after outputs are generated by main.py."""
    results_dir = base_dir / "results" / "main_ieee"
    dashboard_image = results_dir / "dashboard.png"
    sim_results = results_dir / "simulation_results.csv"
    if not sim_results.exists():
        print(
            "Dashboard skipped: full simulation outputs not found in "
            f"{results_dir}"
        )
        return

    try:
        from src.dashboard import render_dashboard
    except Exception as exc:
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        external_python = (
            Path(local_app_data)
            / "venvs"
            / "MENG_DIGITAL_TWIN_SIMULATION_IEEE"
            / "Scripts"
            / "python.exe"
        )

        if external_python.exists() and external_python.resolve() != Path(sys.executable).resolve():
            print(
                "Current interpreter cannot render dashboard. "
                "Trying external interpreter..."
            )
            cmd = [
                str(external_python),
                str(base_dir / "src" / "dashboard.py"),
                "--results-dir",
                str(results_dir),
                "--save",
                str(dashboard_image),
            ]
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(base_dir),
                check=False,
            )
            if completed.returncode == 0 and dashboard_image.exists():
                print(f"Dashboard generated at: {dashboard_image}")
                return

            print(
                "Dashboard skipped: plotting dependencies are unavailable "
                f"({exc}). External render failed with code "
                f"{completed.returncode}."
            )
            if completed.stderr:
                print(completed.stderr.strip())
            return

        print(
            "Dashboard skipped: plotting dependencies are unavailable "
            f"({exc})."
        )
        return

    render_dashboard(
        results_dir=str(results_dir),
        save_path=str(dashboard_image),
        show=True,
    )
    print(f"Dashboard generated and opened at: {dashboard_image}")


def _ensure_main_load_profile_output(base_dir: Path) -> None:
    """Ensure load_profiles.csv is available in results/main_ieee for main.py runs."""
    src_profile = base_dir / "results" / "load_profiles.csv"
    dst_dir = base_dir / "results" / "main_ieee"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst_profile = dst_dir / "load_profiles.csv"

    if src_profile.exists():
        shutil.copy2(str(src_profile), str(dst_profile))
        print(f"Load profiles exported to: {dst_profile}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Hybrid Grid Digital Twin Simulation project"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run the lightweight demo instead of the default full IEEE13 simulation",
    )
    parser.add_argument(
        "--full-ieee13",
        action="store_true",
        help="Backward-compatible flag; full IEEE13 is now the default mode",
    )
    parser.add_argument(
        "--feeder",
        choices=["IEEE13", "IEEE34", "IEEE123"],
        default="IEEE13",
        help="Feeder to run for full simulation mode (default: IEEE13)",
    )
    parser.add_argument(
        "--realism-profile",
        choices=["benchmark", "utility", "stressed"],
        default="utility",
        help="Meter/data realism profile for full simulation mode",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic random seed used when --random-seed is not set",
    )
    parser.add_argument(
        "--random-seed",
        action="store_true",
        help="Use a fresh random seed each run (non-deterministic)",
    )
    parser.add_argument(
        "--strict-realism",
        dest="strict_realism",
        action="store_true",
        default=True,
        help="Enable automatic calibration retries to fit real-world target bands",
    )
    parser.add_argument(
        "--no-strict-realism",
        dest="strict_realism",
        action="store_false",
        help="Disable automatic calibration retries",
    )
    parser.add_argument(
        "--max-calibration-attempts",
        type=int,
        default=12,
        help="Maximum calibration attempts when strict realism is enabled",
    )
    parser.add_argument(
        "--region",
        choices=["south_africa", "global"],
        default="south_africa",
        help="Choose the regional load-profile behavior model",
    )
    return parser.parse_args()


def run() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parent
    feeder = args.feeder

    feeder_runners = {
        "IEEE13": example_ieee13_simulation,
        "IEEE34": example_ieee34_simulation,
        "IEEE123": example_ieee123_simulation,
    }

    if args.demo:
        run_demo()
        _relocate_main_outputs(project_root, feeder=feeder)
        print(
            "Dashboard not generated in --demo mode. "
            f"Run without --demo to generate full {feeder} outputs and dashboard."
        )
    else:
        example_with_realistic_profiles()
        _ensure_main_load_profile_output(project_root)
        simulation_result = feeder_runners[feeder](
            realism_profile=args.realism_profile,
            seed=args.seed,
            randomize_seed=args.random_seed,
            strict_realism=args.strict_realism,
            max_calibration_attempts=args.max_calibration_attempts,
            region=args.region,
        )
        _relocate_main_outputs(project_root, feeder=feeder)
        _ensure_main_load_profile_output(project_root)
        if simulation_result:
            results_df, digital_twin = simulation_result
            _run_deployment_readiness_assessment(
                results_df,
                digital_twin,
                project_root / "results" / "main_ieee",
            )
        _show_dashboard(project_root)

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
