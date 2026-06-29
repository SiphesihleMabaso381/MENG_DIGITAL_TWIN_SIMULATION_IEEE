"""
NTL Detectors for Electricity Theft Detection.

Provides three complementary detection strategies:

1. **Statistical (CUSUM)**
   Cumulative-sum control chart that signals when the running sum of
   deviations from a learned baseline exceeds a control limit.
   Unsupervised – requires no labels for fitting.

2. **Isolation Forest**
   Ensemble anomaly detector that isolates samples by random splits.
   Unsupervised – does not use labels during training.

3. **Random Forest Classifier**
   Supervised binary classifier trained on labelled feature data.
   Requires labelled training data (is_theft column).

All detectors share a common interface:
    fit(X, y=None)  → self
    predict(X)      → np.ndarray of {0, 1}
    predict_proba(X) → np.ndarray of shape (n, 2)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.base import BaseEstimator
from typing import Optional


_FEATURE_COLS = [
    "mean_daily", "std_daily", "min_daily", "max_daily", "total_daily",
    "cv", "peak_offpeak_ratio",
    "weekday", "month", "is_weekend",
    "rolling7_mean", "rolling7_std", "rolling7_min", "rolling7_max",
    "daily_change", "pct_change",
]


class CUSUMDetector:
    """
    CUSUM (Cumulative Sum) control-chart detector.

    Detects persistent downward shifts in daily total consumption
    relative to each consumer's own early-history baseline.

    The detector is self-contained: for each consumer in the input it
    estimates the reference mean and standard deviation from the first
    ``warmup_days`` of daily readings, then runs the lower-sided CUSUM
    on the remaining observations.  This means no cross-consumer
    training data is required and the detector generalises to any
    consumer as long as a warm-up window of clean data exists.

    Parameters
    ----------
    k : float
        Allowance / slack parameter (multiples of baseline std).
    h : float
        Decision interval / threshold (multiples of baseline std).
    warmup_days : int
        Number of initial days per consumer used to estimate the
        reference distribution.
    """

    def __init__(self, k: float = 0.5, h: float = 5.0, warmup_days: int = 30) -> None:
        self.k = k
        self.h = h
        self.warmup_days = warmup_days

    def fit(self, features: pd.DataFrame, y: Optional[pd.Series] = None) -> "CUSUMDetector":
        """No-op: CUSUM uses per-consumer warm-up; fit is a no-op."""
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        """Return binary predictions (1 = NTL detected)."""
        return (self.predict_proba(features)[:, 1] >= 0.5).astype(int)

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        """
        Return probability-like score in [0, 1].

        For each consumer the first ``warmup_days`` days are used as
        the reference baseline.  CUSUM is then run on the remaining
        days and the statistic S_n is mapped to [0, 1] via a sigmoid.
        """
        scores = np.zeros(len(features))

        for cid, grp in features.groupby("consumer_id"):
            totals = grp["total_daily"].values
            n = len(totals)
            warmup = min(self.warmup_days, max(2, n // 3))

            mu = totals[:warmup].mean()
            sigma = totals[:warmup].std()
            if sigma < 1e-6:
                sigma = 1e-6

            S = np.zeros(n)
            for t in range(warmup, n):
                xi = (mu - totals[t]) / sigma  # positive when consumption drops
                S[t] = max(0.0, S[t - 1] + xi - self.k)

            cusum_score = S / (self.h + 1e-9)
            scores[list(grp.index)] = cusum_score

        prob_theft = 1 / (1 + np.exp(-scores + 1.0))  # sigmoid centred at h
        return np.column_stack([1 - prob_theft, prob_theft])


class IsolationForestDetector:
    """
    Anomaly-based NTL detector using Isolation Forest.

    Parameters
    ----------
    contamination : float
        Expected fraction of NTL consumers in the dataset.
    n_estimators : int
        Number of trees in the forest.
    random_state : int, optional
        Random seed.
    """

    def __init__(
        self,
        contamination: float = 0.20,
        n_estimators: int = 100,
        random_state: Optional[int] = 42,
    ) -> None:
        self._model = IsolationForest(
            n_estimators=n_estimators,
            contamination=contamination,
            random_state=random_state,
        )

    def fit(self, features: pd.DataFrame, y: Optional[pd.Series] = None) -> "IsolationForestDetector":
        """Fit the Isolation Forest on feature columns."""
        X = self._get_X(features)
        self._model.fit(X)
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        """Return binary predictions (1 = NTL anomaly)."""
        X = self._get_X(features)
        raw = self._model.predict(X)  # sklearn: -1 anomaly, +1 normal
        return ((raw == -1)).astype(int)

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        """
        Return probability-like score in [0, 1].

        Isolation Forest's decision_function returns higher values for
        normal samples; we invert and normalise.
        """
        X = self._get_X(features)
        scores = self._model.decision_function(X)  # higher → more normal
        # Flip sign so that anomalies have high score, then sigmoid
        prob_theft = 1 / (1 + np.exp(scores * 10))
        return np.column_stack([1 - prob_theft, prob_theft])

    @staticmethod
    def _get_X(features: pd.DataFrame) -> np.ndarray:
        available = [c for c in _FEATURE_COLS if c in features.columns]
        return features[available].values


class RandomForestDetector:
    """
    Supervised NTL detector using a Random Forest classifier.

    Parameters
    ----------
    n_estimators : int
        Number of trees.
    max_depth : int, optional
        Maximum tree depth (None = unlimited).
    class_weight : str or dict
        Passed to RandomForestClassifier to handle class imbalance.
    random_state : int, optional
        Random seed.
    """

    def __init__(
        self,
        n_estimators: int = 200,
        max_depth: Optional[int] = None,
        class_weight: str = "balanced",
        random_state: Optional[int] = 42,
    ) -> None:
        self._model = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            class_weight=class_weight,
            random_state=random_state,
        )
        self._feature_importance: Optional[pd.Series] = None

    def fit(self, features: pd.DataFrame, y: pd.Series) -> "RandomForestDetector":
        """
        Fit the classifier.

        Parameters
        ----------
        features : pd.DataFrame
            Feature matrix from NTLPreprocessor.
        y : pd.Series
            Binary labels (True/1 = NTL).
        """
        X = self._get_X(features)
        self._model.fit(X, y.astype(int))
        available = [c for c in _FEATURE_COLS if c in features.columns]
        self._feature_importance = pd.Series(
            self._model.feature_importances_, index=available
        ).sort_values(ascending=False)
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        """Return binary predictions (1 = NTL)."""
        X = self._get_X(features)
        return self._model.predict(X)

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        """Return class probabilities of shape (n_samples, 2)."""
        X = self._get_X(features)
        return self._model.predict_proba(X)

    @property
    def feature_importance(self) -> Optional[pd.Series]:
        """Feature importance ranking (after fitting)."""
        return self._feature_importance

    @staticmethod
    def _get_X(features: pd.DataFrame) -> np.ndarray:
        available = [c for c in _FEATURE_COLS if c in features.columns]
        return features[available].values


class NTLDetector:
    """
    Unified NTL detector that wraps all three strategies and combines
    their scores via a soft-voting ensemble.

    Parameters
    ----------
    strategy : str
        One of 'ensemble', 'cusum', 'isolation_forest', 'random_forest'.
    contamination : float
        Expected fraction of NTL consumers (used by Isolation Forest).
    random_state : int, optional
        Random seed.
    """

    _STRATEGIES = ("ensemble", "cusum", "isolation_forest", "random_forest")

    def __init__(
        self,
        strategy: str = "ensemble",
        contamination: float = 0.20,
        random_state: Optional[int] = 42,
    ) -> None:
        if strategy not in self._STRATEGIES:
            raise ValueError(
                f"strategy must be one of {self._STRATEGIES}, got '{strategy}'"
            )
        self.strategy = strategy
        self._cusum = CUSUMDetector()
        self._isoforest = IsolationForestDetector(
            contamination=contamination, random_state=random_state
        )
        self._rf = RandomForestDetector(random_state=random_state)
        self._rf_fitted = False

    def fit(
        self, features: pd.DataFrame, y: Optional[pd.Series] = None
    ) -> "NTLDetector":
        """
        Fit the selected detector(s).

        Parameters
        ----------
        features : pd.DataFrame
            Feature matrix from NTLPreprocessor.
        y : pd.Series, optional
            Labels (required when strategy in {'random_forest', 'ensemble'}).
        """
        if self.strategy in ("cusum", "ensemble"):
            self._cusum.fit(features)
        if self.strategy in ("isolation_forest", "ensemble"):
            self._isoforest.fit(features)
        if self.strategy in ("random_forest", "ensemble") and y is not None:
            self._rf.fit(features, y)
            self._rf_fitted = True
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        """Return binary predictions (1 = NTL)."""
        return (self.predict_proba(features) >= 0.5).astype(int)

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        """
        Return theft probability in [0, 1].

        For the ensemble strategy the three models are combined with
        weights (0.20, 0.30, 0.50) for CUSUM, IsoForest, and RF
        respectively.  When RF is not fitted the weights are renormalised
        over the unsupervised models only.
        """
        if self.strategy == "cusum":
            return self._cusum.predict_proba(features)[:, 1]
        if self.strategy == "isolation_forest":
            return self._isoforest.predict_proba(features)[:, 1]
        if self.strategy == "random_forest":
            if not self._rf_fitted:
                raise RuntimeError("Random forest has not been fitted. Provide labels to fit().")
            return self._rf.predict_proba(features)[:, 1]

        # --- ensemble --------------------------------------------------------
        scores = []
        weights: list[float] = []

        p_cusum = self._cusum.predict_proba(features)[:, 1]
        scores.append(p_cusum)
        weights.append(0.20)

        p_iso = self._isoforest.predict_proba(features)[:, 1]
        scores.append(p_iso)
        weights.append(0.30)

        if self._rf_fitted:
            p_rf = self._rf.predict_proba(features)[:, 1]
            scores.append(p_rf)
            weights.append(0.50)

        w = np.array(weights)
        w /= w.sum()
        combined = sum(w_i * s_i for w_i, s_i in zip(w, scores))
        return combined
