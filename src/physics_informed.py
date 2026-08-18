"""Physics-informed grid checks for utility-grade anomaly detection.

The project currently uses synthetic benchmark data. This module adds a practical
physics-aware validation layer that checks whether anomaly predictions remain
consistent with basic electrical priors such as power conservation and voltage
reasonableness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np


@dataclass
class PhysicsCheckResult:
    kcl_residual: float
    voltage_feasibility: float
    overall_score: float
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "kcl_residual": self.kcl_residual,
            "voltage_feasibility": self.voltage_feasibility,
            "overall_score": self.overall_score,
            "notes": self.notes,
        }


class FeederPhysicsValidator:
    """Checks basic feeder plausibility using simple energy-balance logic."""

    def __init__(
        self,
        nominal_voltage: float = 230.0,
        max_voltage_drop_pct: float = 10.0,
        max_current_imbalance_pct: float = 15.0,
    ):
        self.nominal_voltage = nominal_voltage
        self.max_voltage_drop_pct = max_voltage_drop_pct
        self.max_current_imbalance_pct = max_current_imbalance_pct

    def _compute_kcl_residual(self, injected_power_by_node: Dict[str, float]) -> float:
        if not injected_power_by_node:
            return 0.0
        total_injected = float(sum(abs(v) for v in injected_power_by_node.values()))
        if total_injected == 0:
            return 0.0
        # A simple residual score: if the total net power is too large relative to the
        # source model, the network is physically unrealistic.
        net_power = float(sum(injected_power_by_node.values()))
        residual = abs(net_power) / total_injected
        return float(min(max(residual, 0.0), 1.0))

    def _compute_voltage_feasibility(self, voltage_by_node: Dict[str, float]) -> float:
        if not voltage_by_node:
            return 1.0
        values = np.array([abs(v) for v in voltage_by_node.values()], dtype=float)
        min_voltage = float(np.min(values)) if values.size else self.nominal_voltage
        drop_pct = 100.0 * (1.0 - (min_voltage / self.nominal_voltage))
        if drop_pct < 0:
            drop_pct = 0.0
        feasibility = max(0.0, 1.0 - (drop_pct / self.max_voltage_drop_pct))
        return float(min(max(feasibility, 0.0), 1.0))

    def evaluate(
        self,
        injected_power_by_node: Optional[Dict[str, float]] = None,
        voltage_by_node: Optional[Dict[str, float]] = None,
    ) -> PhysicsCheckResult:
        injected_power_by_node = injected_power_by_node or {}
        voltage_by_node = voltage_by_node or {}

        kcl_residual = self._compute_kcl_residual(injected_power_by_node)
        voltage_feasibility = self._compute_voltage_feasibility(voltage_by_node)

        # A practical score: the model is more realistic when both power balance and voltage
        # feasibility remain within acceptable bounds.
        overall_score = 100.0 * (0.6 * (1.0 - kcl_residual) + 0.4 * voltage_feasibility)
        overall_score = float(min(max(overall_score, 0.0), 100.0))

        notes = []
        if kcl_residual > 0.25:
            notes.append("Power-balance residual is elevated; review feeder-level consistency.")
        if voltage_feasibility < 0.8:
            notes.append("Voltage feasibility is weak; possible feeder stress or topology mismatch.")
        if not notes:
            notes.append("Feeder physics appears within acceptable sanity bounds.")

        return PhysicsCheckResult(
            kcl_residual=float(round(kcl_residual, 4)),
            voltage_feasibility=float(round(voltage_feasibility, 4)),
            overall_score=float(round(overall_score, 2)),
            notes=notes,
        )

    def apply_constraints(
        self,
        predicted_values: Dict[str, float],
        lower_bound: float = 0.0,
        upper_bound: float = 1e9,
    ) -> Dict[str, float]:
        """Clip predictions to physically plausible ranges for deployment usage."""
        corrected = {}
        for key, value in predicted_values.items():
            corrected[key] = float(min(max(value, lower_bound), upper_bound))
        return corrected


__all__ = [
    "FeederPhysicsValidator",
    "PhysicsCheckResult",
]
