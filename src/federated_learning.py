"""Federated-learning utilities for privacy-preserving grid intelligence.

This module is designed to support the project's proposal while actual utility
data is not yet available. It allows researchers to simulate distributed client
training over non-IID feeder data and to estimate the deployment impact of a
privacy-preserving learning strategy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import pandas as pd


@dataclass
class ClientModelState:
    client_id: str
    local_score: float
    samples: int
    drift_score: float
    weights: Dict[str, float] = field(default_factory=dict)


@dataclass
class FederatedLearningReport:
    global_score: float
    client_scores: List[ClientModelState]
    non_iid_level: float
    convergence_note: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "global_score": self.global_score,
            "non_iid_level": self.non_iid_level,
            "convergence_note": self.convergence_note,
            "client_scores": [
                {
                    "client_id": client.client_id,
                    "local_score": client.local_score,
                    "samples": client.samples,
                    "drift_score": client.drift_score,
                    "weights": client.weights,
                }
                for client in self.client_scores
            ],
        }


@dataclass
class FederatedLearningConfig:
    rounds: int = 5
    client_count: int = 4
    non_iid_level: float = 0.35
    privacy_mode: str = "differential_privacy"
    aggregation: str = "federated_averaging"


class FederatedClient:
    """A lightweight local client model for simulated distributed training."""

    def __init__(self, client_id: str, data: pd.DataFrame):
        self.client_id = client_id
        self.data = data.copy()

    def train_local_model(self, feature_columns: Sequence[str], target_column: str) -> ClientModelState:
        if self.data.empty:
            return ClientModelState(
                client_id=self.client_id,
                local_score=0.0,
                samples=0,
                drift_score=1.0,
                weights={},
            )

        local_features = self.data[list(feature_columns)].copy()
        target = self.data[target_column].copy()

        # Lightweight heuristic: estimate how informative the local data is by measuring the
        # variance of the target and the signal-to-noise ratio of the features.
        target_mean = float(target.mean()) if not target.empty else 0.0
        feature_strength = 0.0
        for col in local_features.columns:
            col_values = pd.to_numeric(local_features[col], errors="coerce").fillna(0.0)
            feature_strength += float(col_values.std(ddof=0) / max(abs(target_mean), 1e-6))

        samples = len(self.data)
        local_score = min(100.0, 50.0 + min(50.0, feature_strength * 15.0))
        drift_score = max(0.0, min(1.0, 0.5 + (samples / max(len(self.data) + 1, 1)) * 0.5))

        weights = {
            column: float(pd.to_numeric(self.data[column], errors="coerce").std(ddof=0))
            for column in feature_columns
            if not self.data[column].empty
        }

        return ClientModelState(
            client_id=self.client_id,
            local_score=float(round(local_score, 2)),
            samples=samples,
            drift_score=float(round(drift_score, 4)),
            weights=weights,
        )


class FederatedAveragingAggregator:
    """Aggregates local client states using a weighted average strategy."""

    def __init__(self, config: Optional[FederatedLearningConfig] = None):
        self.config = config or FederatedLearningConfig()

    def aggregate(self, client_states: Sequence[ClientModelState]) -> FederatedLearningReport:
        if not client_states:
            return FederatedLearningReport(
                global_score=0.0,
                client_scores=[],
                non_iid_level=self.config.non_iid_level,
                convergence_note="No clients were available for aggregation.",
            )

        total_samples = sum(client.samples for client in client_states)
        if total_samples == 0:
            global_score = 0.0
        else:
            weighted_scores = [client.local_score * client.samples for client in client_states]
            global_score = sum(weighted_scores) / total_samples

        non_iid_level = min(1.0, max(0.0, self.config.non_iid_level))
        convergence_note = (
            "Federated aggregation is stable with a moderate non-IID distribution."
            if non_iid_level < 0.6
            else "Federated aggregation may require personalization or client reweighting under high non-IID conditions."
        )

        return FederatedLearningReport(
            global_score=float(round(global_score, 2)),
            client_scores=list(client_states),
            non_iid_level=float(round(non_iid_level, 4)),
            convergence_note=convergence_note,
        )


__all__ = [
    "ClientModelState",
    "FederatedClient",
    "FederatedLearningConfig",
    "FederatedLearningReport",
    "FederatedAveragingAggregator",
]
