import geopandas
import pytest

import fit_changedetector as fcd


def test_add_hash_key_geom():
    df = geopandas.read_file("tests/data/test_parks_a.geojson")
    df = fcd.add_hash_key(df, "test_hash")
    assert df["test_hash"].iloc[0] == "fe370ca2e67ae006d003a2448eba4d2797f9ec03"


def test_add_hash_key_geom_columns():
    df = geopandas.read_file("tests/data/test_parks_a.geojson")
    df = fcd.add_hash_key(df, "test_hash", fields=["park_name"])
    assert df["test_hash"].iloc[0] == "4a55cfe9a6b8c0863e0c1c4c18eef7a367fd7f54"


def test_add_hash_empty():
    df = geopandas.read_file("tests/data/test_parks_a.geojson")
    with pytest.raises(ValueError):
        df = fcd.add_hash_key(df, "test_hash", fields=[], hash_geometry=False)


def test_diff():
    # one instance of each type of change is found
    # when comparing these two test files
    df_a = geopandas.read_file("tests/data/test_parks_a.geojson")
    df_b = geopandas.read_file("tests/data/test_parks_b.geojson")
    d = fcd.gdf_diff(df_a, df_b, primary_key="id", return_type="gdf")
    assert len(d["NEW"] == 1)
    assert len(d["DELETED"] == 1)
    assert len(d["UNCHANGED"] == 1)
    assert len(d["MODIFIED_BOTH"] == 1)
    assert len(d["MODIFIED_ATTR"] == 3)
    assert len(d["MODIFIED_GEOM"] == 1)
