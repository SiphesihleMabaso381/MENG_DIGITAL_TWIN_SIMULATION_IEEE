# Future Data Layer

This project is already structured so real utility data can be integrated later without replacing the core simulation logic.

## Current status

At the moment the simulator relies on synthetic and benchmark-style data because institutional access to real utility datasets is not yet available. That is intentional and keeps the project reproducible and transparent.

## Planned upgrade path

The intended staged pathway is:

1. AMI integration for customer meter history
2. SCADA integration for feeder status and operating conditions
3. GIS integration for feeder and customer mapping
4. Calibration against real measurements and event logs

## Where future data should go

Optional input files can be placed under:

- data/inputs/scada/scada.csv
- data/inputs/ami/ami.csv
- data/inputs/gis/gis.csv

## Design principle

The simulation core should continue to work even when real data is absent. In that case it should fall back to the existing synthetic model.

## Why this is useful

This approach keeps the current project useful while making it easier to evolve toward more realistic utility-grade analysis once access to real datasets becomes available.

## Expected outcome

Once real data is integrated, the same simulation framework can be used for more accurate calibration, better anomaly detection, and stronger comparison between synthetic and observed system behavior.
