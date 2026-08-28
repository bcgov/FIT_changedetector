import json

import geopandas
import pandas
import pytest
from geopandas import GeoDataFrame
from shapely.geometry import Point, Polygon

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


def test_add_hash_key_geom_dups(gdf):
    gdf = GeoDataFrame(
        {
            "col1": [1, 2, 3],
            "col2": ["a", "b", "c"],
            "geometry": [Point(1, 1), Point(1, 1), Point(1, 2)],
        }
    ).set_crs("EPSG:3005")
    with pytest.raises(ValueError):
        gdf = fcd.add_hash_key(gdf, "test_hash")


def test_add_hash_key_hash_dups(gdf):
    gdf = GeoDataFrame(
        {
            "col1": [1, 2, 3],
            "col2": ["a", "a", "c"],
            "geometry": [Point(1, 1), Point(1, 1), Point(1, 2)],
        }
    ).set_crs("EPSG:3005")
    with pytest.raises(ValueError):
        gdf = fcd.add_hash_key(gdf, "test_hash", fields=["col2"])


def test_add_hash_key_allow_dups(gdf):
    gdf = GeoDataFrame(
        {
            "col1": [1, 2, 3],
            "col2": ["a", "a", "c"],
            "geometry": [Point(1, 1), Point(1, 1), Point(1, 2)],
        }
    ).set_crs("EPSG:3005")
    gdf = fcd.add_hash_key(gdf, "test_hash", fields=["col2"], allow_duplicates=True)
    assert len(gdf.drop_duplicates(subset=["test_hash"])) == 2


def test_add_hash_empty():
    df = geopandas.read_file("tests/data/parks_a.geojson")
    with pytest.raises(ValueError):
        df = fcd.add_hash_key(df, "test_hash", fields=[], hash_geometry=False)


def test_invalid_hash_precision():
    df = geopandas.read_file("tests/data/parks_a.geojson")
    with pytest.raises(ValueError):
        df = fcd.add_hash_key(
            df, "test_hash", fields=[], hash_geometry=True, precision=999
        )


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
    diff_low_precision = fcd.gdf_diff(
        df_a, df_b, primary_key="id", return_type="gdf", precision=1
    )["MODIFIED_GEOM"]
    assert len(diff_high_precision) == 2
    assert len(diff_low_precision) == 0


def test_diff_geom_vertex_order_and_winding_not_modified():
    """Vertex order / ring winding differences alone are not flagged as modified.

    gdf_diff normalizes geometries before comparing (see gdf_diff's use of
    .normalize().geom_equals_exact()), so it matches topological equality
    (GeoSeries.geom_equals) rather than raw vertex-order-sensitive equality
    (geom_equals_exact/geom_equals_identical without normalizing first).
    """
    square = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
    rotated_start = Polygon([(10, 0), (10, 10), (0, 10), (0, 0), (10, 0)])
    reversed_winding = Polygon([(0, 10), (10, 10), (10, 0), (0, 0), (0, 10)])

    gs_a = geopandas.GeoSeries([square, square])
    gs_b = geopandas.GeoSeries([rotated_start, reversed_winding])
    # topologically identical regardless of vertex order/winding
    assert list(gs_a.geom_equals(gs_b)) == [True, True]
    # but not structurally/positionally identical without normalizing first
    assert list(gs_a.geom_equals_exact(gs_b, 0)) == [False, False]
    assert list(gs_a.geom_equals_identical(gs_b)) == [False, False]

    df_a = GeoDataFrame({"id": [1, 2], "geometry": [square, square]}, crs="EPSG:3005")
    df_b = GeoDataFrame(
        {"id": [1, 2], "geometry": [rotated_start, reversed_winding]}, crs="EPSG:3005"
    )
    d = fcd.gdf_diff(df_a, df_b, primary_key="id", return_type="gdf")
    assert len(d["UNCHANGED"]) == 2
    assert len(d["MODIFIED_GEOM"]) == 0


def test_diff_geom_extra_vertex_flagged_modified():
    """An added vertex on an existing edge (same shape/area, no topological
    change) is still flagged MODIFIED_GEOM.

    gdf_diff compares with geom_equals_exact (positional, vertex-count
    sensitive), not the topological geom_equals, so a change to the vertex
    list alone is detected even though GeoSeries.geom_equals considers the
    two geometries equal (same point set/shape).
    """
    square = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
    extra_vertex = Polygon([(0, 0), (5, 0), (10, 0), (10, 10), (0, 10), (0, 0)])

    gs_a = geopandas.GeoSeries([square])
    gs_b = geopandas.GeoSeries([extra_vertex])
    # same shape/point-set...
    assert list(gs_a.geom_equals(gs_b)) == [True]
    # ...but not the same vertex list, even after normalizing
    assert list(gs_a.normalize().geom_equals_exact(gs_b.normalize(), 0)) == [False]

    df_a = GeoDataFrame({"id": [1], "geometry": [square]}, crs="EPSG:3005")
    df_b = GeoDataFrame({"id": [1], "geometry": [extra_vertex]}, crs="EPSG:3005")
    d = fcd.gdf_diff(df_a, df_b, primary_key="id", return_type="gdf")
    assert len(d["MODIFIED_GEOM"]) == 1
    assert len(d["UNCHANGED"]) == 0


def test_diff_geom_tiny_shift_within_precision_not_modified():
    """A coordinate shift smaller than the comparison precision is treated as
    unchanged, even though strict equality (geom_equals/geom_equals_identical)
    considers the geometries different.

    geom_equals_exact's numeric tolerance is what gdf_diff relies on for
    float-noise tolerant comparison - geom_equals/geom_equals_identical have
    no such tolerance.
    """
    square = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
    tiny_shift = Polygon([(0, 0), (10, 0.001), (10, 10), (0, 10), (0, 0)])

    gs_a = geopandas.GeoSeries([square])
    gs_b = geopandas.GeoSeries([tiny_shift])
    assert list(gs_a.geom_equals(gs_b)) == [False]
    assert list(gs_a.geom_equals_identical(gs_b)) == [False]
    assert list(gs_a.geom_equals_exact(gs_b, 0.01)) == [True]

    df_a = GeoDataFrame({"id": [1], "geometry": [square]}, crs="EPSG:3005")
    df_b = GeoDataFrame({"id": [1], "geometry": [tiny_shift]}, crs="EPSG:3005")
    d = fcd.gdf_diff(df_a, df_b, primary_key="id", return_type="gdf", precision=0.01)
    assert len(d["UNCHANGED"]) == 1
    assert len(d["MODIFIED_GEOM"]) == 0


def test_nullable_columns(tmp_path):
    """Integer and string columns with nulls should use pandas nullable dtypes."""
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"id": 1, "count": 5, "name": "Alice"},
                "geometry": {"type": "Point", "coordinates": [0, 0]},
            },
            {
                "type": "Feature",
                "properties": {"id": 2, "count": None, "name": None},
                "geometry": {"type": "Point", "coordinates": [1, 1]},
            },
        ],
    }
    path = tmp_path / "nullable.geojson"
    path.write_text(json.dumps(geojson))

    df = geopandas.read_file(str(path))
    # Without fix: null forces integer column to float64
    assert df["count"].dtype == "float64"

    from fit_changedetector.diff import _cast_dtypes

    df = _cast_dtypes(df, str(path))
    # After fix: nullable types, nulls preserved
    assert df["count"].dtype == "Int32"
    assert df["name"].dtype == "string"
    assert pandas.isna(df.loc[df["id"] == 2, "count"].iloc[0])
    assert pandas.isna(df.loc[df["id"] == 2, "name"].iloc[0])


def test_invalid_diff_precision(gdf):
    df_a = gdf.copy()
    df_b = gdf.copy()
    df_b.at[2, "col2"] = "uuu"
    with pytest.raises(ValueError):
        fcd.gdf_diff(df_a, df_b, primary_key="pk", precision=999)
