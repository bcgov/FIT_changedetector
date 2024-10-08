import geopandas
import pytest

import fit_changedetector as fcd


def test_add_hash_key_geom():
    df = geopandas.read_file("tests/data/parks_a.geojson")
    df = fcd.add_hash_key(df, "test_hash")
    assert df["test_hash"].iloc[0] == "fe370ca2e67ae006d003a2448eba4d2797f9ec03"


def test_add_hash_key_geom_columns():
    df = geopandas.read_file("tests/data/parks_a.geojson")
    df = fcd.add_hash_key(df, "test_hash", fields=["park_name"])
    assert df["test_hash"].iloc[0] == "4a55cfe9a6b8c0863e0c1c4c18eef7a367fd7f54"


def test_add_hash_empty():
    df = geopandas.read_file("tests/data/parks_a.geojson")
    with pytest.raises(ValueError):
        df = fcd.add_hash_key(df, "test_hash", fields=[], hash_geometry=False)


def test_diff():
    df_a = geopandas.read_file("tests/data/parks_a.geojson")
    df_b = geopandas.read_file("tests/data/parks_b.geojson")
    d = fcd.gdf_diff(df_a, df_b, primary_key="id", return_type="gdf")
    assert len(d["NEW"] == 1)
    assert len(d["DELETED"] == 1)
    assert len(d["UNCHANGED"] == 1)
    assert len(d["MODIFIED_BOTH"] == 1)
    assert len(d["MODIFIED_ATTR"] == 4)
    assert len(d["MODIFIED_GEOM"] == 1)


def test_diff_non_spatial():
    df_a = geopandas.read_file("tests/data/pets_1.csv")
    df_b = geopandas.read_file("tests/data/pets_2.csv")
    d = fcd.gdf_diff(df_a, df_b, primary_key="id", return_type="gdf")
    assert len(d["NEW"] == 1)
    assert len(d["DELETED"] == 1)
    assert len(d["UNCHANGED"] == 1)
    assert len(d["MODIFIED_ATTR"] == 1)
    assert d["MODIFIED_GEOM"] == []
    assert d["MODIFIED_BOTH"] == []


def test_precision():
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "id": 1,
                    "airport_name": "Heliport",
                    "description": "heliport",
                    "locality": "Victoria",
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [1193726.622830011881888, 381604.069862816773821],
                },
            },
            {
                "type": "Feature",
                "properties": {
                    "id": 2,
                    "airport_name": "Harbour Airport",
                    "description": "water aerodrome",
                    "locality": "Victoria",
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [1194901.506376262987033, 382257.742864987929352],
                },
            },
        ],
    }
    df_a = geopandas.GeoDataFrame.from_features(geojson, crs="EPSG:3005")
    # make a copy and reduce precision of the copy, rounding to nearest .1m
    df_b = df_a.copy()
    df_b["geometry"] = df_b.geometry.set_precision(0.1)
    # compare with .001 precision - every geom changes
    diff_high_precision = fcd.gdf_diff(
        df_a, df_b, primary_key="id", return_type="gdf", precision=0.001
    )["MODIFIED_GEOM"]
    # compare with 1m precision - no changes
    diff_low_precision = fcd.gdf_diff(
        df_a, df_b, primary_key="id", return_type="gdf", precision=1
    )["MODIFIED_GEOM"]
    assert len(diff_high_precision) == 2
    assert len(diff_low_precision) == 0
