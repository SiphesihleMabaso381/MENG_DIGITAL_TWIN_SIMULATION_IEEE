"""
Example Simulation Script
=========================
Demonstrates how to set up and run a complete hybrid grid digital twin simulation
with OpenDSS, load profiles, hybrid metering, and NTL injection.

Run this script to generate a realistic simulation dataset for NTL detection research.
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple

# Import simulation modules
from src.opendsss_interface import OpenDSSInterface
from src.hybrid_metering import HybridMeteringSystem
from src.load_profiles import HybridGridLoadManager, CustomerType
from src.ntl_injection import NTLInjectionEngine, NTLType
from src.simulation_engine import HybridGridDigitalTwin, SimulationConfig


FEEDER_ENTRY_FILES = {
    "IEEE13": (
        "ieee_feeders/electricdss-code-r4166-trunk-Distrib-IEEETestCases-13Bus/"
        "electricdss-code-r4166-trunk-Distrib-IEEETestCases-13Bus/IEEE13Nodeckt.dss"
    ),
    "IEEE34": (
        "ieee_feeders/electricdss-code-r4166-trunk-Distrib-IEEETestCases-34Bus/"
        "electricdss-code-r4166-trunk-Distrib-IEEETestCases-34Bus/Run_IEEE34Mod1.dss"
    ),
    "IEEE123": (
        "ieee_feeders/electricdss-code-r4166-trunk-Distrib-IEEETestCases-123Bus/"
        "electricdss-code-r4166-trunk-Distrib-IEEETestCases-123Bus/Run_IEEE123Bus.DSS"
    ),
}


REALISM_METER_PROFILES = {
    "benchmark": {
        "smart_accuracy_class": 0.5,
        "legacy_accuracy_class": 2.0,
        "smart_communication_reliability": 0.95,
        "smart_communication_reliability_std": 0.01,
        "legacy_communication_reliability": 1.0,
        "smart_burst_probability": 0.0,
        "smart_burst_steps_min": 1,
        "smart_burst_steps_max": 1,
    },
    "utility": {
        "smart_accuracy_class": 0.5,
        "legacy_accuracy_class": 1.5,
        "smart_communication_reliability": 0.992,
        "smart_communication_reliability_std": 0.004,
        "smart_communication_recovery_rate": 0.85,
        "legacy_communication_reliability": 1.0,
        "legacy_communication_recovery_rate": 0.95,
        "smart_burst_probability": 0.001,
        "smart_burst_steps_min": 2,
        "smart_burst_steps_max": 4,
    },
    "stressed": {
        "smart_accuracy_class": 1.0,
        "legacy_accuracy_class": 2.5,
        "smart_communication_reliability": 0.93,
        "smart_communication_reliability_std": 0.02,
        "legacy_communication_reliability": 0.995,
        "smart_burst_probability": 0.02,
        "smart_burst_steps_min": 4,
        "smart_burst_steps_max": 16,
    },
}


REALISM_TARGETS = {
    "benchmark": {
        "non_ntl_gap_pct": (0.5, 3.0),
        "ntl_pct": (0.5, 4.0),
        "technical_pct": (3.0, 10.0),
        "comm_loss_rate_pct": (0.0, 4.0),
    },
    "utility": {
        "non_ntl_gap_pct": (0.0, 1.5),
        "ntl_pct": (0.5, 6.0),
        "technical_pct": (3.0, 10.0),
        "comm_loss_rate_pct": (0.0, 2.0),
    },
    "stressed": {
        "non_ntl_gap_pct": (1.0, 6.0),
        "ntl_pct": (4.0, 12.0),
        "technical_pct": (4.0, 14.0),
        "comm_loss_rate_pct": (1.0, 8.0),
    },
}


def _resolve_seed(seed: int, randomize_seed: bool) -> int:
    if randomize_seed:
        # Use a large random integer so repeated runs are not deterministic.
        return int(np.random.default_rng().integers(0, 2_147_483_647))
    return int(seed)


def _get_realism_targets(realism_profile: str) -> Dict[str, Tuple[float, float]]:
    return REALISM_TARGETS.get(realism_profile, REALISM_TARGETS["utility"])


def _evaluate_realism_fit(stats: Dict, realism_profile: str) -> Tuple[bool, Dict[str, float], float]:
    targets = _get_realism_targets(realism_profile)

    supplied = float(stats.get("total_energy_supplied_kwh", 0.0))
    non_ntl_gap_pct = (
        float(stats.get("metering_data_gap_kwh", 0.0)) / supplied * 100.0
        if supplied > 0
        else 0.0
    )
    ntl_pct = float(stats.get("ntl_percentage", 0.0))
    technical_pct = float(stats.get("technical_loss_pct_of_source", 0.0))
    comm_loss_rate_pct = float(stats.get("communication_loss_rate_percent", 0.0))

    actual = {
        "non_ntl_gap_pct": non_ntl_gap_pct,
        "ntl_pct": ntl_pct,
        "technical_pct": technical_pct,
        "comm_loss_rate_pct": comm_loss_rate_pct,
    }

    in_range = True
    distance = 0.0
    for key, value in actual.items():
        low, high = targets[key]
        if value < low:
            in_range = False
            distance += (low - value) / max(high - low, 1e-9)
        elif value > high:
            in_range = False
            distance += (value - high) / max(high - low, 1e-9)

    return in_range, actual, distance


def _resolve_project_path(path_str: str) -> str:
    """Resolve a project-relative path from this file location."""
    return str((Path(__file__).resolve().parent / path_str).resolve())


def _build_feeder_load_definitions(load_names: List[str]) -> List[Tuple[str, CustomerType, float]]:
    """Create (node, customer_type, annual_kwh) tuples for all feeder loads."""
    customer_cycle = [
        CustomerType.RESIDENTIAL,
        CustomerType.COMMERCIAL,
        CustomerType.INDUSTRIAL,
        CustomerType.AGRICULTURAL,
        CustomerType.PUBLIC_MUNICIPAL,
        CustomerType.INSTITUTIONAL,
        CustomerType.BULK,
    ]
    annual_kwh_by_type = {
        CustomerType.RESIDENTIAL: 4000,
        CustomerType.COMMERCIAL: 50000,
        CustomerType.INDUSTRIAL: 200000,
        CustomerType.AGRICULTURAL: 70000,
        CustomerType.PUBLIC_MUNICIPAL: 60000,
        CustomerType.INSTITUTIONAL: 90000,
        CustomerType.BULK: 450000,
    }

    definitions: List[Tuple[str, CustomerType, float]] = []
    for idx, load_name in enumerate(sorted([n for n in load_names if n], key=str.lower)):
        customer_type = customer_cycle[idx % len(customer_cycle)]
        definitions.append((load_name, customer_type, annual_kwh_by_type[customer_type]))

    return definitions


def _schedule_realistic_ntl_events(
    ntl_engine: NTLInjectionEngine,
    feeder_name: str,
    load_names: List[str],
    simulation_days: int,
    realism_profile: str,
) -> int:
    """Generate NTL scenarios using prevalence sampling across the full customer set."""
    sorted_nodes = sorted([n for n in load_names if n], key=str.lower)
    total_nodes = len(sorted_nodes)
    if total_nodes == 0:
        return 0

    # Draw feeder-wide theft prevalence; resulting affected nodes can be any count from 0..N.
    prevalence_dist = {
        "benchmark": (1.2, 16.0),
        "utility": (1.8, 14.0),
        "stressed": (2.5, 7.5),
    }
    alpha, beta = prevalence_dist.get(realism_profile, (1.8, 14.0))
    sampled_prevalence = float(np.random.beta(alpha, beta))
    theft_nodes = [n for n in sorted_nodes if np.random.random() < sampled_prevalence]

    # Rare clean intervals and severe waves both remain possible.
    num_theft_nodes = len(theft_nodes)

    generated_events = ntl_engine.generate_realistic_theft_scenarios(
        num_theft_nodes=num_theft_nodes,
        theft_nodes=theft_nodes,
        sim_duration_days=simulation_days,
        realism_profile=realism_profile,
    )
    print(
        "  NTL scenario generation: "
        f"{len(generated_events)} events across {num_theft_nodes}/{total_nodes} nodes "
        f"(sampled prevalence {sampled_prevalence*100:.1f}%)"
    )
    return len(generated_events)


def _run_feeder_simulation(
    feeder_name: str,
    feeder_path: str,
    realism_profile: str = "benchmark",
    seed: int = 42,
    randomize_seed: bool = False,
    strict_realism: bool = True,
    max_calibration_attempts: int = 4,
):
    """
    Generic feeder simulation with hybrid metering and NTL scenarios.
    """
    
    print("\n" + "="*70)
    print(f"EXAMPLE 1: {feeder_name} Feeder Digital Twin Simulation")
    print("="*70)
    
    # Step 1: Configure simulation
    config = SimulationConfig()
    config.feeder_name = feeder_name
    config.simulation_days = 7  # 1 week simulation
    config.time_step_minutes = 15
    config.smart_meter_penetration = 0.6  # 60% smart meters
    config.num_ntl_nodes = 0  # Will be sampled dynamically by realism profile.
    config.seed = _resolve_seed(seed, randomize_seed)
    config.realism_profile = realism_profile

    meter_profile = REALISM_METER_PROFILES.get(realism_profile, REALISM_METER_PROFILES["benchmark"])
    
    print("\n[Step 1] Configuration:")
    print(f"  Feeder: {config.feeder_name}")
    print(f"  Duration: {config.simulation_days} days")
    print(f"  Time step: {config.time_step_minutes} minutes")
    print(f"  Smart meter penetration: {config.smart_meter_penetration*100:.0f}%")
    print(f"  Realism profile: {config.realism_profile}")
    print(f"  Random seed: {config.seed}")
    
    attempts = max(1, int(max_calibration_attempts)) if strict_realism else 1
    best_result = None
    best_score = float("inf")
    targets_met = False

    # Step 2+: Build and run one or more candidate worlds, then keep the best realism fit.
    for attempt in range(1, attempts + 1):
        attempt_seed = config.seed if attempt == 1 else int(config.seed + attempt * 7919)
        config.seed = attempt_seed

        print("\n[Step 2] Initializing feeder model...")
        opendss = OpenDSSInterface(feeder_path, config.feeder_name)

        print("\n[Step 3] Creating digital twin...")
        digital_twin = HybridGridDigitalTwin(config)
        digital_twin.setup_feeder(opendss)

        load_manager = HybridGridLoadManager()
        feeder_loads = _build_feeder_load_definitions(opendss.loads)
        print(f"  Detected feeder loads: {len(feeder_loads)}")
        load_manager.add_load_nodes_bulk(feeder_loads)

        metering_system = HybridMeteringSystem([node[0] for node in feeder_loads])
        metering_system.deploy_meters_by_penetration(
            config.smart_meter_penetration,
            meter_profile=meter_profile,
        )

        ntl_engine = NTLInjectionEngine(load_manager)

        print("\n[Step 4] Attaching metering and NTL components...")
        digital_twin.setup_load_profiles(load_manager)
        digital_twin.setup_metering_system(metering_system)
        digital_twin.setup_ntl_engine(ntl_engine)

        print("\n[Step 5] Scheduling NTL events...")
        _schedule_realistic_ntl_events(
            ntl_engine,
            feeder_name,
            [node for node, _, _ in feeder_loads],
            simulation_days=config.simulation_days,
            realism_profile=config.realism_profile,
        )

        print("\n[Step 6] Running simulation...")

        def progress_callback(current, total):
            if current % 96 == 0:  # Log every 24 hours
                pct = (current / total) * 100
                print(f"  Progress: {pct:.1f}% ({current}/{total} timesteps)")

        try:
            results_df = digital_twin.run_simulation(progress_callback=progress_callback)
            print(f"\n  Simulation completed: {len(results_df)} measurements recorded")
        except Exception as e:
            print(f"\n  ERROR: Simulation failed - {str(e)}")
            print("  NOTE: This may be due to missing IEEE feeder .dss file.")
            print("  Download from: https://sourceforge.net/p/electricdss/code/HEAD/tree/trunk/Distrib/IEEETestCases/")
            return

        stats = digital_twin.get_summary_statistics()
        in_range, actual, score = _evaluate_realism_fit(stats, config.realism_profile)
        print(
            "  Calibration check "
            f"(attempt {attempt}/{attempts}, seed={attempt_seed}): "
            f"non-NTL={actual['non_ntl_gap_pct']:.2f}%, "
            f"NTL={actual['ntl_pct']:.2f}%, "
            f"tech={actual['technical_pct']:.2f}%, "
            f"comm={actual['comm_loss_rate_pct']:.2f}%"
        )

        if score < best_score:
            best_score = score
            best_result = (results_df, digital_twin)

        if in_range:
            print("  Calibration status: targets met, using this run.")
            best_result = (results_df, digital_twin)
            targets_met = True
            break

        if attempt < attempts:
            print("  Calibration status: outside target bands, retrying...")

    if best_result is None:
        raise RuntimeError("No simulation result generated during realism calibration")

    if strict_realism and not targets_met:
        raise RuntimeError(
            "Strict realism targets were not achieved within "
            f"{attempts} attempts. Increase --max-calibration-attempts or adjust realism bands."
        )

    results_df, digital_twin = best_result
    
    # Step 7: Print summary
    print("\n[Step 7] Simulation Results:")
    digital_twin.print_summary()
    
    # Step 8: Export results
    print("\n[Step 8] Exporting results...")
    project_root = Path(__file__).resolve().parent
    output_dir = str(project_root / "results" / f"{feeder_name.lower()}_example")
    digital_twin.export_results(output_dir)
    print(f"  Results exported to: {output_dir}")
    
    # Step 9: Display sample data
    print("\n[Step 9] Sample Measurements (first 20 rows):")
    print(results_df.head(20).to_string())
    
    # Step 10: Analyze NTL statistics
    print("\n[Step 10] NTL Statistics by Node:")
    ntl_stats = digital_twin._compute_ntl_statistics()
    print(ntl_stats.to_string())
    
    return results_df, digital_twin


def example_ieee13_simulation(
    realism_profile: str = "benchmark",
    seed: int = 42,
    randomize_seed: bool = False,
    strict_realism: bool = True,
    max_calibration_attempts: int = 4,
):
    """Example: IEEE 13-bus feeder with hybrid metering and NTL scenarios."""
    return _run_feeder_simulation(
        "IEEE13",
        _resolve_project_path(FEEDER_ENTRY_FILES["IEEE13"]),
        realism_profile=realism_profile,
        seed=seed,
        randomize_seed=randomize_seed,
        strict_realism=strict_realism,
        max_calibration_attempts=max_calibration_attempts,
    )


def example_ieee34_simulation(
    realism_profile: str = "benchmark",
    seed: int = 42,
    randomize_seed: bool = False,
    strict_realism: bool = True,
    max_calibration_attempts: int = 4,
):
    """Example: IEEE 34-bus feeder with hybrid metering and NTL scenarios."""
    return _run_feeder_simulation(
        "IEEE34",
        _resolve_project_path(FEEDER_ENTRY_FILES["IEEE34"]),
        realism_profile=realism_profile,
        seed=seed,
        randomize_seed=randomize_seed,
        strict_realism=strict_realism,
        max_calibration_attempts=max_calibration_attempts,
    )


def example_ieee123_simulation(
    realism_profile: str = "benchmark",
    seed: int = 42,
    randomize_seed: bool = False,
    strict_realism: bool = True,
    max_calibration_attempts: int = 4,
):
    """Example: IEEE 123-bus feeder with hybrid metering and NTL scenarios."""
    return _run_feeder_simulation(
        "IEEE123",
        _resolve_project_path(FEEDER_ENTRY_FILES["IEEE123"]),
        realism_profile=realism_profile,
        seed=seed,
        randomize_seed=randomize_seed,
        strict_realism=strict_realism,
        max_calibration_attempts=max_calibration_attempts,
    )


def example_with_realistic_profiles():
    """
    Example: Load profiles with real-world characteristics.
    """
    
    print("\n" + "="*70)
    print("EXAMPLE 2: Load Profile Generation with Real-World Patterns")
    print("="*70)
    
    from src.load_profiles import LoadProfileGenerator
    
    print("\n[Step 1] Generating load profiles for different customer types...")
    
    profile_specs = [
        (CustomerType.RESIDENTIAL, 4000),
        (CustomerType.COMMERCIAL, 50000),
        (CustomerType.INDUSTRIAL, 200000),
        (CustomerType.AGRICULTURAL, 70000),
        (CustomerType.PUBLIC_MUNICIPAL, 60000),
        (CustomerType.INSTITUTIONAL, 90000),
        (CustomerType.BULK, 450000),
    ]

    profile_results = {}
    for customer_type, annual_kwh in profile_specs:
        generator = LoadProfileGenerator(customer_type, annual_consumption_kwh=annual_kwh)
        day1 = generator.get_hourly_profile(day_of_year=1)
        day180 = generator.get_hourly_profile(day_of_year=180)
        profile_results[customer_type.value] = {
            'day1': day1,
            'day180': day180,
        }

    print("\n[Step 2] Profile Summary:")
    for customer_type, _ in profile_specs:
        values = profile_results[customer_type.value]
        print(
            f"  {customer_type.value:<16} - Day 1 avg load: {values['day1'].mean():.2f}pu, "
            f"Day 180 avg: {values['day180'].mean():.2f}pu"
        )
    
    # Export profiles to CSV
    hours = np.arange(24)
    profiles_data = {'Hour': hours}
    for customer_type, _ in profile_specs:
        values = profile_results[customer_type.value]
        column_prefix = customer_type.value.replace("_", " ").title().replace(" ", "_")
        profiles_data[f'{column_prefix}_Winter'] = values['day1']
        profiles_data[f'{column_prefix}_Summer'] = values['day180']

    profiles_df = pd.DataFrame(profiles_data)
    
    Path("results").mkdir(exist_ok=True)
    profiles_df.to_csv("results/load_profiles.csv", index=False)
    print(f"\n  Exported load profiles to: results/load_profiles.csv")
    
    return profiles_df


def example_ntl_scenarios():
    """
    Example: Demonstrate various NTL scenario types.
    """
    
    print("\n" + "="*70)
    print("EXAMPLE 3: NTL Scenario Types and Detection Features")
    print("="*70)
    
    from src.load_profiles import HybridGridLoadManager, CustomerType
    from src.ntl_injection import NTLInjectionEngine, NTLType
    
    # Create load manager with dummy loads
    load_manager = HybridGridLoadManager()
    load_manager.add_load_nodes_bulk([
        ('node1', CustomerType.RESIDENTIAL, 4000),
        ('node2', CustomerType.COMMERCIAL, 50000),
    ])
    
    # Create NTL engine
    ntl_engine = NTLInjectionEngine(load_manager)
    
    # Schedule various NTL scenarios
    scenarios = [
        (NTLType.FULL_METER_BYPASS, 'node1', 1, 0, 24, 1.0),
        (NTLType.PARTIAL_METER_BYPASS, 'node2', 1, 8, 12, 0.4),
        (NTLType.METER_TAMPERING, 'node1', 1, 20, 4, 0.3),
        (NTLType.ILLEGAL_CONNECTION, 'node2', 1, 0, 24, 0.5),
        (NTLType.LOAD_MANIPULATION, 'node1', 1, 12, 6, 0.2),
        (NTLType.METER_FREEZING, 'node2', 1, 16, 8, 0.3),
    ]
    
    for ntl_type, node, day, hour, duration, intensity in scenarios:
        ntl_engine.schedule_ntl_event(node, ntl_type, day, hour, duration, intensity)
    
    print("\n[Step 1] Scheduled NTL Scenarios:")
    events_df = ntl_engine.export_event_schedule()
    print(events_df.to_string())
    
    # Simulate a 24-hour period with NTL
    print("\n[Step 2] Simulated Power Flows at Different Times:")
    
    times_to_check = [(1, 0), (1, 8), (1, 12), (1, 20)]
    
    for day, hour in times_to_check:
        all_data = ntl_engine.get_all_nodes_with_ntl(day, hour)
        summary = ntl_engine.get_ntl_summary(day, hour)
        
        print(f"\n  Time: Day {day}, Hour {hour}")
        print(f"    Total actual load:   {summary['total_actual_kw']:.1f} kW")
        print(f"    Total metered load:  {summary['total_metered_kw']:.1f} kW")
        print(f"    NTL loss:            {summary['total_ntl_loss_kw']:.1f} kW")
        print(f"    NTL percentage:      {summary['ntl_percentage']:.2f}%")
        print(f"    Affected nodes:      {summary['affected_nodes']}")
        
        for node, data in all_data.items():
            if data['ntl_type'] is not None:
                print(f"      - {node}: {data['ntl_type'].value}, "
                      f"loss={data['ntl_loss'][0]:.1f}kW")
    
    return events_df, ntl_engine


def main():
    """Run all examples."""
    
    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + "  HYBRID GRID DIGITAL TWIN SIMULATION - COMPREHENSIVE EXAMPLES".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)
    
    # Example 1: Load profiles
    try:
        example_with_realistic_profiles()
    except Exception as e:
        print(f"\nExample 2 error: {str(e)}")
    
    # Example 2: NTL scenarios
    try:
        example_ntl_scenarios()
    except Exception as e:
        print(f"\nExample 3 error: {str(e)}")
    
    # Example 3: Full simulation (optional - requires IEEE feeder files)
    try:
        # example_ieee13_simulation()
        print("\n" + "="*70)
        print("NOTE: Full IEEE 13 simulation requires extracted feeder folders and valid entry files.")
        print("Download from: https://sourceforge.net/p/electricdss/code/HEAD/tree/trunk/Distrib/IEEETestCases/")
        print("Example entry: ieee_feeders/.../IEEE13Nodeckt.dss")
        print("Then uncomment 'example_ieee13_simulation()' in main()")
        print("="*70)
    except Exception as e:
        print(f"\nExample 1 error: {str(e)}")
    
    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + "  Examples completed. Check results/ directory for outputs.".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70 + "\n")


if __name__ == "__main__":
    main()
