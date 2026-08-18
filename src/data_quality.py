"""Utility data-quality validation and preprocessing utilities.

This module gives the project a realistic data-quality layer before the real
utility data arrives. It handles missing values, duplicate records, time-series
alignment, outlier detection, and a simple quality score that can be used to
estimate how close the data is to deployment-ready conditions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd


@dataclass
class DataQualityIssue:
    category: str
    severity: str
    message: str
    value: Optional[float] = None


@dataclass
class DataQualityReport:
    quality_score: float
    missing_rate: float
    duplicate_rate: float
    outlier_rate: float
    timestamp_alignment_score: float
    cleaned: pd.DataFrame
    issues: List[DataQualityIssue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "quality_score": self.quality_score,
            "missing_rate": self.missing_rate,
            "duplicate_rate": self.duplicate_rate,
            "outlier_rate": self.outlier_rate,
            "timestamp_alignment_score": self.timestamp_alignment_score,
            "issues": [
                {
                    "category": issue.category,
                    "severity": issue.severity,
                    "message": issue.message,
                    "value": issue.value,
                }
                for issue in self.issues
            ],
        }


class DataQualityManager:
    """Validate, clean, and score utility time-series and tabular data."""

    def __init__(self, timestamp_field: str = "timestamp"):
        self.timestamp_field = timestamp_field

    def assess_dataframe(
        self,
        data: pd.DataFrame,
        required_columns: Optional[Sequence[str]] = None,
        timestamp_field: Optional[str] = None,
    ) -> DataQualityReport:
        timestamp_field = timestamp_field or self.timestamp_field
        issues: List[DataQualityIssue] = []
        working = data.copy()

        if working.empty:
            issues.append(
                DataQualityIssue(
                    "empty_data",
                    "critical",
                    "Data frame is empty; cannot assess quality or deploy model.",
                    0.0,
                )
            )
            return DataQualityReport(
                quality_score=0.0,
                missing_rate=1.0,
                duplicate_rate=1.0,
                outlier_rate=1.0,
                timestamp_alignment_score=0.0,
                cleaned=working,
                issues=issues,
            )

        if required_columns:
            missing = [col for col in required_columns if col not in working.columns]
            if missing:
                for col in missing:
                    issues.append(
                        DataQualityIssue(
                            "missing_required_column",
                            "critical",
                            f"Required column '{col}' is missing from the dataset.",
                            None,
                        )
                    )

        # Duplicate rows.
        duplicate_rate = float(working.duplicated().mean()) if len(working) else 0.0
        if duplicate_rate > 0:
            issues.append(
                DataQualityIssue(
                    "duplicate_rows",
                    "warning",
                    "Duplicate rows detected. These should be removed before modeling.",
                    duplicate_rate,
                )
            )
        working = working.drop_duplicates().copy()

        # Missing values.
        missing_values = working.isna().sum().sum()
        total_cells = float(working.size)
        missing_rate = (missing_values / total_cells) if total_cells > 0 else 0.0
        if missing_rate > 0:
            issues.append(
                DataQualityIssue(
                    "missing_values",
                    "warning",
                    "Missing values detected; imputation or filtering is required.",
                    missing_rate,
                )
            )

        # Timestamp alignment.
        timestamp_score = 1.0
        if timestamp_field in working.columns:
            try:
                working[timestamp_field] = pd.to_datetime(working[timestamp_field], errors="coerce")
                bad_timestamps = working[timestamp_field].isna().sum()
                if bad_timestamps:
                    issues.append(
                        DataQualityIssue(
                            "invalid_timestamps",
                            "warning",
                            "Some timestamps are invalid or unparseable. They were coerced to NaT.",
                            float(bad_timestamps / len(working)),
                        )
                    )
                    timestamp_score -= min(0.5, float(bad_timestamps / max(len(working), 1)))
                if working[timestamp_field].notna().sum() > 1:
                    sorted_series = working[timestamp_field].dropna().sort_values()
                    if len(sorted_series) > 1:
                        diffs = sorted_series.diff().dropna()
                        if not diffs.empty:
                            zero_or_negative = float((diffs <= pd.Timedelta(0)).mean())
                            if zero_or_negative > 0:
                                timestamp_score -= min(0.3, zero_or_negative)
                                issues.append(
                                    DataQualityIssue(
                                        "non_monotonic_timestamps",
                                        "warning",
                                        "Timestamps are not fully monotonic. Temporal alignment is required.",
                                        zero_or_negative,
                                    )
                                )
                working = working.sort_values(timestamp_field).drop_duplicates(subset=[timestamp_field]).copy()
            except Exception as exc:  # pragma: no cover - defensive branch
                issues.append(
                    DataQualityIssue(
                        "timestamp_parse_error",
                        "warning",
                        f"Timestamp parsing failed: {exc}",
                        None,
                    )
                )
                timestamp_score = 0.0
        else:
            issues.append(
                DataQualityIssue(
                    "missing_timestamp_column",
                    "warning",
                    "No timestamp column was provided; temporal integrity checks could not run.",
                    None,
                )
            )
            timestamp_score = 0.0

        # Numeric outlier detection.
        numeric_cols = working.select_dtypes(include=[np.number]).columns.tolist()
        outlier_rate = 0.0
        if numeric_cols:
            outlier_hits = 0
            total_numeric_cells = 0
            for col in numeric_cols:
                series = pd.to_numeric(working[col], errors="coerce")
                q1 = series.quantile(0.25)
                q3 = series.quantile(0.75)
                iqr = q3 - q1
                lower = q1 - 1.5 * iqr
                upper = q3 + 1.5 * iqr
                total_numeric_cells += len(series)
                outlier_hits += int(((series < lower) | (series > upper)).sum())
            outlier_rate = float(outlier_hits / max(total_numeric_cells, 1))
        if outlier_rate > 0:
            issues.append(
                DataQualityIssue(
                    "outliers_detected",
                    "warning",
                    "Outliers were detected in numeric fields. Review before production deployment.",
                    outlier_rate,
                )
            )

        # Final cleaning actions.
        cleaned = working.copy()
        for col in cleaned.columns:
            if pd.api.types.is_numeric_dtype(cleaned[col]):
                cleaned[col] = cleaned[col].fillna(cleaned[col].median())
            else:
                cleaned[col] = cleaned[col].ffill().bfill()

        quality_score = 100.0
        quality_score -= missing_rate * 100.0 * 0.6
        quality_score -= duplicate_rate * 100.0 * 0.3
        quality_score -= outlier_rate * 100.0 * 0.3
        quality_score -= (1.0 - timestamp_score) * 100.0 * 0.4
        quality_score = max(0.0, min(100.0, quality_score))

        return DataQualityReport(
            quality_score=float(round(quality_score, 2)),
            missing_rate=float(round(missing_rate, 4)),
            duplicate_rate=float(round(duplicate_rate, 4)),
            outlier_rate=float(round(outlier_rate, 4)),
            timestamp_alignment_score=float(round(timestamp_score, 4)),
            cleaned=cleaned,
            issues=issues,
        )

    def clean_and_validate(
        self,
        data: pd.DataFrame,
        required_columns: Optional[Sequence[str]] = None,
        timestamp_field: Optional[str] = None,
    ) -> DataQualityReport:
        """Convenience wrapper returning cleaned data and a well-structured score."""
        return self.assess_dataframe(data, required_columns=required_columns, timestamp_field=timestamp_field)


__all__ = [
    "DataQualityIssue",
    "DataQualityReport",
    "DataQualityManager",
]
