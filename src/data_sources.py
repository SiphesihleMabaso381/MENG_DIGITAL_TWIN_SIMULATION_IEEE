"""
Data source adapters for future real-world utility datasets.

This module keeps SCADA, AMI, and GIS inputs separate from the simulation
engine so the current synthetic/benchmark pipeline can continue to run
unchanged. When real utility datasets become available, they can be loaded
through the same interfaces without rewriting the core simulation logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import pandas as pd


@dataclass
class DataSourcePaths:
    """Standard locations for optional utility datasets."""

    scada_csv: Optional[Path] = None
    ami_csv: Optional[Path] = None
    gis_csv: Optional[Path] = None
    metadata: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def default(cls, project_root: Path) -> "DataSourcePaths":
        data_root = project_root / "data" / "inputs"
        return cls(
            scada_csv=data_root / "scada" / "scada.csv",
            ami_csv=data_root / "ami" / "ami.csv",
            gis_csv=data_root / "gis" / "gis.csv",
            metadata={
                "note": "Place real utility datasets in the matching folders when available."
            },
        )


@dataclass
class UtilityDataBundle:
    """Container for optional SCADA, AMI, and GIS datasets."""

    scada: Optional[pd.DataFrame] = None
    ami: Optional[pd.DataFrame] = None
    gis: Optional[pd.DataFrame] = None
    source_paths: Optional[DataSourcePaths] = None

    @property
    def has_any_data(self) -> bool:
        return any(frame is not None and not frame.empty for frame in (self.scada, self.ami, self.gis))


class UtilityDataLoader:
    """Load optional utility datasets if they exist on disk."""

    def __init__(self, paths: DataSourcePaths):
        self.paths = paths

    def load_csv_if_exists(self, path: Optional[Path]) -> Optional[pd.DataFrame]:
        if path is None:
            return None
        if not path.exists():
            return None
        return pd.read_csv(path)

    def load_bundle(self) -> UtilityDataBundle:
        return UtilityDataBundle(
            scada=self.load_csv_if_exists(self.paths.scada_csv),
            ami=self.load_csv_if_exists(self.paths.ami_csv),
            gis=self.load_csv_if_exists(self.paths.gis_csv),
            source_paths=self.paths,
        )


def load_optional_utility_data(project_root: Path) -> UtilityDataBundle:
    """Convenience helper for loading optional real-world datasets."""
    loader = UtilityDataLoader(DataSourcePaths.default(project_root))
    return loader.load_bundle()


__all__ = [
    "DataSourcePaths",
    "UtilityDataBundle",
    "UtilityDataLoader",
    "load_optional_utility_data",
]
