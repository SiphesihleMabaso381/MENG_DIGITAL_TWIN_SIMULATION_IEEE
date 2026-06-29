"""
Digital Twin Model for Expected Electricity Consumption.

The Digital Twin learns a *global* consumption model from clean training
data and then flags deviations as potential NTL events.

Global baseline model
---------------------
A single Ridge regression is trained on **normalised** consumption from
clean (non-theft) training consumers:

    norm_consumption = consumption_kwh / consumer_mean_kwh

The feature vector uses cyclic encodings of hour, weekday and month so
the model captures the universal shape of electricity demand.

At inference time, each consumer's scale factor (mean consumption) is
estimated from the first ``warmup_days`` of their available readings and
applied to the model's normalised prediction:

    expected_kwh = global_model(hour, weekday, month) × consumer_mean

This design means the twin generalises to *any* consumer, including those
unseen during training, as long as a short warm-up window is available.

Anomaly score
-------------
    deviation = (actual − expected) / expected   (clamped to [−1, 1])

A large negative deviation indicates under-reporting (theft).
A deviation below ``anomaly_threshold`` triggers an NTL alert.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from typing import Optional


class DigitalTwin:
    """
    Global digital twin that models expected normalised consumption.

    Parameters
    ----------
    alpha : float
        Ridge regularisation parameter.
    anomaly_threshold : float
        Deviation (actual − expected) / expected below which an hourly
        reading is flagged as an NTL anomaly.
        Negative value → under-consumption relative to model.
    warmup_days : int
        Number of initial days per consumer used to estimate that
        consumer's mean consumption scale factor at inference time.
    """

    def __init__(
        self,
        alpha: float = 1.0,
        anomaly_threshold: float = -0.40,
        warmup_days: int = 14,
    ) -> None:
        self.alpha = alpha
        self.anomaly_threshold = anomaly_threshold
        self.warmup_days = warmup_days
        self._global_model: Optional[Ridge] = None
        self._global_scaler: Optional[StandardScaler] = None
        self._is_fitted = False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fit(self, df: pd.DataFrame) -> "DigitalTwin":
        """
        Train the global Ridge model on clean training data.

        Parameters
        ----------
        df : pd.DataFrame
            Raw hourly data. Must include: consumer_id, timestamp,
            consumption_kwh, is_theft.  Only rows where is_theft is
            False are used for training.

        Returns
        -------
        self
        """
        clean = df[~df["is_theft"]].copy()

        # Per-consumer mean for normalisation (training consumers only)
        consumer_means = (
            clean.groupby("consumer_id")["consumption_kwh"].mean().replace(0, np.nan)
        )
        clean["norm_consumption"] = (
            clean["consumption_kwh"]
            / clean["consumer_id"].map(consumer_means)
        ).fillna(0.0)

        X, y = self._build_regression_features(clean, target_col="norm_consumption")
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        model = Ridge(alpha=self.alpha)
        model.fit(X_scaled, y)

        self._global_model = model
        self._global_scaler = scaler
        self._is_fitted = True
        return self

    def predict_expected(self, df: pd.DataFrame) -> pd.Series:
        """
        Predict expected consumption for every row in *df*.

        For each consumer the scale factor (mean kWh) is estimated from
        the first ``warmup_days`` of data available in *df*.

        Parameters
        ----------
        df : pd.DataFrame
            Raw hourly data. Must include consumer_id, timestamp, and
            consumption_kwh.

        Returns
        -------
        pd.Series
            Expected consumption in kWh, indexed like *df*.
        """
        if not self._is_fitted:
            raise RuntimeError("DigitalTwin must be fitted before calling predict_expected.")

        warmup_hours = self.warmup_days * 24
        scale_factors: dict[int, float] = {}
        for cid, group in df.groupby("consumer_id"):
            warmup = group.iloc[:warmup_hours]["consumption_kwh"]
            mean_val = warmup.mean()
            scale_factors[cid] = mean_val if mean_val > 0 else 1.0

        X, _ = self._build_regression_features(df)
        X_scaled = self._global_scaler.transform(X)
        norm_pred = self._global_model.predict(X_scaled)

        consumer_scale = df["consumer_id"].map(scale_factors).values
        expected = np.maximum(norm_pred * consumer_scale, 0.0)
        return pd.Series(expected, index=df.index)

    def compute_anomaly_scores(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute per-row deviation scores and hourly NTL flags.

        Parameters
        ----------
        df : pd.DataFrame
            Raw hourly data with consumption_kwh column.

        Returns
        -------
        pd.DataFrame
            Original data with extra columns:
                expected_kwh  – digital twin prediction
                deviation     – (actual - expected) / expected
                ntl_flag      – True when deviation < anomaly_threshold
        """
        result = df.copy()
        result["expected_kwh"] = self.predict_expected(df)
        denom = result["expected_kwh"].replace(0, np.nan)
        result["deviation"] = (result["consumption_kwh"] - result["expected_kwh"]) / denom
        result["deviation"] = result["deviation"].fillna(0.0).clip(-1.0, 1.0)
        result["ntl_flag"] = result["deviation"] < self.anomaly_threshold
        return result

    def score_consumers(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Aggregate hourly anomaly scores to a per-consumer daily NTL score.

        Returns a DataFrame with columns:
            consumer_id, date, ntl_score, ntl_flag
        where ntl_score is the fraction of hours flagged per day.
        """
        scored = self.compute_anomaly_scores(df)
        scored["date"] = scored["timestamp"].dt.date
        agg = (
            scored.groupby(["consumer_id", "date"])
            .agg(
                ntl_score=("ntl_flag", "mean"),
                mean_deviation=("deviation", "mean"),
            )
            .reset_index()
        )
        agg["ntl_flag"] = agg["ntl_score"] >= 0.25  # ≥25 % of hours flagged
        return agg

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_regression_features(
        group: pd.DataFrame,
        target_col: str = "consumption_kwh",
    ) -> tuple[np.ndarray, np.ndarray]:
        """Build (X, y) arrays from a multi-consumer hourly DataFrame."""
        ts = group["timestamp"]
        hour = ts.dt.hour.values
        weekday = ts.dt.dayofweek.values
        month = ts.dt.month.values - 1  # 0-indexed

        # Cyclic encoding of hour (avoids discontinuity at midnight)
        hour_sin = np.sin(2 * np.pi * hour / 24)
        hour_cos = np.cos(2 * np.pi * hour / 24)
        # Cyclic encoding of month
        month_sin = np.sin(2 * np.pi * month / 12)
        month_cos = np.cos(2 * np.pi * month / 12)
        # Weekday as cyclic
        weekday_sin = np.sin(2 * np.pi * weekday / 7)
        weekday_cos = np.cos(2 * np.pi * weekday / 7)

        X = np.column_stack(
            [hour_sin, hour_cos, month_sin, month_cos, weekday_sin, weekday_cos]
        )
        y = group[target_col].values if target_col in group.columns else np.zeros(len(group))
        return X, y
