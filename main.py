"""
Main pipeline for the Digital Twin NTL Detection System.

Execution flow
--------------
1. Generate synthetic smart-meter data (normal + NTL consumers).
2. Split into train / test sets.
3. Fit the Digital Twin on clean training data.
4. Preprocess both splits into feature matrices.
5. Train all three NTL detectors on the training split.
6. Evaluate each detector on the held-out test split.
7. Print a concise evaluation report.

Usage
-----
    python main.py
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from src.data_generator import SmartMeterDataGenerator
from src.preprocessing import NTLPreprocessor
from src.digital_twin import DigitalTwin
from src.detector import NTLDetector
from src.evaluator import evaluate_detection, print_evaluation_report

warnings.filterwarnings("ignore")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SEED = 42
N_CONSUMERS = 100
N_DAYS = 365
THEFT_RATE = 0.20
TEST_FRACTION = 0.25  # fraction of consumers held out for testing


def split_by_consumer(
    df: pd.DataFrame, test_fraction: float, seed: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split dataset by consumer ID so no consumer appears in both splits."""
    consumer_ids = df["consumer_id"].unique()
    train_ids, test_ids = train_test_split(
        consumer_ids, test_size=test_fraction, random_state=seed
    )
    return df[df["consumer_id"].isin(train_ids)], df[df["consumer_id"].isin(test_ids)]


def main() -> None:
    print("=" * 60)
    print("  Digital Twin NTL Detection System")
    print("  IEEE MENG Research — Electricity Theft Detection")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Generate data
    # ------------------------------------------------------------------
    print("\n[1/6] Generating synthetic smart-meter data …")
    gen = SmartMeterDataGenerator(n_consumers=N_CONSUMERS, seed=SEED)
    raw_df = gen.generate(
        start_date="2023-01-01",
        n_days=N_DAYS,
        theft_rate=THEFT_RATE,
        theft_types=["tampering", "bypass", "diversion"],
    )
    n_consumers = raw_df["consumer_id"].nunique()
    n_thieves = raw_df.groupby("consumer_id")["is_theft"].any().sum()
    print(f"    Consumers total : {n_consumers}")
    print(f"    NTL consumers   : {n_thieves}  ({100 * n_thieves / n_consumers:.1f} %)")
    print(f"    Hourly records  : {len(raw_df):,}")

    # ------------------------------------------------------------------
    # 2. Train / test split
    # ------------------------------------------------------------------
    print("\n[2/6] Splitting data by consumer …")
    train_raw, test_raw = split_by_consumer(raw_df, TEST_FRACTION, SEED)
    print(f"    Train consumers : {train_raw['consumer_id'].nunique()}")
    print(f"    Test  consumers : {test_raw['consumer_id'].nunique()}")

    # ------------------------------------------------------------------
    # 3. Fit the Digital Twin on clean training consumers
    # ------------------------------------------------------------------
    print("\n[3/6] Fitting Digital Twin on clean training data …")
    twin = DigitalTwin(anomaly_threshold=-0.40)
    twin.fit(train_raw)

    twin_scores_test = twin.score_consumers(test_raw)
    twin_labels = twin_scores_test.merge(
        test_raw.groupby("consumer_id")["is_theft"].any().reset_index(),
        on="consumer_id",
    )
    twin_metrics = evaluate_detection(
        twin_labels["is_theft"],
        twin_labels["ntl_flag"],
        twin_labels["ntl_score"],
    )
    print_evaluation_report(twin_metrics, "Digital Twin (baseline)")

    # ------------------------------------------------------------------
    # 4. Preprocess features
    # ------------------------------------------------------------------
    print("[4/6] Extracting features …")
    preprocessor = NTLPreprocessor(scale=True)
    train_features = preprocessor.fit_transform(train_raw)
    test_features = preprocessor.transform(test_raw)
    print(f"    Train samples (consumer-days): {len(train_features):,}")
    print(f"    Test  samples (consumer-days): {len(test_features):,}")

    y_train = train_features["is_theft"].astype(int)
    y_test = test_features["is_theft"].astype(int)

    # ------------------------------------------------------------------
    # 5. Train detectors
    # ------------------------------------------------------------------
    print("\n[5/6] Training NTL detectors …")

    strategies = [
        ("CUSUM (unsupervised)", "cusum", False),
        ("Isolation Forest (unsupervised)", "isolation_forest", False),
        ("Random Forest (supervised)", "random_forest", True),
        ("Ensemble", "ensemble", True),
    ]

    results: list[tuple[str, dict]] = []
    for name, strategy, needs_labels in strategies:
        detector = NTLDetector(strategy=strategy, contamination=THEFT_RATE, random_state=SEED)
        detector.fit(train_features, y_train if needs_labels else None)
        y_proba = detector.predict_proba(test_features)
        y_pred = (y_proba >= 0.5).astype(int)
        metrics = evaluate_detection(y_test, y_pred, y_proba)
        results.append((name, metrics))

    # ------------------------------------------------------------------
    # 6. Print results
    # ------------------------------------------------------------------
    print("[6/6] Evaluation results\n")
    for name, metrics in results:
        print_evaluation_report(metrics, name)

    # Summary table
    print("\n  ─── Summary ────────────────────────────────────────────")
    header = f"  {'Model':<38} {'F1':>6} {'AUC-ROC':>8} {'Recall':>7} {'Prec.':>7}"
    print(header)
    print(f"  {'─'*66}")
    for name, m in [("Digital Twin (baseline)", twin_metrics)] + results:
        auc = f"{m.get('auc_roc', 0.0):.4f}"
        print(
            f"  {name:<38} {m['f1']:>6.4f} {auc:>8} {m['recall']:>7.4f} {m['precision']:>7.4f}"
        )
    print()


if __name__ == "__main__":
    main()
