"""
Data Preprocessing and Feature Engineering for NTL Detection.

Transforms raw hourly smart-meter readings into a tabular feature
matrix suitable for machine-learning classifiers and anomaly detectors.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from typing import Optional


class NTLPreprocessor:
    """
    Extract features from smart-meter time-series data.

    Features generated per consumer per day
    ----------------------------------------
    Statistical aggregates (daily window):
        mean_daily, std_daily, min_daily, max_daily, total_daily

    Rolling window features (7-day rolling on daily totals):
        rolling7_mean, rolling7_std, rolling7_min, rolling7_max

    Temporal features:
        weekday (0-6), month (1-12), is_weekend

    Ratio features:
        peak_offpeak_ratio  - ratio of mean peak (18-23 h) to mean off-peak (00-05 h)
        cv                  - coefficient of variation (std / mean)

    Change features:
        daily_change        - day-over-day change in total consumption
        pct_change          - percentage change from previous day

    Parameters
    ----------
    scale : bool
        If True, standardise features with zero mean and unit variance.
    """

    _PEAK_HOURS = list(range(18, 24))
    _OFFPEAK_HOURS = list(range(0, 6))

    def __init__(self, scale: bool = True) -> None:
        self.scale = scale
        self._scaler: Optional[StandardScaler] = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Fit the preprocessor and return the feature matrix.

        Parameters
        ----------
        df : pd.DataFrame
            Raw data as returned by SmartMeterDataGenerator.generate().
            Required columns: consumer_id, timestamp, consumption_kwh,
            is_theft.

        Returns
        -------
        pd.DataFrame
            Feature matrix with one row per (consumer_id, date).
            Includes 'is_theft' label column.
        """
        features = self._build_features(df)
        X = features.drop(columns=["is_theft"])
        y = features["is_theft"]

        if self.scale:
            self._scaler = StandardScaler()
            numeric_cols = X.select_dtypes(include=[np.number]).columns.tolist()
            X[numeric_cols] = self._scaler.fit_transform(X[numeric_cols])

        features_scaled = X.copy()
        features_scaled["is_theft"] = y.values
        return features_scaled

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Transform new data using the already-fitted scaler.

        Parameters
        ----------
        df : pd.DataFrame
            Raw data (same schema as fit_transform input).

        Returns
        -------
        pd.DataFrame
            Feature matrix (same schema as fit_transform output).
        """
        features = self._build_features(df)
        X = features.drop(columns=["is_theft"])
        y = features["is_theft"]

        if self.scale and self._scaler is not None:
            numeric_cols = X.select_dtypes(include=[np.number]).columns.tolist()
            X[numeric_cols] = self._scaler.transform(X[numeric_cols])

        features_scaled = X.copy()
        features_scaled["is_theft"] = y.values
        return features_scaled

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute all features; return a per-(consumer, day) DataFrame."""
        df = df.copy()
        df["date"] = df["timestamp"].dt.date
        df["hour"] = df["timestamp"].dt.hour

        # --- daily aggregates -------------------------------------------------
        daily = (
            df.groupby(["consumer_id", "date"])["consumption_kwh"]
            .agg(
                mean_daily="mean",
                std_daily="std",
                min_daily="min",
                max_daily="max",
                total_daily="sum",
            )
            .reset_index()
        )
        daily["std_daily"] = daily["std_daily"].fillna(0.0)

        # Coefficient of variation (safe division)
        daily["cv"] = np.where(
            daily["mean_daily"] > 0,
            daily["std_daily"] / daily["mean_daily"],
            0.0,
        )

        # --- peak / off-peak ratio --------------------------------------------
        peak = (
            df[df["hour"].isin(self._PEAK_HOURS)]
            .groupby(["consumer_id", "date"])["consumption_kwh"]
            .mean()
            .rename("mean_peak")
            .reset_index()
        )
        offpeak = (
            df[df["hour"].isin(self._OFFPEAK_HOURS)]
            .groupby(["consumer_id", "date"])["consumption_kwh"]
            .mean()
            .rename("mean_offpeak")
            .reset_index()
        )
        daily = daily.merge(peak, on=["consumer_id", "date"], how="left")
        daily = daily.merge(offpeak, on=["consumer_id", "date"], how="left")
        daily["peak_offpeak_ratio"] = np.where(
            daily["mean_offpeak"] > 0,
            daily["mean_peak"] / daily["mean_offpeak"],
            daily["mean_peak"],
        )
        daily.drop(columns=["mean_peak", "mean_offpeak"], inplace=True)

        # --- temporal features ------------------------------------------------
        daily["date"] = pd.to_datetime(daily["date"])
        daily["weekday"] = daily["date"].dt.dayofweek
        daily["month"] = daily["date"].dt.month
        daily["is_weekend"] = (daily["weekday"] >= 5).astype(int)

        # --- rolling 7-day features (per consumer) ----------------------------
        daily = daily.sort_values(["consumer_id", "date"])
        for col, agg in [
            ("total_daily", "mean"),
            ("total_daily", "std"),
            ("total_daily", "min"),
            ("total_daily", "max"),
        ]:
            feat_name = f"rolling7_{agg}"
            daily[feat_name] = (
                daily.groupby("consumer_id")["total_daily"]
                .transform(lambda s: s.rolling(7, min_periods=1).agg(agg))
            )
        daily["rolling7_std"] = daily["rolling7_std"].fillna(0.0)

        # --- day-over-day change ----------------------------------------------
        daily["daily_change"] = daily.groupby("consumer_id")["total_daily"].diff()
        daily["pct_change"] = daily.groupby("consumer_id")["total_daily"].pct_change()
        daily["daily_change"] = daily["daily_change"].fillna(0.0)
        daily["pct_change"] = daily["pct_change"].fillna(0.0).replace(
            [np.inf, -np.inf], 0.0
        )

        # --- labels -----------------------------------------------------------
        labels = (
            df.groupby(["consumer_id", "date"])["is_theft"]
            .any()
            .reset_index()
        )
        labels["date"] = pd.to_datetime(labels["date"])
        daily = daily.merge(labels, on=["consumer_id", "date"], how="left")
        daily["is_theft"] = daily["is_theft"].fillna(False)

        feature_cols = [
            "consumer_id", "date",
            "mean_daily", "std_daily", "min_daily", "max_daily", "total_daily",
            "cv", "peak_offpeak_ratio",
            "weekday", "month", "is_weekend",
            "rolling7_mean", "rolling7_std", "rolling7_min", "rolling7_max",
            "daily_change", "pct_change",
            "is_theft",
        ]
        return daily[feature_cols].reset_index(drop=True)
