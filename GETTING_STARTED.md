# Getting Started with the Hybrid Grid Digital Twin Simulator

## Current project state

The project now runs as a full end-to-end synthetic simulation workflow from the terminal or the VS Code Run button. It generates benchmark feeder, load, metering, NTL, and operational-disturbance results, evaluates the generated output with the readiness modules, writes everything into results/main_ieee, and opens the dashboard automatically after a full run.

This phase intentionally does not require real utility data or a final trained AI model. It is a reproducible research and deployment-preparation platform based on IEEE benchmark feeders and synthetic scenarios.

## Quick setup

### 1. Install dependencies

From the project root:

```powershell
.\setup.ps1
```

This creates or updates the local Python environment for the project.

### 2. Make sure the feeder files are available

The repository already includes IEEE feeder content under the ieee_feeders folder. If needed, verify that the expected .dss entry files are present.

### 3. Run the project

Recommended starter command:

```powershell
python main.py --feeder IEEE13 --realism-profile utility --seed 42 --no-strict-realism
```

This is a good default run for a quick test because it is deterministic and completes reliably.

## Common commands

### Full run

```powershell
python main.py
```

### Demo run

```powershell
python main.py --demo
```

### Alternative feeders

```powershell
python main.py --feeder IEEE34 --realism-profile utility --seed 42 --no-strict-realism
python main.py --feeder IEEE123 --realism-profile utility --seed 42 --no-strict-realism
```

## CLI options

- --demo
- --feeder IEEE13|IEEE34|IEEE123
- --realism-profile benchmark|utility|stressed
- --seed <int>
- --random-seed
- --strict-realism / --no-strict-realism
- --max-calibration-attempts <int>
- --region south_africa|global

## Output files

After a full run, the consolidated outputs are placed in results/main_ieee.

Typical files:

- results/main_ieee/simulation_results.csv
- results/main_ieee/ntl_events.csv
- results/main_ieee/ntl_statistics.csv
- results/main_ieee/simulation_config.json
- results/main_ieee/realism_report.csv
- results/main_ieee/sensitivity_report.csv
- results/main_ieee/labeling_ready.csv
- results/main_ieee/load_profiles.csv
- results/main_ieee/deployment_readiness_report.json
- results/main_ieee/dashboard.png

## Notes on realism

The simulator deliberately separates operational disturbances from NTL events. This makes it easier to distinguish:
- load shedding or outages,
- meter behavior issues,
- and theft-like patterns.

After a full run, Step 11 assesses the generated results using data quality, physics consistency, explainability, federated-learning scaffolding, and benchmark validation. This score describes synthetic prototype readiness; it is not a live utility deployment score.

## Troubleshooting

### Dashboard or plotting issues

If plotting fails, the launcher will try the external Python environment in the local AppData venv path. If the error persists, make sure the plotting dependencies are installed.

### Missing feeder files

Make sure the expected IEEE feeder entry files exist under ieee_feeders.

### Strict realism failures

If a strict-realism run fails, try a slightly smaller target or disable strict mode for exploratory runs:

```powershell
python main.py --feeder IEEE13 --realism-profile utility --seed 42 --no-strict-realism
```

## Suggested next step

Open the generated outputs in results/main_ieee and review the dashboard, realism report, and NTL statistics.

This project is currently a synthetic research prototype for power-system and NTL experimentation. Its current improvement path is repeatable benchmarking, baseline comparison, robustness testing, explainable alert generation, and automated verification. It also includes sensitivity reporting, a labeling-ready dataset, and a deployment-readiness report for research evaluation.
