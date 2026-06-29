"""
Synthetic Smart Meter Data Generator for NTL Detection.

Generates realistic hourly electricity consumption data for multiple
consumers, with configurable injection of Non-Technical Loss (NTL)
patterns (meter tampering, meter bypass, energy diversion).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Optional


# ---------------------------------------------------------------------------
# Consumption profile helpers
# ---------------------------------------------------------------------------

# Hourly load shape for a residential consumer (index 0-23).
# Values represent relative consumption normalised to peak.
_HOURLY_RESIDENTIAL = np.array(
    [
        0.30, 0.25, 0.22, 0.20, 0.20, 0.22,  # 00-05  night/early morning
        0.35, 0.55, 0.60, 0.50, 0.45, 0.48,  # 06-11  morning ramp
        0.52, 0.50, 0.48, 0.50, 0.60, 0.80,  # 12-17  afternoon
        1.00, 0.95, 0.85, 0.70, 0.55, 0.40,  # 18-23  evening peak
    ],
    dtype=float,
)

# Weekday multiplier (Mon=0 … Sun=6)
_WEEKDAY_MULT = np.array([1.00, 1.00, 1.00, 1.00, 1.05, 1.15, 1.10])

# Monthly seasonality multiplier (Jan=0 … Dec=11)
_MONTHLY_MULT = np.array(
    [1.20, 1.15, 1.05, 0.95, 0.90, 0.88, 0.92, 0.95, 0.98, 1.00, 1.10, 1.18]
)


class SmartMeterDataGenerator:
    """
    Generate synthetic smart-meter readings for NTL research.

    Parameters
    ----------
    n_consumers : int
        Number of electricity consumers to simulate.
    seed : int, optional
        Random seed for reproducibility.
    base_consumption_kwh : float
        Mean peak hourly consumption in kWh per consumer.
    noise_std_fraction : float
        Standard deviation of Gaussian noise as a fraction of the
        expected value at each time step.
    """

    def __init__(
        self,
        n_consumers: int = 50,
        seed: Optional[int] = 42,
        base_consumption_kwh: float = 2.0,
        noise_std_fraction: float = 0.10,
    ) -> None:
        self.n_consumers = n_consumers
        self.seed = seed
        self.base_consumption_kwh = base_consumption_kwh
        self.noise_std_fraction = noise_std_fraction
        self._rng = np.random.default_rng(seed)

        # Per-consumer scale factors (heterogeneous population)
        self._consumer_scales = self._rng.uniform(0.5, 2.0, size=n_consumers)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def generate(
        self,
        start_date: str = "2023-01-01",
        n_days: int = 365,
        theft_rate: float = 0.20,
        theft_types: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        """
        Generate a full dataset of smart-meter readings.

        Parameters
        ----------
        start_date : str
            ISO-format start date for the time series.
        n_days : int
            Number of days to simulate.
        theft_rate : float
            Fraction of consumers that commit NTL (0–1).
        theft_types : list of str, optional
            Subset of {'tampering', 'bypass', 'diversion'} to include.
            Defaults to all three types.

        Returns
        -------
        pd.DataFrame
            Columns: consumer_id, timestamp, consumption_kwh, is_theft,
            theft_type.
        """
        if theft_types is None:
            theft_types = ["tampering", "bypass", "diversion"]

        timestamps = pd.date_range(start_date, periods=n_days * 24, freq="h")
        n_thieves = int(self.n_consumers * theft_rate)
        thief_ids = set(self._rng.choice(self.n_consumers, size=n_thieves, replace=False))

        records: list[pd.DataFrame] = []
        for cid in range(self.n_consumers):
            df = self._generate_consumer(cid, timestamps)
            if cid in thief_ids:
                theft_type = self._rng.choice(theft_types)
                df = self._inject_theft(df, theft_type)
            else:
                df["is_theft"] = False
                df["theft_type"] = "none"
            records.append(df)

        return pd.concat(records, ignore_index=True)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _generate_consumer(
        self, consumer_id: int, timestamps: pd.DatetimeIndex
    ) -> pd.DataFrame:
        """Produce a clean (no-theft) load profile for one consumer."""
        scale = self._consumer_scales[consumer_id]
        n = len(timestamps)

        hourly = _HOURLY_RESIDENTIAL[timestamps.hour]
        weekday = _WEEKDAY_MULT[timestamps.dayofweek]
        monthly = _MONTHLY_MULT[timestamps.month - 1]

        expected = self.base_consumption_kwh * scale * hourly * weekday * monthly
        noise = self._rng.normal(0, self.noise_std_fraction * expected)
        consumption = np.maximum(expected + noise, 0.0)

        return pd.DataFrame(
            {
                "consumer_id": consumer_id,
                "timestamp": timestamps,
                "consumption_kwh": consumption,
            }
        )

    def _inject_theft(self, df: pd.DataFrame, theft_type: str) -> pd.DataFrame:
        """Overlay a NTL pattern onto a clean consumer profile."""
        df = df.copy()
        n = len(df)

        # Theft starts at a random point (after first 10 % of history)
        start_idx = int(n * 0.10) + self._rng.integers(0, int(n * 0.05) + 1)

        theft_mask = np.zeros(n, dtype=bool)
        theft_mask[start_idx:] = True

        if theft_type == "tampering":
            # Meter under-reports: consumption multiplied by factor < 1
            factor = self._rng.uniform(0.30, 0.70)
            df.loc[theft_mask, "consumption_kwh"] *= factor

        elif theft_type == "bypass":
            # Consumer bypasses meter: near-zero readings
            df.loc[theft_mask, "consumption_kwh"] = self._rng.uniform(
                0.0, 0.05, size=theft_mask.sum()
            )

        elif theft_type == "diversion":
            # Intermittent large drops and occasional spikes (irregular)
            idx = np.where(theft_mask)[0]
            drop_idx = idx[self._rng.integers(0, len(idx), size=len(idx) // 3)]
            spike_idx = idx[self._rng.integers(0, len(idx), size=len(idx) // 10)]
            df.iloc[drop_idx, df.columns.get_loc("consumption_kwh")] *= self._rng.uniform(
                0.05, 0.40
            )
            df.iloc[spike_idx, df.columns.get_loc("consumption_kwh")] *= self._rng.uniform(
                1.50, 3.00
            )

        df["is_theft"] = theft_mask
        df["theft_type"] = np.where(theft_mask, theft_type, "none")
        return df
