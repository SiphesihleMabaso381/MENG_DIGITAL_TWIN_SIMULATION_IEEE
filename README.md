# Hybrid Grid Digital Twin Simulation

## Overview

This project is a South Africa-oriented digital-twin prototype for studying power distribution behavior, metering quality, and non-technical losses (NTL) in a simplified but explainable way.

It combines:
- physics-based feeder behavior through OpenDSS,
- synthetic but realistic customer-load patterns,
- hybrid smart/legacy metering,
- operational disturbances such as load shedding,
- and exportable reports for analysis and presentation.

The current implementation is best viewed as a research and demonstration prototype rather than a production utility platform.

## Current capabilities

- OpenDSS-based feeder simulation for IEEE 13/34/123 bus test cases
- Hybrid smart and legacy meter modeling
- South Africa-inspired customer behavior and demand shapes
- Separate handling of operational disturbances and theft/NTL events
- Export of simulation results, NTL statistics, and realism summaries
- Automatic dashboard generation and saving to results/main_ieee/dashboard.png
- Optional future integration with real AMI, SCADA, and GIS data

## Project status

This version uses synthetic and benchmark-style data because real utility datasets are not yet available. That is intentional and keeps the work transparent, reproducible, and suitable for early-stage research.

The project is already runnable end to end from the terminal or the VS Code Run button.

## Installation

### Requirements
- Python 3.10+
- OpenDSS-compatible environment
- Windows, Linux, or macOS

### Setup

From the project root, run:

```powershell
.
setup.ps1
```

If you prefer to activate the environment manually, use:

```powershell
& "$env:LOCALAPPDATA\venvs\MENG_DIGITAL_TWIN_SIMULATION_IEEE\Scripts\Activate.ps1"
```

## Quick start

### Default run

```powershell
python main.py
```

This runs the full IEEE13 workflow by default, generates load profiles, performs the simulation, relocates outputs into results/main_ieee, and opens the dashboard after completion.

### Demo run

```powershell
python main.py --demo
```

### Higher-realism example

```powershell
python main.py --feeder IEEE13 --realism-profile utility --seed 42 --strict-realism
```

### Useful options

- --demo
- --feeder IEEE13|IEEE34|IEEE123
- --realism-profile benchmark|utility|stressed
- --seed <int>
- --random-seed
- --strict-realism / --no-strict-realism
- --max-calibration-attempts <int>
- --region south_africa|global

## Output files

Full runs write consolidated outputs to results/main_ieee:

- simulation_results.csv
- ntl_events.csv
- ntl_statistics.csv
- simulation_config.json
- realism_report.csv
- load_profiles.csv
- dashboard.png

## Project structure

```text
MENG_DIGITAL_TWIN_SIMULATION_IEEE/
├── main.py
├── example_simulation.py
├── src/
│   ├── dashboard.py
│   ├── data_sources.py
│   ├── hybrid_metering.py
│   ├── load_profiles.py
│   ├── ntl_injection.py
│   ├── opendsss_interface.py
│   └── simulation_engine.py
├── ieee_feeders/
├── results/
├── docs/
├── notebooks/
└── tests/
```

## Main modules

- src/load_profiles.py: builds synthetic load behavior for different customer classes and South Africa-oriented profiles
- src/hybrid_metering.py: simulates smart and legacy meters, including error and communication behavior
- src/ntl_injection.py: injects theft/NTL and operational-disturbance scenarios separately
- src/simulation_engine.py: coordinates the full workflow and exports results
- src/dashboard.py: creates the post-run visualization dashboard

## Notes on realism

The model is intentionally transparent and configurable. It supports:
- utility-style calibration targets,
- operational disturbances such as load shedding,
- distinct NTL and non-NTL loss interpretation,
- and exportable metrics for comparison and reporting.

The current realism is good for research, education, and presentation. It is not yet intended for direct operational decision-making with live utility data.

## Future direction

The next step is to upgrade the project from synthetic benchmarking to real utility data once access is available. The intended path is:
1. AMI integration,
2. SCADA integration,
3. GIS-based feeder mapping,
4. calibration against real measurements.

## License and usage

This repository is intended for academic, research, and educational use. Please adapt it carefully if you intend to use it for business or operational deployment.

## References

- OpenDSS
- IEEE feeder test cases
- Python scientific stack (pandas, numpy, matplotlib)

Last updated: August 2026
