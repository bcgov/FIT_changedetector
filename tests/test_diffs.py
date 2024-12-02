import geopandas
import pytest
from geopandas import GeoDataFrame
from shapely.geometry import Point
from shapely.geometry.multipoint import MultiPoint

import fit_changedetector as fcd


@pytest.fixture
def gdf():
    return GeoDataFrame(
        {
            "pk": range(10, 13),
            "col1": [100, 300, 500],
            "col2": ["x", "y", "z"],
            "geometry": [Point(x, x) for x in range(3)],
        }
    )


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


def test_invalid_hash_precision():
    df = geopandas.read_file("tests/data/parks_a.geojson")
    with pytest.raises(ValueError):
        df = fcd.add_hash_key(df, "test_hash", fields=[], hash_geometry=True, precision=999)


def test_add_hash_ll(caplog):
    df = geopandas.read_file("tests/data/parks_a.geojson").to_crs("EPSG:4326")
    df = fcd.add_hash_key(df, "test_hash")
    assert (
        "Data is projected in degrees, default precision of 0.01m specified. Adjusting to .0000001 degrees"
        in caplog.text
    )


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


# for modified attr output, retain only columns with changes
def test_diff_modified_columns(gdf):
    df_a = gdf.copy()
    df_b = gdf.copy()
    df_b.at[2, "col2"] = "uuu"
    d = fcd.gdf_diff(df_a, df_b, primary_key="pk", return_type="gdf")
    assert list(d["MODIFIED_ATTR"].columns) == ["pk", "col2_a", "col2_b", "geometry"]
    df_b.at[2, "geometry"] = Point(10, 10)
    d = fcd.gdf_diff(df_a, df_b, primary_key="pk", return_type="gdf")
    assert list(d["MODIFIED_BOTH"].columns) == ["pk", "col2_a", "col2_b", "geometry"]


# check that output schemas match input schemas
def test_diff_source_columns(gdf):
    df_a = gdf.copy()
    df_b = gdf.copy()
    df_b.loc[:, "C"] = df_b.loc[:, "col1"]  # different schema in source b
    d = fcd.gdf_diff(df_a, df_b, primary_key="pk", return_type="gdf")
    # additions - schema b
    assert list(d["NEW"].columns) == list(df_b.columns)
    # deleted - schema a
    assert list(d["DELETED"].columns) == list(df_a.columns)
    # unchanged - schema a
    assert list(d["UNCHANGED"].columns) == list(df_a.columns)
    # modified geometries - schema b
    assert list(d["MODIFIED_GEOM"].columns) == list(df_b.columns)


def test_diff_ignore_columns_default():
    df_a = geopandas.read_file("tests/data/parks_a.geojson").rename(
        columns={"parkclasscode": "Shape_Area"}
    )
    df_b = geopandas.read_file("tests/data/parks_b.geojson").rename(
        columns={"parkclasscode": "Shape_Area"}
    )
    d = fcd.gdf_diff(df_a, df_b, primary_key="id", return_type="gdf", suffix_a="a")
    assert "Shape_Area_a" not in d["MODIFIED_BOTH"].columns
    assert "Shape_Area_a" not in d["MODIFIED_ATTR"].columns


def test_diff_ignore_columns(gdf):
    df_a = gdf.copy()
    df_b = gdf.copy()
    df_b.at[2, "col2"] = "uuu"
    d = fcd.gdf_diff(
        df_a,
        df_b,
        primary_key="pk",
        return_type="gdf",
        suffix_a="a",
        ignore_fields=["col2"],
    )
    assert "col2" not in d["MODIFIED_ATTR"].columns


def test_diff_mixed_geom_types(gdf):
    df_a = gdf.copy()
    df_b = gdf.copy()
    df_a.at[0, "geometry"] = MultiPoint([df_a.at[0, "geometry"]])
    d = fcd.gdf_diff(
        df_a,
        df_b,
        primary_key="pk",
        return_type="gdf",
        suffix_a="a",
    )
    assert (
        len(d["UNCHANGED"].geom_type.unique()) == 1
        and d["UNCHANGED"].geom_type.unique()[0].upper() == "MULTIPOINT"
    )


def test_diff_ignore_pk(gdf):
    df_a = gdf.copy()
    df_b = gdf.copy()
    df_a = df_a.rename(columns={"pk": "fid"})
    df_b = df_b.rename(columns={"pk": "fid"})
    df_b.at[2, "col2"] = "uuu"
    with pytest.raises(ValueError):
        fcd.gdf_diff(
            df_a,
            df_b,
            primary_key="fid",
            return_type="gdf",
            suffix_a="a",
            ignore_fields=["fid"],
        )


def test_diff_non_spatial():
    df_a = geopandas.read_file("tests/data/pets_1.csv")
    df_b = geopandas.read_file("tests/data/pets_2.csv")
    d = fcd.gdf_diff(df_a, df_b, primary_key="id", return_type="gdf")
    assert len(d["NEW"] == 1)
    assert len(d["DELETED"] == 1)
    assert len(d["UNCHANGED"] == 1)
    assert len(d["MODIFIED_ATTR"] == 1)
    assert d["MODIFIED_GEOM"].empty
    assert d["MODIFIED_BOTH"].empty


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
    diff_low_precision = fcd.gdf_diff(df_a, df_b, primary_key="id", return_type="gdf", precision=1)[
        "MODIFIED_GEOM"
    ]
    assert len(diff_high_precision) == 2
    assert len(diff_low_precision) == 0


def test_invalid_diff_precision(gdf):
    df_a = gdf.copy()
    df_b = gdf.copy()
    df_b.at[2, "col2"] = "uuu"
    with pytest.raises(ValueError):
        fcd.gdf_diff(df_a, df_b, primary_key="pk", precision=999)
