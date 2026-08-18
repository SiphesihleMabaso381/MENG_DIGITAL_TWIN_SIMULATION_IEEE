"""Operational deployment readiness assessment.

This module bundles the project's future-ready features into a single coherent
readiness score so that the project can be assessed as a research prototype and
as a utility deployment candidate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .data_quality import DataQualityReport
from .explainability import ExplainabilityReport
from .federated_learning import FederatedLearningReport
from .physics_informed import PhysicsCheckResult


@dataclass
class DeploymentReadinessCheck:
    name: str
    status: str
    details: str
    score: float


@dataclass
class DeploymentReadinessReport:
    readiness_score: float
    checks: List[DeploymentReadinessCheck]
    summary: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "readiness_score": self.readiness_score,
            "checks": [
                {
                    "name": check.name,
                    "status": check.status,
                    "details": check.details,
                    "score": check.score,
                }
                for check in self.checks
            ],
            "summary": self.summary,
        }


class DeploymentReadinessEvaluator:
    """Aggregate the synthetic readiness components into a single practical score."""

    def evaluate(
        self,
        data_quality: Optional[DataQualityReport] = None,
        physics: Optional[PhysicsCheckResult] = None,
        explainability: Optional[ExplainabilityReport] = None,
        federated: Optional[FederatedLearningReport] = None,
        benchmark_score: float = 0.0,
    ) -> DeploymentReadinessReport:
        checks: List[DeploymentReadinessCheck] = []

        dq_score = (data_quality.quality_score if data_quality else 0.0)
        checks.append(
            DeploymentReadinessCheck(
                name="data_quality",
                status="ready" if dq_score >= 75 else "needs_attention",
                details="Data-quality checks cover missing values, duplicates, timestamps, and outlier review.",
                score=float(round(dq_score, 2)),
            )
        )

        physics_score = (physics.overall_score if physics else 0.0)
        checks.append(
            DeploymentReadinessCheck(
                name="physics_consistency",
                status="ready" if physics_score >= 75 else "needs_attention",
                details="Physics-informed checks help keep anomaly predictions consistent with feeder feasibility.",
                score=float(round(physics_score, 2)),
            )
        )

        xai_score = (explainability.score if explainability else 0.0)
        checks.append(
            DeploymentReadinessCheck(
                name="explainability",
                status="ready" if xai_score >= 60 else "needs_attention",
                details="Operator-friendly explanations support auditability and trust in decision-making.",
                score=float(round(xai_score, 2)),
            )
        )

        federated_score = (federated.global_score if federated else 0.0)
        checks.append(
            DeploymentReadinessCheck(
                name="federated_learning",
                status="ready" if federated_score >= 65 else "needs_attention",
                details="Federated training ensures privacy-preserving collaboration across grid clients.",
                score=float(round(federated_score, 2)),
            )
        )

        benchmark_score = max(0.0, min(100.0, benchmark_score))
        checks.append(
            DeploymentReadinessCheck(
                name="benchmark_validation",
                status="ready" if benchmark_score >= 70 else "needs_attention",
                details="Benchmark validation compares the framework against centralised and simpler baseline approaches.",
                score=float(round(benchmark_score, 2)),
            )
        )

        readiness_score = (
            dq_score * 0.25
            + physics_score * 0.25
            + xai_score * 0.15
            + federated_score * 0.20
            + benchmark_score * 0.15
        ) / 1.0
        readiness_score = float(round(readiness_score, 2))

        if readiness_score >= 80:
            summary = (
                "The project is approaching utility-grade readiness for a pilot deployment "
                "on a limited feeder set, provided real AMI, SCADA, and GIS data are added."
            )
        elif readiness_score >= 60:
            summary = (
                "The project is a strong synthetic prototype with a realistic future-ready architecture, "
                "but it still requires real-data validation before deployment confidence is high."
            )
        else:
            summary = (
                "The project shows promising research foundations, but the pipeline still needs further "
                "benchmarking, validation, and real-utility integration before deployment confidence is acceptable."
            )

        return DeploymentReadinessReport(
            readiness_score=readiness_score,
            checks=checks,
            summary=summary,
        )


__all__ = [
    "DeploymentReadinessCheck",
    "DeploymentReadinessEvaluator",
    "DeploymentReadinessReport",
]
