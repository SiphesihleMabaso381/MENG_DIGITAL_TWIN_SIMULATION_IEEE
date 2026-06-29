# Future Data Layer

This project is structured so real utility datasets can be added later without changing the core simulation engine.

## What will be added later

- SCADA data
- AMI smart meter history
- GIS network map data

## Current rule

The simulation must keep working with synthetic and benchmark data even if no real utility data is present.

## Where real data should go

- `data/inputs/scada/scada.csv`
- `data/inputs/ami/ami.csv`
- `data/inputs/gis/gis.csv`

## How the code should use it

The simulation core should not read raw utility files directly.
Instead, it should use a small adapter layer that:

1. checks whether real data exists
2. loads it if available
3. falls back to synthetic data if it is not available

## Why this is safe

This keeps the current code stable.
It means adding real datasets later will mostly change the data layer, not the full simulation logic.

## Suggested future integration order

1. SCADA adapter for feeder status and voltage measurements
2. AMI adapter for customer meter readings
3. GIS adapter for network location and feeder mapping
4. Validation step to compare real data against simulation outputs
