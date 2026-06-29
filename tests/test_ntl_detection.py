"""Tests for NTL (Non-Technical Loss) detection system."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.data_generator import SmartMeterDataGenerator
from src.preprocessing import NTLPreprocessor
from src.digital_twin import DigitalTwin
from src.detector import (
    CUSUMDetector,
    IsolationForestDetector,
    RandomForestDetector,
    NTLDetector,
)
from src.evaluator import evaluate_detection


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def small_dataset():
    """A small synthetic dataset: 20 consumers, 60 days."""
    gen = SmartMeterDataGenerator(n_consumers=20, seed=0)
    return gen.generate(
        start_date="2023-01-01",
        n_days=60,
        theft_rate=0.25,
        theft_types=["tampering", "bypass", "diversion"],
    )


@pytest.fixture(scope="module")
def feature_matrix(small_dataset):
    """Preprocessed daily feature matrix derived from small_dataset."""
    preprocessor = NTLPreprocessor(scale=True)
    return preprocessor.fit_transform(small_dataset)


# ---------------------------------------------------------------------------
# Data Generator
# ---------------------------------------------------------------------------

class TestSmartMeterDataGenerator:
    def test_output_shape(self, small_dataset):
        expected_rows = 20 * 60 * 24
        assert len(small_dataset) == expected_rows

    def test_required_columns(self, small_dataset):
        required = {"consumer_id", "timestamp", "consumption_kwh", "is_theft", "theft_type"}
        assert required.issubset(set(small_dataset.columns))

    def test_consumption_non_negative(self, small_dataset):
        assert (small_dataset["consumption_kwh"] >= 0).all()

    def test_theft_rate_approx(self, small_dataset):
        n_thieves = small_dataset.groupby("consumer_id")["is_theft"].any().sum()
        n_total = small_dataset["consumer_id"].nunique()
        theft_rate = n_thieves / n_total
        # Allow ±10 pp tolerance around 25 %
        assert 0.10 <= theft_rate <= 0.40

    def test_theft_types_present(self, small_dataset):
        theft_types = set(small_dataset.loc[small_dataset["is_theft"], "theft_type"].unique())
        assert theft_types.issubset({"tampering", "bypass", "diversion"})

    def test_normal_consumers_have_no_theft_flag(self, small_dataset):
        normal_consumers = (
            small_dataset.groupby("consumer_id")["is_theft"]
            .any()
            .pipe(lambda s: s[~s].index)
        )
        normal_rows = small_dataset[small_dataset["consumer_id"].isin(normal_consumers)]
        assert not normal_rows["is_theft"].any()

    def test_reproducibility(self):
        gen1 = SmartMeterDataGenerator(n_consumers=5, seed=123)
        gen2 = SmartMeterDataGenerator(n_consumers=5, seed=123)
        df1 = gen1.generate(n_days=7)
        df2 = gen2.generate(n_days=7)
        pd.testing.assert_frame_equal(df1, df2)

    def test_different_seeds_differ(self):
        gen1 = SmartMeterDataGenerator(n_consumers=5, seed=1)
        gen2 = SmartMeterDataGenerator(n_consumers=5, seed=2)
        df1 = gen1.generate(n_days=7)
        df2 = gen2.generate(n_days=7)
        assert not df1["consumption_kwh"].equals(df2["consumption_kwh"])


# ---------------------------------------------------------------------------
# Preprocessor
# ---------------------------------------------------------------------------

class TestNTLPreprocessor:
    def test_output_columns(self, feature_matrix):
        expected = {
            "consumer_id", "date",
            "mean_daily", "std_daily", "min_daily", "max_daily", "total_daily",
            "cv", "peak_offpeak_ratio",
            "weekday", "month", "is_weekend",
            "rolling7_mean", "rolling7_std", "rolling7_min", "rolling7_max",
            "daily_change", "pct_change",
            "is_theft",
        }
        assert expected.issubset(set(feature_matrix.columns))

    def test_no_nan_in_feature_cols(self, feature_matrix):
        feature_cols = [
            c for c in feature_matrix.columns
            if c not in ("consumer_id", "date", "is_theft")
        ]
        assert feature_matrix[feature_cols].isna().sum().sum() == 0

    def test_rows_equal_consumer_days(self, small_dataset):
        preprocessor = NTLPreprocessor(scale=False)
        features = preprocessor.fit_transform(small_dataset)
        expected = small_dataset["consumer_id"].nunique() * 60
        assert len(features) == expected

    def test_transform_matches_fit_transform(self, small_dataset):
        preprocessor = NTLPreprocessor(scale=False)
        fit_result = preprocessor.fit_transform(small_dataset)
        transform_result = preprocessor.transform(small_dataset)
        pd.testing.assert_frame_equal(fit_result, transform_result)

    def test_is_weekend_binary(self, small_dataset):
        preprocessor = NTLPreprocessor(scale=False)
        features = preprocessor.fit_transform(small_dataset)
        assert set(features["is_weekend"].unique()).issubset({0, 1})

    def test_weekday_range(self, small_dataset):
        preprocessor = NTLPreprocessor(scale=False)
        features = preprocessor.fit_transform(small_dataset)
        assert features["weekday"].between(0, 6).all()

    def test_month_range(self, small_dataset):
        preprocessor = NTLPreprocessor(scale=False)
        features = preprocessor.fit_transform(small_dataset)
        assert features["month"].between(1, 12).all()


# ---------------------------------------------------------------------------
# Digital Twin
# ---------------------------------------------------------------------------

class TestDigitalTwin:
    def test_fit_and_predict(self, small_dataset):
        twin = DigitalTwin()
        twin.fit(small_dataset)
        expected = twin.predict_expected(small_dataset.head(48))
        assert len(expected) == 48
        assert (expected >= 0).all()

    def test_unfitted_raises(self, small_dataset):
        twin = DigitalTwin()
        with pytest.raises(RuntimeError, match="fitted"):
            twin.predict_expected(small_dataset.head(10))

    def test_anomaly_scores_columns(self, small_dataset):
        twin = DigitalTwin()
        twin.fit(small_dataset)
        scored = twin.compute_anomaly_scores(small_dataset.head(240))
        assert "expected_kwh" in scored.columns
        assert "deviation" in scored.columns
        assert "ntl_flag" in scored.columns

    def test_deviation_bounded(self, small_dataset):
        twin = DigitalTwin()
        twin.fit(small_dataset)
        scored = twin.compute_anomaly_scores(small_dataset.head(240))
        assert scored["deviation"].between(-1.0, 1.0).all()

    def test_score_consumers_returns_consumer_day_rows(self, small_dataset):
        twin = DigitalTwin()
        twin.fit(small_dataset)
        scored = twin.score_consumers(small_dataset)
        # Should be 20 consumers × 60 days
        expected_rows = small_dataset["consumer_id"].nunique() * 60
        assert len(scored) == expected_rows


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

class TestCUSUMDetector:
    def test_predict_binary(self, feature_matrix):
        detector = CUSUMDetector()
        detector.fit(feature_matrix)
        preds = detector.predict(feature_matrix)
        assert set(np.unique(preds)).issubset({0, 1})

    def test_predict_proba_shape(self, feature_matrix):
        detector = CUSUMDetector()
        detector.fit(feature_matrix)
        proba = detector.predict_proba(feature_matrix)
        assert proba.shape == (len(feature_matrix), 2)

    def test_proba_sums_to_one(self, feature_matrix):
        detector = CUSUMDetector()
        detector.fit(feature_matrix)
        proba = detector.predict_proba(feature_matrix)
        np.testing.assert_allclose(proba.sum(axis=1), 1.0, atol=1e-6)


class TestIsolationForestDetector:
    def test_predict_binary(self, feature_matrix):
        detector = IsolationForestDetector(contamination=0.20, random_state=42)
        detector.fit(feature_matrix)
        preds = detector.predict(feature_matrix)
        assert set(np.unique(preds)).issubset({0, 1})

    def test_predict_proba_range(self, feature_matrix):
        detector = IsolationForestDetector(contamination=0.20, random_state=42)
        detector.fit(feature_matrix)
        proba = detector.predict_proba(feature_matrix)
        assert (proba[:, 1] >= 0).all() and (proba[:, 1] <= 1).all()


class TestRandomForestDetector:
    def test_fit_and_predict(self, feature_matrix):
        y = feature_matrix["is_theft"].astype(int)
        detector = RandomForestDetector(n_estimators=10, random_state=42)
        detector.fit(feature_matrix, y)
        preds = detector.predict(feature_matrix)
        assert len(preds) == len(feature_matrix)
        assert set(np.unique(preds)).issubset({0, 1})

    def test_feature_importance_available(self, feature_matrix):
        y = feature_matrix["is_theft"].astype(int)
        detector = RandomForestDetector(n_estimators=10, random_state=42)
        detector.fit(feature_matrix, y)
        assert detector.feature_importance is not None
        assert len(detector.feature_importance) > 0


class TestNTLDetector:
    @pytest.mark.parametrize("strategy", ["cusum", "isolation_forest", "random_forest", "ensemble"])
    def test_strategies_run(self, feature_matrix, strategy):
        y = feature_matrix["is_theft"].astype(int)
        detector = NTLDetector(strategy=strategy, random_state=42)
        detector.fit(feature_matrix, y)
        preds = detector.predict(feature_matrix)
        assert len(preds) == len(feature_matrix)
        assert set(np.unique(preds)).issubset({0, 1})

    def test_invalid_strategy_raises(self):
        with pytest.raises(ValueError, match="strategy"):
            NTLDetector(strategy="unknown")

    def test_rf_without_labels_raises(self, feature_matrix):
        detector = NTLDetector(strategy="random_forest")
        detector.fit(feature_matrix, y=None)  # no labels provided
        with pytest.raises(RuntimeError, match="fitted"):
            detector.predict_proba(feature_matrix)

    def test_proba_in_range(self, feature_matrix):
        y = feature_matrix["is_theft"].astype(int)
        for strategy in ["cusum", "isolation_forest", "random_forest", "ensemble"]:
            detector = NTLDetector(strategy=strategy, random_state=42)
            detector.fit(feature_matrix, y)
            proba = detector.predict_proba(feature_matrix)
            assert (proba >= 0).all() and (proba <= 1).all(), f"Out-of-range for {strategy}"


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

class TestEvaluateDetection:
    def test_perfect_prediction(self):
        y = np.array([0, 0, 1, 1, 0, 1])
        metrics = evaluate_detection(y, y)
        assert metrics["accuracy"] == 1.0
        assert metrics["precision"] == 1.0
        assert metrics["recall"] == 1.0
        assert metrics["f1"] == 1.0
        assert metrics["fp"] == 0
        assert metrics["fn"] == 0

    def test_all_wrong(self):
        y_true = np.array([0, 0, 1, 1])
        y_pred = np.array([1, 1, 0, 0])
        metrics = evaluate_detection(y_true, y_pred)
        assert metrics["accuracy"] == 0.0
        assert metrics["tp"] == 0
        assert metrics["tn"] == 0

    def test_auc_roc_computed_with_proba(self):
        rng = np.random.default_rng(0)
        y = rng.integers(0, 2, size=200)
        y_proba = rng.uniform(0, 1, size=200)
        metrics = evaluate_detection(y, (y_proba > 0.5).astype(int), y_proba)
        assert "auc_roc" in metrics
        assert 0.0 <= metrics["auc_roc"] <= 1.0
        assert "auc_pr" in metrics
        assert "optimal_threshold" in metrics

    def test_roc_curve_keys(self):
        rng = np.random.default_rng(1)
        y = rng.integers(0, 2, size=100)
        y_proba = rng.uniform(0, 1, size=100)
        metrics = evaluate_detection(y, (y_proba > 0.5).astype(int), y_proba)
        assert "fpr" in metrics["roc_curve"]
        assert "tpr" in metrics["roc_curve"]

    def test_no_proba_keys_absent(self):
        y = np.array([0, 1, 0, 1])
        metrics = evaluate_detection(y, y)
        assert "auc_roc" not in metrics
        assert "auc_pr" not in metrics

    def test_confusion_matrix_consistency(self):
        y_true = np.array([0, 0, 1, 1, 1])
        y_pred = np.array([0, 1, 1, 1, 0])
        metrics = evaluate_detection(y_true, y_pred)
        assert metrics["tp"] == 2
        assert metrics["fp"] == 1
        assert metrics["fn"] == 1
        assert metrics["tn"] == 1

    def test_mcc_range(self):
        rng = np.random.default_rng(7)
        y_true = rng.integers(0, 2, size=100)
        y_pred = rng.integers(0, 2, size=100)
        metrics = evaluate_detection(y_true, y_pred)
        assert -1.0 <= metrics["mcc"] <= 1.0
