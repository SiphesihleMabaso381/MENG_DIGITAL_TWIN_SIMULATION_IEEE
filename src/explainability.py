"""Explainability utilities for operational trust and utility review.

These functions provide a lightweight, deployment-oriented explainability layer
without requiring a heavy external XAI library. The goal is to ensure that every
flagged anomaly can be explained to utility operators in human-understandable terms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Sequence

import numpy as np
import pandas as pd


@dataclass
class FeatureImpact:
    feature: str
    contribution: float
    direction: str


@dataclass
class ExplainabilityReport:
    score: float
    top_features: List[FeatureImpact]
    summary: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "score": self.score,
            "top_features": [
                {
                    "feature": item.feature,
                    "contribution": item.contribution,
                    "direction": item.direction,
                }
                for item in self.top_features
            ],
            "summary": self.summary,
        }


class ExplainabilityEngine:
    """Generate human-readable feature importance and risk explanations."""

    def explain_feature_importance(
        self,
        data: pd.DataFrame,
        target_column: str,
        top_k: int = 5,
    ) -> ExplainabilityReport:
        if data.empty or target_column not in data.columns:
            return ExplainabilityReport(
                score=0.0,
                top_features=[],
                summary="No data available for explainability analysis.",
            )

        numeric_df = data.select_dtypes(include=[np.number]).copy()
        if target_column in numeric_df.columns:
            target = pd.to_numeric(numeric_df[target_column], errors="coerce").fillna(0.0)
            numeric_df = numeric_df.drop(columns=[target_column])
        else:
            return ExplainabilityReport(
                score=0.0,
                top_features=[],
                summary="Target column is not numeric and cannot be used for feature attribution.",
            )

        impacts: List[FeatureImpact] = []
        for feature in numeric_df.columns:
            feature_values = pd.to_numeric(numeric_df[feature], errors="coerce").fillna(0.0)
            if feature_values.std(ddof=0) == 0:
                contribution = 0.0
            else:
                corr = np.corrcoef(feature_values.to_numpy(), target.to_numpy())[0, 1]
                contribution = abs(float(corr)) if np.isfinite(corr) else 0.0
            direction = "positive" if contribution > 0.5 else "neutral"
            impacts.append(FeatureImpact(feature=feature, contribution=float(round(contribution, 4)), direction=direction))

        impacts.sort(key=lambda item: item.contribution, reverse=True)
        top = impacts[:top_k]
        score = float(np.mean([item.contribution for item in top])) * 100.0 if top else 0.0
        summary = (
            "Top contributing features highlight the strongest drivers of anomaly risk; "
            "these are the features to inspect first by utility operators."
        )
        return ExplainabilityReport(score=float(round(score, 2)), top_features=top, summary=summary)

    def explain_anomaly_instance(
        self,
        row: Dict[str, float],
        feature_names: Optional[Sequence[str]] = None,
    ) -> List[FeatureImpact]:
        if not row:
            return []

        feature_names = feature_names or list(row.keys())
        impacts: List[FeatureImpact] = []
        for feature in feature_names:
            value = float(row.get(feature, 0.0))
            contribution = abs(value)
            direction = "positive" if value >= 0 else "negative"
            impacts.append(FeatureImpact(feature=feature, contribution=float(round(contribution, 4)), direction=direction))
        impacts.sort(key=lambda item: item.contribution, reverse=True)
        return impacts


__all__ = [
    "FeatureImpact",
    "ExplainabilityReport",
    "ExplainabilityEngine",
]
