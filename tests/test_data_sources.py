from pathlib import Path

import pandas as pd

from src.data_sources import DataSourcePaths, UtilityDataLoader


def test_load_csv_if_exists_returns_none_for_missing_files(tmp_path: Path) -> None:
    paths = DataSourcePaths(ami_csv=tmp_path / "ami.csv")
    loader = UtilityDataLoader(paths)

    assert loader.load_csv_if_exists(paths.ami_csv) is None


def test_load_bundle_reads_available_csv_files(tmp_path: Path) -> None:
    scada_path = tmp_path / "scada.csv"
    ami_path = tmp_path / "ami.csv"
    pd.DataFrame({"value": [1, 2]}).to_csv(scada_path, index=False)
    pd.DataFrame({"value": [3]}).to_csv(ami_path, index=False)

    paths = DataSourcePaths(scada_csv=scada_path, ami_csv=ami_path)
    loader = UtilityDataLoader(paths)
    bundle = loader.load_bundle()

    assert bundle.scada is not None
    assert bundle.ami is not None
    assert bundle.gis is None
    assert bundle.has_any_data is True
