# MENG_DIGITAL_TWIN_SIMULATION_IEEE

## Digital Twin NTL Detection System for Electricity Theft

A research implementation of **Non-Technical Loss (NTL) detection** for electricity theft, built for the IEEE MENG Digital Twin Simulation project. The system generates synthetic smart-meter data, constructs a digital twin of expected consumption, and applies multiple machine-learning detectors to flag electricity theft.

---

## Overview

Non-Technical Losses (NTL) in electricity distribution networks arise from energy theft, meter tampering, billing fraud, and meter bypassing. This project implements a full NTL detection pipeline:

```
Smart-Meter Data → Digital Twin → Feature Engineering → NTL Detectors → Evaluation
```

### Theft Scenarios Simulated

| Type | Description |
|---|---|
| **Tampering** | Meter under-reports consumption by a random factor (30–70 %) |
| **Bypass** | Consumer bypasses the meter entirely (near-zero readings) |
| **Diversion** | Irregular drops and spikes (energy diverted intermittently) |

---

## Architecture

```
src/
├── data_generator.py   # Synthetic smart-meter data with NTL injection
├── preprocessing.py    # Daily feature engineering (16 features per consumer-day)
├── digital_twin.py     # Global Ridge regression twin; flags deviations as NTL
├── detector.py         # CUSUM · Isolation Forest · Random Forest · Ensemble
└── evaluator.py        # Accuracy · Precision · Recall · F1 · MCC · AUC-ROC · AUC-PR

tests/
└── test_ntl_detection.py   # 41 unit tests covering every module

main.py                 # End-to-end pipeline
requirements.txt
```

### Detection Strategies

| Strategy | Type | Description |
|---|---|---|
| **Digital Twin** | Unsupervised | Global Ridge model learns normalised consumption shape; flags large negative deviations |
| **CUSUM** | Unsupervised | Per-consumer CUSUM control chart detects persistent downward shifts from early-history baseline |
| **Isolation Forest** | Unsupervised | Anomaly detection on daily feature vectors |
| **Random Forest** | Supervised | Binary classifier trained on labelled consumer-days |
| **Ensemble** | Hybrid | Soft-vote combination (CUSUM 20 %, IsoForest 30 %, RF 50 %) |

---

## Results (100 consumers · 365 days · 20 % theft rate)

| Model | F1 | AUC-ROC | Recall | Precision |
|---|---|---|---|---|
| Digital Twin (baseline) | 0.655 | 0.926 | 0.902 | 0.514 |
| CUSUM (unsupervised) | 0.441 | 0.657 | 1.000 | 0.283 |
| Isolation Forest (unsupervised) | 0.691 | 0.862 | 0.775 | 0.623 |
| Random Forest (supervised) | **0.795** | **0.936** | 0.688 | **0.941** |
| Ensemble | 0.797 | 0.927 | 0.714 | 0.902 |

---

## Quickstart

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the full pipeline

```bash
python main.py
```

### 3. Run tests

```bash
python -m pytest tests/ -v
```

---

## Feature Engineering

The `NTLPreprocessor` extracts 16 features per consumer per day from raw hourly readings:

- **Statistical**: mean, std, min, max, total daily consumption; coefficient of variation
- **Ratio**: peak (18–23 h) to off-peak (00–05 h) consumption ratio
- **Temporal**: weekday, month, is_weekend
- **Rolling (7-day)**: mean, std, min, max of daily totals
- **Change**: day-over-day absolute and percentage change

---

## Digital Twin Design

The twin trains a global **Ridge regression** on *normalised* consumption from clean training consumers:

```
norm_consumption = consumption_kwh / consumer_mean_kwh
```

Features are cyclic encodings of hour-of-day, day-of-week, and month to avoid boundary discontinuities. At inference time each consumer's mean is estimated from their first 14 days (warm-up window), making the model applicable to unseen consumers.

---

## References

- Nizar, A. H., Dong, Z. Y., & Wang, Y. (2008). Power utility nontechnical loss analysis with extreme learning machine method. *IEEE Transactions on Power Systems*.
- Glauner, P., Meira, J. A., Valtchev, P., State, R., & Bettinger, F. (2016). The challenge of non-technical loss detection using artificial intelligence: A survey. *arXiv:1606.00626*.
- Jokar, P., Arianpoo, N., & Leung, V. C. (2016). Electricity theft detection in AMI using customers' consumption patterns. *IEEE Transactions on Smart Grid*.
- Pereira, J., & Silveira, M. (2020). Unsupervised anomaly detection in energy time series data using variational recurrent autoencoders with attention. *ICMLA*.
