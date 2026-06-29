# Hybrid Grid Digital Twin Simulation

## Overview

A comprehensive, high-fidelity digital twin simulator for hybrid power distribution networks combining legacy and smart metering infrastructure. Designed for research on **Non-Technical Loss (NTL) detection and mitigation** using federated learning and explainable AI.

**Key Features:**
- ✅ OpenDSS integration for physics-based power flow analysis
- ✅ IEEE 13/34/123 bus test feeders support
- ✅ Hybrid smart + legacy metering system simulation
- ✅ Realistic load profiles (residential/commercial/industrial/agricultural/public/institutional/bulk)
- ✅ 6 NTL scenario types with temporal scheduling
- ✅ Quasi-static time-series (QSTS) simulation
- ✅ Data export for federated learning pipelines
- ✅ Automatic dashboard generation and saved dashboard image
- ✅ Optional SCADA / AMI / GIS data layer for future real datasets

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│          Hybrid Grid Digital Twin Simulator                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  OpenDSS     │  │   Load       │  │   Hybrid     │      │
│  │  Interface   │  │  Profiles    │  │  Metering    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│         │                 │                 │                │
│         └─────────────────┴─────────────────┘                │
│                      │                                       │
│          ┌───────────▼────────────┐                         │
│          │   Simulation Engine    │                         │
│          └───────────┬────────────┘                         │
│                      │                                       │
│          ┌───────────▼────────────┐                         │
│          │  NTL Injection Engine  │                         │
│          └───────────┬────────────┘                         │
│                      │                                       │
│          ┌───────────▼────────────┐                         │
│          │  Results & Export      │                         │
│          │  (CSV, JSON, etc.)     │                         │
│          └───────────────────────┘                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Installation

### Requirements
- Python 3.8+
- OpenDSS (installation varies by OS)
- Windows, Linux, or macOS

### Setup

1. **Clone or create project:**
```bash
cd MENG_DIGITAL_TWIN_SIMULATION_IEEE
```

2. **Install Python dependencies:**
```bash
pip install -r requirements.txt
```

3. **Download IEEE test feeders:**
   - Visit: https://sourceforge.net/p/electricdss/code/HEAD/tree/trunk/Distrib/IEEETestCases/
  - Download and extract: `13Bus`, `34Bus`, and `123Bus` folders
  - Keep each feeder folder intact inside `ieee_feeders/` (do not copy only one file for 34/123)
  - Use entry files:
    - 13Bus: `.../IEEE13Nodeckt.dss`
    - 34Bus: `.../Run_IEEE34Mod1.dss` (or `Run_IEEE34Mod2.dss`)
    - 123Bus: `.../Run_IEEE123Bus.DSS` (or `IEEE123Master.dss`)

4. **Verify OpenDSS installation:**
```python
import opendssdirect as dss
print(dss.run_command("New Circuit.test"))
```

---

## Quick Start

### Run Example Simulations

```bash
python main.py
```

This runs the full IEEE 13-bus simulation by default, then opens the dashboard and saves it to `results/main_ieee/dashboard.png`.

If you want the lightweight demo flow, run:

```bash
python main.py --demo
```

The demo still generates the load profile and NTL example outputs.

### Output
- Full-run outputs are exported to: `results/main_ieee/`
- CSV files with measurements, NTL events, and statistics
- Dashboard image saved as `results/main_ieee/dashboard.png`
- Demo load profile output remains in `results/load_profiles.csv`

---

## Project Structure

```
MENG_DIGITAL_TWIN_SIMULATION_IEEE/
├── src/
│   ├── __init__.py                  # Package initialization
│   ├── opendsss_interface.py        # OpenDSS wrapper (500+ lines)
│   ├── hybrid_metering.py           # Smart/legacy meter simulation (400+ lines)
│   ├── load_profiles.py             # Load generation engine (500+ lines)
│   ├── ntl_injection.py             # NTL scenario injection (500+ lines)
│   └── simulation_engine.py         # Main orchestrator (400+ lines)
├── ieee_feeders/                    # IEEE .dss feeder files (download from OpenDSS)
├── config/                          # Configuration files (YAML/JSON)
├── data/                            # Generated datasets and optional utility inputs
│   └── inputs/                      # SCADA / AMI / GIS drop-in folder
│       ├── scada/                   # Optional SCADA CSV files
│       ├── ami/                     # Optional AMI CSV files
│       └── gis/                     # Optional GIS CSV files
├── results/                         # Simulation outputs
├── notebooks/                       # Jupyter analysis notebooks
├── docs/                            # Documentation
├── src/data_sources.py              # Optional utility-data loader/adapters
├── src/dashboard.py                 # Dashboard visualizer
├── example_simulation.py            # Executable examples
├── main.py                          # Default entrypoint for full simulation + dashboard
├── requirements.txt                 # Python dependencies
└── README.md                        # This file
```

### Optional Utility Data Layer

Real-world SCADA, AMI, and GIS datasets can be added later without changing the simulation core.
The code now expects optional files in:

- `data/inputs/scada/scada.csv`
- `data/inputs/ami/ami.csv`
- `data/inputs/gis/gis.csv`

If those files are absent, the simulator continues using the current synthetic/benchmark data.
The core simulation does not depend on these files being present.

---

## Core Modules

### 1. OpenDSS Interface (`src/opendsss_interface.py`)

Wrapper around `opendssdirect.py` for high-level control.

**Key features:**
- Load IEEE feeder files
- Set/get bus voltages and load power
- Solve single-point and quasi-static time-series (QSTS)
- Inject NTL scenarios at OpenDSS level
- Extract results (voltages, currents, power)

**Usage:**
```python
from src.opendsss_interface import OpenDSSInterface

# Initialize
opendss = OpenDSSInterface(
  "ieee_feeders/electricdss-code-r4166-trunk-Distrib-IEEETestCases-13Bus/"
  "electricdss-code-r4166-trunk-Distrib-IEEETestCases-13Bus/IEEE13Nodeckt.dss",
  "IEEE13"
)

# Load circuit
opendss.load_circuit()

# Set load power
opendss.set_load_power("load_name", p_kw=10, q_kvar=2)

# Solve power flow
opendss.solve_power_flow(mode="snapshot")

# Get results
voltage = opendss.get_bus_voltage("bus_name")
power = opendss.get_load_power("load_name")

# Run quasi-static time-series
qsts_results = opendss.quasi_static_time_series(num_steps=96)  # 24 hours
```

### 2. Hybrid Metering System (`src/hybrid_metering.py`)

Simulates realistic smart and legacy meters with errors and communication issues.

**Key features:**
- Smart meter characteristics (IEC 62053 Class 0.5)
- Legacy meter characteristics (Class 2.0, monthly reads)
- Measurement errors (±accuracy class)
- Clock drift simulation
- Communication loss (packet dropout)
- Tamper detection flags

**Usage:**
```python
from src.hybrid_metering import HybridMeteringSystem
from src.load_profiles import CustomerType

# Initialize
metering = HybridMeteringSystem(['node1', 'node2', 'node3'])

# Deploy meters
metering.deploy_meters_by_penetration(smart_meter_fraction=0.6)

# Record measurements
measurements = metering.record_all_measurements(
    {'node1': (10.5, 2.1), 'node2': (25.3, 5.8)},
    time_interval_minutes=15
)

# Get metering statistics
stats = metering.get_metering_statistics()
# {'total_meters': 3, 'smart_meters': 2, 'legacy_meters': 1, ...}

# Inject meter tampering
metering.inject_ntl_at_meter('node1', 'meter_tampering', 0.3)
```

### 3. Load Profiles (`src/load_profiles.py`)

Generates realistic consumption patterns with temporal and seasonal variations.

**Key features:**
- 7 customer types: Residential, Commercial, Industrial, Agricultural, Public/Municipal, Institutional, Bulk
- Hourly and 15-minute resolution
- Day-of-week factors (weekday vs. weekend)
- Seasonal variations (summer/winter peaks)
- Stochastic noise
- OpenEI-compatible format

**Usage:**
```python
from src.load_profiles import HybridGridLoadManager, CustomerType, LoadProfileGenerator

# Initialize generator
generator = LoadProfileGenerator(CustomerType.RESIDENTIAL, annual_consumption_kwh=4000)

# Get hourly profile
hourly_profile = generator.get_hourly_profile(day_of_year=180)  # Summer day

# Get instantaneous power
power_kw = generator.get_power_kw(day_of_year=180, hour=14.5, peak_power_kw=8.0)

# Or use the grid-level manager
load_manager = HybridGridLoadManager()
load_manager.add_load_nodes_bulk([
    ('node1', CustomerType.RESIDENTIAL, 4000),
    ('node2', CustomerType.COMMERCIAL, 50000),
    ('node3', CustomerType.INDUSTRIAL, 200000),
])

# Get all loads at specific time
loads = load_manager.get_loads_at_time(day_of_year=180, hour=14.5)
# {'node1': (2.3, 0.5), 'node2': (45.1, 10.2), 'node3': (185.3, 35.2)}

# Generate daily profile
daily_profile = load_manager.generate_daily_profiles(day_of_year=180)
```

### 4. NTL Injection Engine (`src/ntl_injection.py`)

Schedules and simulates realistic non-technical loss scenarios.

**Supported NTL types:**
1. **Full Meter Bypass** - Entire load diverted, meter reads zero
2. **Partial Meter Bypass** - Fraction of load diverted
3. **Meter Tampering** - Meter underreports consumption
4. **Illegal Connection** - Unmetered load added to node
5. **Load Manipulation** - Temporal shifting/peak clipping
6. **Meter Freezing** - Meter reading halts periodically

**Usage:**
```python
from src.ntl_injection import NTLInjectionEngine, NTLType

ntl_engine = NTLInjectionEngine(load_manager)

# Schedule NTL event
ntl_engine.schedule_ntl_event(
    node_name='node1',
    ntl_type=NTLType.PARTIAL_METER_BYPASS,
    start_day=5,
    start_hour=20.0,
    duration_hours=6.0,
    intensity=0.35,  # 35% theft
    description="Theft at residential node 1"
)

# Get power with NTL applied
power_data = ntl_engine.get_node_power_with_ntl(
    node_name='node1', 
    day_of_year=5, 
    hour=22.5
)
# {'actual_power': (10.5, 2.1), 'metered_power': (6.8, 1.4), 'ntl_loss': (3.7, 0.7)}

# Generate realistic theft patterns
ntl_engine.generate_realistic_theft_scenarios(
    num_theft_nodes=5,
    sim_duration_days=30
)

# Get NTL summary
summary = ntl_engine.get_ntl_summary(day_of_year=5, hour=22.5)
# {'total_actual_kw': 150.3, 'total_metered_kw': 145.1, 'total_ntl_loss_kw': 5.2, ...}
```

### 5. Simulation Engine (`src/simulation_engine.py`)

Orchestrates full digital twin simulation.

**Usage:**
```python
from src.simulation_engine import HybridGridDigitalTwin, SimulationConfig

# Configure
config = SimulationConfig()
config.feeder_name = "IEEE13"
config.simulation_days = 7
config.time_step_minutes = 15
config.smart_meter_penetration = 0.6

# Create digital twin
digital_twin = HybridGridDigitalTwin(config)
digital_twin.setup_feeder(opendss)
digital_twin.setup_load_profiles(load_manager)
digital_twin.setup_metering_system(metering_system)
digital_twin.setup_ntl_engine(ntl_engine)

# Run simulation
results_df = digital_twin.run_simulation()

# Export results
digital_twin.export_results("results/simulation_output")

# Print summary
digital_twin.print_summary()
```

The launcher in `main.py` now runs the full IEEE13 flow by default, then exports the dashboard image into `results/main_ieee/`.

---

## Data Output Format

### Main Results (CSV)

**File:** `simulation_results.csv`

```
meter_id,node_name,actual_p_kw,measured_p_kw,energy_kwh,meter_type,ntl_type,day,hour,...
SM_node1,node1,10.5,10.2,2.55,smart,None,1,0.0,...
LM_node2,node2,25.3,24.1,6.03,legacy,partial_meter_bypass,1,0.25,...
```

### NTL Events (CSV)

**File:** `ntl_events.csv`

```
Node,NTL_Type,Start_Day,Start_Hour,Duration_Hours,Intensity,Description
node1,partial_meter_bypass,5,20.0,6.0,0.35,Theft at residential node 1
node3,meter_tampering,10,8.0,12.0,0.30,Meter tampering at industrial node 3
```

### Statistics (CSV)

**File:** `ntl_statistics.csv`

```
Node,Meter_Type,Total_Energy_kWh,Avg_Power_kW,Max_Power_kW,Total_NTL_Loss_kWh,NTL_Events_Count,...
node1,smart,560.4,23.3,35.2,85.3,3,...
node2,legacy,1280.5,53.1,80.5,0.0,0,...
```

---

## Real-World Fidelity Checklist

- ✅ **Network Physics**
  - Kirchhoff's laws enforced by OpenDSS
  - Unbalanced 3-phase networks
  - Transformer and feeder behavior in the test systems

- ✅ **Load Profiles**
  - Residential, commercial, industrial, agricultural, public, institutional, and bulk customers
  - Seasonal and day-of-week variations
  - Stochastic variability

- ✅ **Smart and Legacy Meters**
  - Interval-style readings and meter-specific errors
  - Communication loss and tamper flags
  - Mixed smart/legacy deployment

- ✅ **NTL Scenarios**
  - Meter bypass, tampering, illegal connection, load manipulation, and meter freezing
  - Temporal scheduling of suspicious events

- ✅ **Future Utility Data Layer**
  - SCADA, AMI, and GIS inputs can be added later
  - Core simulation keeps working without them

---

## Integration with Federated Learning

This simulator generates datasets ready for federated learning pipelines:

```python
# Export as numpy arrays for ML
results_df = digital_twin._compile_results_dataframe()

# Create feature matrix
features = results_df[['measured_p_kw', 'measured_q_kvar', 'Voltage_pu', ...]].values
labels = (results_df['ntl_type'] != 'None').astype(int).values

# Create metadata for federated partitioning
meter_types = results_df['meter_type'].values
nodes = results_df['node_name'].values

# Ready for federated learning framework
# (e.g., TensorFlow Federated, Flower, etc.)
```

---

## Configuration Files

Create `config/simulation_config.yaml`:

```yaml
# Feeder Configuration
feeder:
  name: IEEE13
  path: "ieee_feeders/electricdss-code-r4166-trunk-Distrib-IEEETestCases-13Bus/electricdss-code-r4166-trunk-Distrib-IEEETestCases-13Bus/IEEE13Nodeckt.dss"
  buses: 13

# Simulation Parameters
simulation:
  duration_days: 30
  time_step_minutes: 15
  quasi_static_mode: true
  seed: 42

# Metering Configuration
metering:
  smart_meter_penetration: 0.6
  smart_meter_accuracy_class: 0.5
  legacy_meter_accuracy_class: 2.0
  communication_reliability: 0.95

# Load Configuration
loads:
  - name: node1
    type: residential
    annual_kwh: 4000
  - name: node2
    type: commercial
    annual_kwh: 50000

# NTL Configuration
ntl:
  enable: true
  num_theft_nodes: 3
  intensity_range: [0.2, 0.6]
  scenarios:
    - type: partial_meter_bypass
      probability: 0.4
    - type: meter_tampering
      probability: 0.35
    - type: illegal_connection
      probability: 0.25
```

---

## Advanced Topics

### Custom Load Profiles

To use real ISSDA or OpenEI data:

```python
# Load external CSV
real_data = pd.read_csv("issda_profiles.csv")

# Replace synthetic profile
for node_name, data_row in real_data.iterrows():
    load_manager.node_profiles[node_name].generator.scaling_factor = ...
```

### Concept Drift

Simulate evolving theft patterns:

```python
# Initial theft intensity
intensity = 0.3

# Adaptively increase after utility inspection
if utility_inspects_node:
    intensity *= 0.7  # Thief reduces to avoid detection
```

### South African Grid Context

Include load shedding and prepaid meters:

```python
# Load shedding schedule
loadshedding_schedule = {
    'stage_1': 0.05,  # 5% load shed
    'stage_6': 0.30,  # 30% load shed
    'stage_8': 0.60,  # 60% load shed
}

# Apply to load profile
if current_stage > 0:
    load *= (1 - loadshedding_schedule[f'stage_{current_stage}'])
```

---

## Troubleshooting

### OpenDSS DLL not found
**Solution:** Install 32-bit Python or install OpenDSS COM interface:
```bash
pip install opendssdirect-py  # Alternative: opendssdirect.py
```

### Convergence issues
**Solution:** Verify circuit file, reduce time step, or enable tap changer limiting:
```python
opendss.run_command("Set ControlMode=OFF")  # Disable controls temporarily
```

### Memory issues with large datasets
**Solution:** Export results in chunks or use sparse matrices:
```python
# Process in batches
for day in range(1, config.simulation_days + 1):
    daily_results = export_day(day)
    daily_results.to_csv(f"day_{day}.csv")
```

---

## Citation

If using this simulator for research, please cite:

```bibtex
@software{ntl_digital_twin_2024,
  title={Hybrid Grid Digital Twin Simulator for NTL Detection Research},
  author={Your Name},
  year={2024},
  url={https://github.com/yourrepo/MENG_DIGITAL_TWIN_SIMULATION_IEEE},
  note={MEng Research Project}
}
```

---

## References

- **OpenDSS:** https://sourceforge.net/p/electricdss/wiki/home/
- **IEEE Test Cases:** https://sourceforge.net/p/electricdss/code/HEAD/tree/trunk/Distrib/IEEETestCases/
- **OpenEI Datasets:** https://openei.org/
- **ISSDA:** https://www.ucd.ie/issda/

---

## Support

For issues or questions:
1. Check this README first
2. Review `example_simulation.py` for usage patterns
3. Consult OpenDSS documentation: https://sourceforge.net/p/electricdss/wiki/

---

**Last Updated:** June 2024  
**Version:** 1.0.0  
**Status:** Production Ready for Research
