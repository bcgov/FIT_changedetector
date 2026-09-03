import json

import geopandas
import pandas
import pyogrio
import pytest
from geopandas import GeoDataFrame
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    Point,
    Polygon,
)

import fit_changedetector as fcd
from fit_changedetector.changedetector import (
    _read_and_diff,
    _validate_and_prepare_diff_inputs,
)


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


def test_diff_primary_key_and_hash_fields_raises():
    """hash_fields has no effect once a primary_key is supplied - the
    combination is rejected rather than silently ignored."""
    with pytest.raises(
        ValueError, match="has no effect when a primary_key is supplied"
    ):
        fcd.diff_to_json(
            "tests/data/parks_a.geojson",
            "tests/data/parks_b.geojson",
            None,
            None,
            primary_key=["id"],
            hash_fields=["name"],
        )


def test_diff_allow_duplicates_reports_duplicates(gdf):
    """With allow_duplicates, gdf_diff drops all but the first occurrence of a
    duplicated primary key (per source) and returns the dropped records under
    "DUPLICATES", tagged by which source (suffix_a/suffix_b) they came from.
    """
    df_a = gdf.copy()
    df_a.loc[1, "pk"] = df_a.loc[0, "pk"]  # duplicate pk in source a only
    df_b = gdf.copy()
    d = fcd.gdf_diff(
        df_a, df_b, primary_key="pk", return_type="gdf", allow_duplicates=True
    )
    assert len(d["DUPLICATES"]) == 1
    assert d["DUPLICATES"]["pk"].iloc[0] == df_a.loc[0, "pk"]
    assert d["DUPLICATES"]["_fcd_source_"].iloc[0] == "a"


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

    from fit_changedetector.changedetector import _cast_dtypes

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


def _spatial_gdf():
    """A small, valid, CRS-set GeoDataFrame - a base for
    _validate_and_prepare_diff_inputs tests to mutate to break one rule.
    """
    return GeoDataFrame(
        {
            "pk": [1, 2, 3],
            "col1": ["a", "b", "c"],
            "geometry": [Point(0, 0), Point(1, 1), Point(2, 2)],
        },
        crs="EPSG:3005",
    )


def test_validate_diff_inputs_spatial_mismatch():
    df_a = _spatial_gdf()
    df_b = pandas.DataFrame(df_a.drop(columns="geometry"))
    with pytest.raises(TypeError, match="source 1"):
        _validate_and_prepare_diff_inputs(df_a, df_b, "pk", [], [], 0.01)
    with pytest.raises(TypeError, match="source 2"):
        _validate_and_prepare_diff_inputs(df_b, df_a, "pk", [], [], 0.01)


def test_validate_diff_inputs_invalid_precision():
    df_a, df_b = _spatial_gdf(), _spatial_gdf()
    with pytest.raises(ValueError, match="Precision"):
        _validate_and_prepare_diff_inputs(df_a, df_b, "pk", [], [], 999)


def test_validate_diff_inputs_pk_in_ignore_fields():
    df_a, df_b = _spatial_gdf(), _spatial_gdf()
    with pytest.raises(ValueError, match="cannot be used as a primary key"):
        _validate_and_prepare_diff_inputs(df_a, df_b, "pk", [], ["pk"], 0.01)


def test_validate_diff_inputs_pk_missing():
    df_a = _spatial_gdf()
    df_b = _spatial_gdf().rename(columns={"pk": "fid"})
    with pytest.raises(ValueError, match="must be present in both datasets"):
        _validate_and_prepare_diff_inputs(df_a, df_b, "pk", [], [], 0.01)


def test_validate_diff_inputs_fields_not_common():
    df_a, df_b = _spatial_gdf(), _spatial_gdf()
    with pytest.raises(ValueError, match="not common to both datasets"):
        _validate_and_prepare_diff_inputs(
            df_a, df_b, "pk", ["nonexistent_field"], [], 0.01
        )


def test_validate_diff_inputs_dtype_mismatch():
    df_a, df_b = _spatial_gdf(), _spatial_gdf()
    df_b["col1"] = df_b["col1"].astype("string")
    assert df_a["col1"].dtype != df_b["col1"].dtype
    with pytest.raises(ValueError, match="Field types do not match"):
        _validate_and_prepare_diff_inputs(df_a, df_b, "pk", [], [], 0.01)


def test_validate_diff_inputs_geometry_type_mismatch():
    df_a, df_b = _spatial_gdf(), _spatial_gdf()
    df_b.loc[0, "geometry"] = Polygon([(0, 0), (1, 0), (1, 1), (0, 0)])
    with pytest.raises(ValueError, match="not equivalent"):
        _validate_and_prepare_diff_inputs(df_a, df_b, "pk", [], [], 0.01)


def test_validate_diff_inputs_crs_mismatch():
    df_a = _spatial_gdf()
    df_b = _spatial_gdf().to_crs("EPSG:4326")
    with pytest.raises(ValueError, match="Coordinate reference systems"):
        _validate_and_prepare_diff_inputs(df_a, df_b, "pk", [], [], 0.01)


def test_validate_diff_inputs_duplicate_primary_key():
    df_a = _spatial_gdf()
    df_a.loc[1, "pk"] = 1  # now duplicates row 0's pk
    df_b = _spatial_gdf()
    with pytest.raises(ValueError, match="Duplicate values exist"):
        _validate_and_prepare_diff_inputs(df_a, df_b, "pk", [], [], 0.01)


def test_validate_diff_inputs_duplicate_primary_key_allow_duplicates():
    df_a = _spatial_gdf()
    df_a.loc[1, "pk"] = 1  # now duplicates row 0's pk (col1 still "b")
    df_b = _spatial_gdf()
    (
        out_a,
        out_b,
        src_a,
        _src_b,
        _fields,
        _spatial,
        duplicates_a,
        duplicates_b,
    ) = _validate_and_prepare_diff_inputs(
        df_a, df_b, "pk", [], [], 0.01, allow_duplicates=True
    )
    # first occurrence of the duplicated pk (row 0, col1="a") is kept, the
    # second (row 1, col1="b") is dropped, from both the filtered and *_src
    # copies
    assert sorted(out_a["pk"]) == [1, 3]
    assert out_a[out_a["pk"] == 1]["col1"].iloc[0] == "a"
    assert sorted(src_a["pk"]) == [1, 3]
    assert src_a[src_a["pk"] == 1]["col1"].iloc[0] == "a"
    # df_b is untouched
    assert sorted(out_b["pk"]) == [1, 2, 3]
    # the dropped record (row 1, col1="b") is returned separately
    assert len(duplicates_a) == 1
    assert duplicates_a["pk"].iloc[0] == 1
    assert duplicates_a["col1"].iloc[0] == "b"
    assert len(duplicates_b) == 0


def test_validate_diff_inputs_prepares_outputs():
    """Happy-path: check the actual returned values, not just that no error
    was raised - esri area/length fields dropped, geometry column renamed to
    "geometry", fields defaulted to common columns, and *_src copies retain
    the full, unfiltered original schema.
    """
    data = {
        "pk": [1, 2],
        "col1": ["a", "b"],
        "SHAPE_Area": [10.0, 20.0],
        "geom": [Point(0, 0), Point(1, 1)],
    }
    df_a = GeoDataFrame(data, crs="EPSG:3005", geometry="geom")
    df_b = GeoDataFrame(data, crs="EPSG:3005", geometry="geom")

    out_a, _, src_a, src_b, fields, spatial, _, _ = _validate_and_prepare_diff_inputs(
        df_a, df_b, "pk", None, None, 0.01
    )
    assert spatial is True
    assert sorted(fields) == ["col1", "geometry", "pk"]
    assert "SHAPE_Area" not in out_a.columns
    assert out_a.geometry.name == "geometry"
    # source copies retain the full, unfiltered original schema
    assert list(src_a.columns) == ["pk", "col1", "SHAPE_Area", "geom"]
    assert list(src_b.columns) == ["pk", "col1", "SHAPE_Area", "geom"]


def test_validate_diff_inputs_non_spatial_ok():
    df_a = pandas.DataFrame({"pk": [1, 2], "col1": ["a", "b"]})
    df_b = pandas.DataFrame({"pk": [1, 2], "col1": ["a", "b"]})
    _, _, _, _, fields, spatial, _, _ = _validate_and_prepare_diff_inputs(
        df_a, df_b, "pk", None, None, 0.01
    )
    assert spatial is False
    assert sorted(fields) == ["col1", "pk"]


def test_unsupported_geometry_type_rejected(tmp_path):
    """GeometryCollection is not one of the supported geometry types and is
    rejected rather than silently compared. Used here as a stand-in for any
    unsupported type, since shapely has no curve geometry classes to construct
    a real curve-typed fixture with - see _check_geometry_type in
    changedetector.py for why curve types specifically are also rejected.

    https://github.com/bcgov/FIT_changedetector/issues/66
    """
    gdf = GeoDataFrame(
        {"id": [1]},
        geometry=[
            GeometryCollection([Point(0, 0), Polygon([(0, 0), (1, 0), (1, 1), (0, 0)])])
        ],
        crs="EPSG:3005",
    )
    path = tmp_path / "geometrycollection.geojson"
    gdf.to_file(path, driver="GeoJSON")

    with pytest.raises(ValueError, match="GeometryCollection"):
        fcd.diff_to_gdb(
            str(path),
            "tests/data/parks_b.geojson",
            None,
            None,
            str(tmp_path / "out.gdb"),
            primary_key=["id"],
        )


def test_mixed_single_multipart_geometry_type_allowed(tmp_path):
    """A layer mixing single/multipart geometries of the same base type (e.g.
    Point + MultiPoint) reports geometry_type "Unknown" from pyogrio.read_info -
    this is a legitimate, already-supported case (see promote_to_multi) and must
    not be rejected by the unsupported/curve geometry type check.
    """
    points = [Point(0, 0), MultiPoint([(1, 1), (2, 2)])]
    df_a = GeoDataFrame({"id": [1, 2]}, geometry=points, crs="EPSG:3005")
    df_b = GeoDataFrame({"id": [1, 2]}, geometry=points, crs="EPSG:3005")
    path_a = tmp_path / "mixed_a.geojson"
    path_b = tmp_path / "mixed_b.geojson"
    df_a.to_file(path_a, driver="GeoJSON")
    df_b.to_file(path_b, driver="GeoJSON")

    fcd.diff_to_gdb(
        str(path_a),
        str(path_b),
        None,
        None,
        str(tmp_path / "out.gdb"),
        primary_key=["id"],
    )


def test_diff_to_gdb_mixed_multipart_no_primary_key_writes_ok(tmp_path):
    """Regression test for a real-world crash: a source mixing single/multipart
    geometries of the same base type (e.g. a shapefile with mostly LineString
    plus a few MultiLineString features) must not crash diff_to_gdb when no
    primary key is given.

    With no primary key, diff_to_gdb hashes on geometry, which forces
    dump_inputs - writing the (previously unpromoted) source_a/source_b
    layers to .gdb. promote_to_multi was only applied to the internal
    comparison copies inside _validate_and_prepare_diff_inputs, not to these
    dumped layers (nor, for the same reason, to NEW/DELETED/MODIFIED_GEOM,
    which are rebuilt from equally unpromoted df_a_src/df_b_src) - so a real
    mixed-type source hit pyogrio's OpenFileGDB writer with a genuine mix of
    types and failed with "Unsupported geometry type".
    """
    df_a = GeoDataFrame(
        {"id": [1, 2, 3]},
        geometry=[
            LineString([(0, 0), (1, 1)]),
            LineString([(2, 2), (3, 3)]),
            MultiLineString([[(4, 4), (5, 5)]]),
        ],
        crs="EPSG:3005",
    )
    df_b = GeoDataFrame(
        {"id": [1, 2, 3]},
        geometry=[
            LineString([(0, 0), (1, 1)]),  # unchanged
            LineString([(2, 2), (3, 3), (3, 4)]),  # modified -> new hash
            MultiLineString([[(6, 6), (7, 7)]]),  # modified -> new hash
        ],
        crs="EPSG:3005",
    )
    path_a = tmp_path / "mixed_a.geojson"
    path_b = tmp_path / "mixed_b.geojson"
    df_a.to_file(path_a, driver="GeoJSON")
    df_b.to_file(path_b, driver="GeoJSON")

    out_file = str(tmp_path / "out.gdb")
    fcd.diff_to_gdb(str(path_a), str(path_b), None, None, out_file)

    # every layer written must be uniformly promoted to multipart - a real
    # mix of single/multipart types in any written layer is exactly what
    # OpenFileGDB rejects
    for layer in pyogrio.list_layers(out_file)[:, 0]:
        gdf = geopandas.read_file(out_file, layer=layer)
        assert set(gdf.geom_type) <= {"MultiLineString"}


def test_diff_to_gdb_uniform_singlepart_not_promoted(tmp_path):
    """Confirms promotion is opt-in per the mixed-type check: a source with no
    multipart features at all (uniformly single-part in both sources) must
    not be promoted - output geometries stay Point, not MultiPoint.

    (Point/MultiPoint is used rather than LineString/Polygon here because
    OpenFileGDB's Polyline/Polygon feature classes are inherently multipart -
    a uniformly single-part LineString source round-trips as MultiLineString
    through OpenFileGDB regardless of promote_to_multi, so that round trip
    can't distinguish "promoted" from "not promoted". Point vs Multipoint are
    distinct ESRI feature classes, so the round trip is meaningful here.)
    """
    df_a = GeoDataFrame(
        {"id": [1, 2]},
        geometry=[Point(0, 0), Point(2, 2)],
        crs="EPSG:3005",
    )
    df_b = GeoDataFrame(
        {"id": [1, 2]},
        geometry=[
            Point(0, 0),  # unchanged
            Point(3, 3),  # modified -> new hash
        ],
        crs="EPSG:3005",
    )
    path_a = tmp_path / "single_a.geojson"
    path_b = tmp_path / "single_b.geojson"
    df_a.to_file(path_a, driver="GeoJSON")
    df_b.to_file(path_b, driver="GeoJSON")

    out_file = str(tmp_path / "out.gdb")
    fcd.diff_to_gdb(str(path_a), str(path_b), None, None, out_file)

    written_layers = pyogrio.list_layers(out_file)[:, 0]
    assert len(written_layers) > 0
    for layer in written_layers:
        gdf = geopandas.read_file(out_file, layer=layer)
        assert set(gdf.geom_type) <= {"Point"}


def test_diff_to_gdb_duplicate_objectid_dropped(tmp_path):
    """Regression test for a real-world crash: a source with a field literally
    named "objectid" containing duplicate values (a common case - it's often
    just the source's row order, not a stable identifier) must not crash
    diff_to_gdb when no primary key is given.

    GDAL's OpenFileGDB writer auto-maps a field named OBJECTID/FID/OID_
    (case-insensitive) to the layer's actual feature id rather than
    generating its own, so writing any output that retains such a field with
    duplicate values fails with "Cannot create feature of ID <n> because one
    already exists". fcd.id_fields must be dropped everywhere (comparison
    copies, *_src copies, and the dump_inputs source_a/source_b layers), not
    just from the attribute-comparison step.
    """
    df_a = GeoDataFrame(
        {"objectid": [1, 2, 2], "name": ["a1", "a2", "a3"]},
        geometry=[Point(0, 0), Point(1, 1), Point(2, 2)],
        crs="EPSG:3005",
    )
    df_b = GeoDataFrame(
        {"objectid": [1, 2, 2], "name": ["a1", "a2", "b3"]},
        geometry=[Point(0, 0), Point(1, 1), Point(3, 3)],
        crs="EPSG:3005",
    )
    path_a = tmp_path / "dup_objectid_a.geojson"
    path_b = tmp_path / "dup_objectid_b.geojson"
    df_a.to_file(path_a, driver="GeoJSON")
    df_b.to_file(path_b, driver="GeoJSON")

    out_file = str(tmp_path / "out.gdb")
    fcd.diff_to_gdb(str(path_a), str(path_b), None, None, out_file)

    for layer in pyogrio.list_layers(out_file)[:, 0]:
        gdf = geopandas.read_file(out_file, layer=layer)
        assert "objectid" not in [c.lower() for c in gdf.columns]


def test_read_and_diff_id_field_kept_as_explicit_primary_key(tmp_path):
    """A field named OBJECTID/FID/OID_ is only auto-dropped when the caller
    hasn't asked for it - if explicitly used as the primary key (a reasonable
    choice when it happens to be unique in both sources), it must be kept for
    diffing.

    Checked against the in-memory diff (via _read_and_diff directly) rather
    than a written .gdb: ESRI file geodatabases always treat a column named
    OBJECTID as the layer's own row id, never as regular attribute data - so
    even correctly-preserved-for-diffing "objectid" values wouldn't survive a
    write/read round trip as a data column, regardless of this drop/keep
    logic (a driver-level ESRI convention, not something to work around).
    """
    df_a = GeoDataFrame(
        {"objectid": [1, 2], "name": ["a1", "a2"]},
        geometry=[Point(0, 0), Point(1, 1)],
        crs="EPSG:3005",
    )
    df_b = GeoDataFrame(
        {"objectid": [1, 2], "name": ["a1", "b2"]},
        geometry=[Point(0, 0), Point(1, 1)],
        crs="EPSG:3005",
    )
    path_a = tmp_path / "pk_objectid_a.geojson"
    path_b = tmp_path / "pk_objectid_b.geojson"
    df_a.to_file(path_a, driver="GeoJSON")
    df_b.to_file(path_b, driver="GeoJSON")

    diff, _, _, primary_key, _ = _read_and_diff(
        str(path_a),
        str(path_b),
        None,
        None,
        ["objectid"],
        None,
        None,
        "a",
        "b",
        True,
        None,
        "fcd_hash_id",
        None,
        0.01,
    )
    assert primary_key == ["objectid"]
    assert list(diff["MODIFIED_ATTR"]["objectid"]) == [2]


def test_diff_to_gdb_no_primary_key_null_geometry(tmp_path):
    """When no primary key is supplied, diff_to_gdb hashes on geometry to link
    records - a null geometry cannot be hashed, so with the default
    drop_null_geometry=True it must be dropped (with a warning) rather than
    raising, and simply excluded from the diff entirely (not reported under
    any category, in either source).
    """
    df_a = GeoDataFrame(
        {"id": [1, 2, 3], "name": ["a1", "a2", "a3"]},
        geometry=[Point(0, 0), Point(1, 1), None],
        crs="EPSG:3005",
    )
    df_b = GeoDataFrame(
        {"id": [1, 2, 3], "name": ["a1", "a2", "b3"]},
        geometry=[Point(0, 0), None, Point(3, 3)],
        crs="EPSG:3005",
    )
    path_a = tmp_path / "null_geom_a.geojson"
    path_b = tmp_path / "null_geom_b.geojson"
    df_a.to_file(path_a, driver="GeoJSON")
    df_b.to_file(path_b, driver="GeoJSON")

    out_file = str(tmp_path / "out.gdb")
    fcd.diff_to_gdb(
        str(path_a),
        str(path_b),
        None,
        None,
        out_file,
    )
    # df_a's id=2 (Point(1,1)) has no geometry match in df_b -> deleted
    deleted = geopandas.read_file(out_file, layer="DELETED")
    assert list(deleted["id"]) == [2]
    # df_b's id=3 (Point(3,3)) has no geometry match in df_a -> new
    new = geopandas.read_file(out_file, layer="NEW")
    assert list(new["id"]) == [3]
    # id=1 (Point(0,0), unchanged in both) is the only record with a
    # comparable geometry in both sources - diff_to_gdb does not write an
    # UNCHANGED layer at all, and (since id=1 is unchanged) no MODIFIED_*
    # layers either; df_a's id=3 and df_b's id=2 (both null geometry) are
    # dropped entirely rather than appearing anywhere, including the dumped
    # source_a/source_b layers (always written when no primary key is given)
    written_layers = set(pyogrio.list_layers(out_file)[:, 0])
    assert written_layers == {"NEW", "DELETED", "source_a", "source_b"}
    assert sorted(geopandas.read_file(out_file, layer="source_a")["id"]) == [1, 2]
    assert sorted(geopandas.read_file(out_file, layer="source_b")["id"]) == [1, 3]


def test_diff_to_gdb_no_primary_key_null_geometry_not_dropped_raises(tmp_path):
    """With drop_null_geometry=False, a null geometry in either source cannot
    be hashed and must raise rather than being silently dropped or crashing
    on a downstream operation.
    """
    df_a = GeoDataFrame({"id": [1, 2]}, geometry=[Point(0, 0), None], crs="EPSG:3005")
    df_b = GeoDataFrame(
        {"id": [1, 2]}, geometry=[Point(0, 0), Point(1, 1)], crs="EPSG:3005"
    )
    path_a = tmp_path / "null_geom_a.geojson"
    path_b = tmp_path / "null_geom_b.geojson"
    df_a.to_file(path_a, driver="GeoJSON")
    df_b.to_file(path_b, driver="GeoJSON")

    with pytest.raises(ValueError, match="Cannot reliably hash null geometries"):
        fcd.diff_to_gdb(
            str(path_a),
            str(path_b),
            None,
            None,
            str(tmp_path / "out.gdb"),
            drop_null_geometry=False,
        )


def test_diff_to_gdb_allow_duplicates_writes_duplicates_layer(tmp_path):
    """diff_to_gdb(allow_duplicates=True) writes dropped duplicate-primary-key
    records to a DUPLICATES layer in the output .gdb.
    """
    df_a = GeoDataFrame(
        {"id": [1, 1, 2], "name": ["a0", "a1", "a2"]},
        geometry=[Point(0, 0), Point(0, 0), Point(1, 1)],
        crs="EPSG:3005",
    )
    df_b = GeoDataFrame(
        {"id": [1, 2]},
        geometry=[Point(0, 0), Point(1, 1)],
        crs="EPSG:3005",
    )
    path_a = tmp_path / "dupes_a.geojson"
    path_b = tmp_path / "dupes_b.geojson"
    df_a.to_file(path_a, driver="GeoJSON")
    df_b.to_file(path_b, driver="GeoJSON")

    out_file = str(tmp_path / "out.gdb")
    fcd.diff_to_gdb(
        str(path_a),
        str(path_b),
        None,
        None,
        out_file,
        primary_key=["id"],
        allow_duplicates=True,
    )
    duplicates = geopandas.read_file(out_file, layer="DUPLICATES")
    assert len(duplicates) == 1
    assert duplicates["id"].iloc[0] == 1
    assert duplicates["name"].iloc[0] == "a1"
    assert duplicates["_fcd_source_"].iloc[0] == "a"


def test_diff_to_gdb_allow_duplicates_not_applied_to_geometry_only_hash(tmp_path):
    """allow_duplicates does not apply to a pure geometry hash (no primary key,
    no hash_fields): two records sharing a location aren't necessarily
    duplicates - they could be genuinely distinct features that happen to be
    at the same place - so a hash collision here must still raise even with
    allow_duplicates=True, rather than silently discarding one record's
    attributes.
    """
    df_a = GeoDataFrame(
        {"name": ["a0", "a1", "a2"]},
        geometry=[Point(0, 0), Point(0, 0), Point(1, 1)],
        crs="EPSG:3005",
    )
    df_b = GeoDataFrame(
        {"name": ["a0", "a2"]},
        geometry=[Point(0, 0), Point(1, 1)],
        crs="EPSG:3005",
    )
    path_a = tmp_path / "hash_dupes_a.geojson"
    path_b = tmp_path / "hash_dupes_b.geojson"
    df_a.to_file(path_a, driver="GeoJSON")
    df_b.to_file(path_b, driver="GeoJSON")

    with pytest.raises(ValueError, match="Duplicate geometries are present"):
        fcd.diff_to_gdb(
            str(path_a),
            str(path_b),
            None,
            None,
            str(tmp_path / "out.gdb"),
            allow_duplicates=True,
        )


def test_diff_to_gdb_allow_duplicates_hash_with_fields(tmp_path):
    """allow_duplicates does apply to a hash-generated primary key once at
    least one non-geometry field also contributes to the hash (via
    hash_fields) - a match on geometry AND an attribute is a much stronger
    duplicate signal than geometry alone.
    """
    df_a = GeoDataFrame(
        {"cat": ["x", "x", "y"], "name": ["a0", "a1", "a2"]},
        geometry=[Point(0, 0), Point(0, 0), Point(1, 1)],
        crs="EPSG:3005",
    )
    df_b = GeoDataFrame(
        {"cat": ["x", "y"], "name": ["a0", "a2"]},
        geometry=[Point(0, 0), Point(1, 1)],
        crs="EPSG:3005",
    )
    path_a = tmp_path / "hash_dupes_fields_a.geojson"
    path_b = tmp_path / "hash_dupes_fields_b.geojson"
    df_a.to_file(path_a, driver="GeoJSON")
    df_b.to_file(path_b, driver="GeoJSON")

    out_file = str(tmp_path / "out.gdb")
    fcd.diff_to_gdb(
        str(path_a),
        str(path_b),
        None,
        None,
        out_file,
        hash_fields=["cat"],
        allow_duplicates=True,
    )
    duplicates = geopandas.read_file(out_file, layer="DUPLICATES")
    assert len(duplicates) == 1
    assert duplicates["name"].iloc[0] == "a1"
    assert duplicates["_fcd_source_"].iloc[0] == "a"


def test_gdf_diff_single_vs_multipart_same_feature_unchanged():
    """A feature that is single-part in one source and the equivalent
    multi-part in the other must be treated as unchanged, not rejected
    (geometry type mismatch) or spuriously flagged as modified.
    """
    df_a = GeoDataFrame(
        {"id": [1, 2]}, geometry=[Point(0, 0), Point(5, 5)], crs="EPSG:3005"
    )
    df_b = GeoDataFrame(
        {"id": [1, 2]},
        geometry=[MultiPoint([(0, 0)]), Point(5, 5)],
        crs="EPSG:3005",
    )
    d = fcd.gdf_diff(df_a, df_b, primary_key="id")
    assert len(d["UNCHANGED"]) == 2
    assert len(d["MODIFIED_GEOM"]) == 0
    assert len(d["MODIFIED_BOTH"]) == 0
