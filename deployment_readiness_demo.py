"""Demo script for synthetic deployment-readiness assessment.

This demonstration is intentionally synthetic and designed to show how the project
can score its readiness while real utility data is still pending.
"""

from __future__ import annotations

import pandas as pd

from src.data_quality import DataQualityManager
from src.explainability import ExplainabilityEngine
from src.federated_learning import FederatedAveragingAggregator, FederatedClient, FederatedLearningConfig
from src.physics_informed import FeederPhysicsValidator
from src.deployment_readiness import DeploymentReadinessEvaluator


def run_demo() -> None:
    sample_data = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=24, freq="30min"),
            "energy_kwh": [
                10, 11, 12, 15, 14, 16, 17, 18, 20, 22, 19, 18,
                17, 16, 15, 14, 13, 12, 15, 18, 20, 21, 22, 24,
            ],
            "voltage_v": [230.0] * 24,
            "current_a": [
                10.0, 10.5, 11.0, 12.0, 11.5, 12.2, 13.0, 13.5, 14.0, 15.0,
                14.8, 14.4, 13.5, 13.0, 12.7, 12.3, 12.0, 11.5, 11.8, 12.5, 13.2,
                14.0, 15.2, 16.0,
            ],
            "is_anomaly": [
                0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1,
                0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0,
            ],
        }
    )

    quality = DataQualityManager().clean_and_validate(
        sample_data,
        required_columns=["timestamp", "energy_kwh", "voltage_v", "current_a", "is_anomaly"],
        timestamp_field="timestamp",
    )

    physics = FeederPhysicsValidator().evaluate(
        injected_power_by_node={"node_a": 160.0, "node_b": 140.0, "node_c": -300.0},
        voltage_by_node={"node_a": 230.0, "node_b": 224.0, "node_c": 228.0},
    )

    explainability = ExplainabilityEngine().explain_feature_importance(sample_data, target_column="is_anomaly", top_k=3)

    client_data = [
        sample_data.iloc[:20].copy(),
        sample_data.iloc[20:35].copy(),
        sample_data.iloc[35:].copy(),
    ]
    clients = [FederatedClient(f"client_{idx}", frame) for idx, frame in enumerate(client_data, start=1)]
    client_states = [
        client.train_local_model(["energy_kwh", "voltage_v", "current_a"], "is_anomaly")
        for client in clients
    ]
    federated = FederatedAveragingAggregator(FederatedLearningConfig(rounds=3, client_count=3)).aggregate(client_states)

    report = DeploymentReadinessEvaluator().evaluate(
        data_quality=quality,
        physics=physics,
        explainability=explainability,
        federated=federated,
        benchmark_score=72.0,
    )

    print("Deployment readiness score:", report.readiness_score)
    print(report.summary)
    for check in report.checks:
        print(f"- {check.name}: {check.score} ({check.status})")


if __name__ == "__main__":
    run_demo()
