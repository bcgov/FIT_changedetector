import hashlib
import json
import os

import geopandas
import numpy
from click.testing import CliRunner
from geopandas import GeoDataFrame
from shapely.geometry import MultiPoint, Point

from fit_changedetector.cli import cli


def test_diff2gdb_pk(tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "diff2gdb",
            "tests/data/parks_a.geojson",
            "tests/data/parks_b.geojson",
            "-pk",
            "id",
            "-o",
            str(os.path.join(tmp_path, "test.gdb")),
        ],
    )
    change_counts = {
        "NEW": 1,
        "DELETED": 1,
        "MODIFIED_BOTH": 1,
        "MODIFIED_ATTR": 4,
        "MODIFIED_GEOM": 1,
    }
    assert result.exit_code == 0
    for layer, count in change_counts.items():
        df = geopandas.read_file(os.path.join(tmp_path, "test.gdb"), layer=layer)
        assert len(df) == count


def test_diff_pk(tmp_path, monkeypatch):
    """diff lists the primary key value(s) in each category of change (not
    UNCHANGED - #129), as JSON to stdout, and writes no output file at all."""
    repo_root = os.getcwd()
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "diff",
            os.path.join(repo_root, "tests/data/parks_a.geojson"),
            os.path.join(repo_root, "tests/data/parks_b.geojson"),
            "-pk",
            "id",
        ],
    )
    assert result.exit_code == 0
    assert os.listdir(tmp_path) == []
    assert json.loads(result.output) == {
        "NEW": ["8"],
        "DELETED": ["2"],
        "MODIFIED_BOTH": ["5"],
        "MODIFIED_ATTR": ["3", "6", "7", "9"],
        "MODIFIED_GEOM": ["4"],
    }


def test_diff_pk_out_file(tmp_path):
    """--out-file writes the JSON summary to a file instead of stdout."""
    out_file = os.path.join(tmp_path, "summary.json")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "diff",
            "tests/data/parks_a.geojson",
            "tests/data/parks_b.geojson",
            "-pk",
            "id",
            "-o",
            out_file,
        ],
    )
    assert result.exit_code == 0
    assert result.output == ""
    with open(out_file) as f:
        output = json.load(f)
    assert output["MODIFIED_ATTR"] == ["3", "6", "7", "9"]


def test_diff_pk_count(tmp_path, monkeypatch):
    """--count prints the record count per category of change, instead of
    the primary key values."""
    repo_root = os.getcwd()
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "diff",
            os.path.join(repo_root, "tests/data/parks_a.geojson"),
            os.path.join(repo_root, "tests/data/parks_b.geojson"),
            "-pk",
            "id",
            "--count",
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "NEW": 1,
        "DELETED": 1,
        "MODIFIED_BOTH": 1,
        "MODIFIED_ATTR": 4,
        "MODIFIED_GEOM": 1,
    }


def test_diff_duplicate_primary_key_raises(tmp_path):
    """By default (no --allow-duplicates), a duplicated primary key raises -
    and the output has no DUPLICATES category at all (not even a "0" one),
    since it's dead weight when the feature isn't in use.
    """
    df_a = GeoDataFrame(
        {"id": [1, 1]}, geometry=[Point(0, 0), Point(1, 1)], crs="EPSG:3005"
    )
    df_b = GeoDataFrame({"id": [1]}, geometry=[Point(0, 0)], crs="EPSG:3005")
    path_a = tmp_path / "dupes_a.geojson"
    path_b = tmp_path / "dupes_b.geojson"
    df_a.to_file(path_a, driver="GeoJSON")
    df_b.to_file(path_b, driver="GeoJSON")

    runner = CliRunner()
    result = runner.invoke(cli, ["diff", str(path_a), str(path_b), "-pk", "id"])
    assert result.exit_code != 0
    assert "Duplicate values exist" in str(result.exception)


def test_diff_allow_duplicates(tmp_path):
    """--allow-duplicates drops all but the first occurrence of a duplicated
    primary key instead of raising, and the JSON output gains a DUPLICATES
    category listing the dropped record(s).
    """
    df_a = GeoDataFrame(
        {"id": [1, 1, 2], "name": ["a0", "a1", "a2"]},
        geometry=[Point(0, 0), Point(0, 0), Point(1, 1)],
        crs="EPSG:3005",
    )
    df_b = GeoDataFrame(
        {"id": [1, 2], "name": ["a0", "a2"]},
        geometry=[Point(0, 0), Point(1, 1)],
        crs="EPSG:3005",
    )
    path_a = tmp_path / "dupes_a.geojson"
    path_b = tmp_path / "dupes_b.geojson"
    df_a.to_file(path_a, driver="GeoJSON")
    df_b.to_file(path_b, driver="GeoJSON")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["diff", str(path_a), str(path_b), "-pk", "id", "--allow-duplicates"],
    )
    assert result.exit_code == 0
    assert json.loads(result.output)["DUPLICATES"] == [1]


def test_diff_no_promote_multi(tmp_path):
    """By default a feature stored single-part in one source and multi-part
    in the other is UNCHANGED - --no-promote-multi reports it as MODIFIED_GEOM.
    """
    df_a = GeoDataFrame({"id": [1]}, geometry=[Point(0, 0)], crs="EPSG:3005")
    df_b = GeoDataFrame({"id": [1]}, geometry=[MultiPoint([(0, 0)])], crs="EPSG:3005")
    path_a = tmp_path / "a.geojson"
    path_b = tmp_path / "b.geojson"
    df_a.to_file(path_a, driver="GeoJSON")
    df_b.to_file(path_b, driver="GeoJSON")

    runner = CliRunner()
    args = ["diff", str(path_a), str(path_b), "-pk", "id", "--count"]
    result = runner.invoke(cli, args)
    assert result.exit_code == 0
    assert sum(json.loads(result.output).values()) == 0  # unchanged
    result = runner.invoke(cli, args + ["--no-promote-multi"])
    assert result.exit_code == 0
    assert json.loads(result.output)["MODIFIED_GEOM"] == 1


def test_diff_strict_types(tmp_path):
    """Integer (Int32) vs Integer64 fields are compared by default, and
    rejected with --strict-types."""
    geom = [Point(0, 0)]
    df_a = GeoDataFrame(
        {"id": numpy.array([1], dtype="int32")}, geometry=geom, crs="EPSG:3005"
    )
    df_b = GeoDataFrame(
        {"id": numpy.array([1], dtype="int64")}, geometry=geom, crs="EPSG:3005"
    )
    path_a = tmp_path / "a.gpkg"
    path_b = tmp_path / "b.gpkg"
    df_a.to_file(path_a)
    df_b.to_file(path_b)

    runner = CliRunner()
    args = ["diff", str(path_a), str(path_b), "-pk", "id", "--count"]
    result = runner.invoke(cli, args)
    assert result.exit_code == 0
    assert sum(json.loads(result.output).values()) == 0  # unchanged
    result = runner.invoke(cli, args + ["--strict-types"])
    assert result.exit_code != 0
    assert "Field types do not match" in str(result.exception)


def test_diff2gdb_stdin(tmp_path):
    runner = CliRunner()
    with open("tests/data/parks_a.geojson", "rb") as f:
        stdin_data = f.read()
    result = runner.invoke(
        cli,
        [
            "diff2gdb",
            "-",
            "tests/data/parks_b.geojson",
            "-pk",
            "id",
            "-o",
            str(os.path.join(tmp_path, "test.gdb")),
        ],
        input=stdin_data,
    )
    change_counts = {
        "NEW": 1,
        "DELETED": 1,
        "MODIFIED_BOTH": 1,
        "MODIFIED_ATTR": 4,
        "MODIFIED_GEOM": 1,
    }
    assert result.exit_code == 0
    for layer, count in change_counts.items():
        df = geopandas.read_file(os.path.join(tmp_path, "test.gdb"), layer=layer)
        assert len(df) == count


def test_diff2gdb_stdin_layer_a_not_allowed(tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "diff2gdb",
            "-",
            "tests/data/parks_b.geojson",
            "-pk",
            "id",
            "--layer-a",
            "foo",
            "-o",
            str(os.path.join(tmp_path, "test.gdb")),
        ],
        input=b"",
    )
    assert result.exit_code != 0
    assert "stdin" in str(result.exception)


def _geojson_to_parquet(geojson_path, parquet_path):
    geopandas.read_file(geojson_path).to_parquet(parquet_path)
    return str(parquet_path)


def test_diff2gdb_parquet(tmp_path):
    parquet_a = _geojson_to_parquet(
        "tests/data/parks_a.geojson", tmp_path / "parks_a.parquet"
    )
    parquet_b = _geojson_to_parquet(
        "tests/data/parks_b.geojson", tmp_path / "parks_b.parquet"
    )
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "diff2gdb",
            parquet_a,
            parquet_b,
            "-pk",
            "id",
            "-o",
            str(os.path.join(tmp_path, "test.gdb")),
        ],
    )
    change_counts = {
        "NEW": 1,
        "DELETED": 1,
        "MODIFIED_BOTH": 1,
        "MODIFIED_ATTR": 4,
        "MODIFIED_GEOM": 1,
    }
    assert result.exit_code == 0
    for layer, count in change_counts.items():
        df = geopandas.read_file(os.path.join(tmp_path, "test.gdb"), layer=layer)
        assert len(df) == count


def test_diff2gdb_parquet_mixed_with_geojson(tmp_path):
    # source A as parquet, source B as geojson - exercises the string dtype
    # normalization needed for the two sources' schemas to be considered equivalent
    parquet_a = _geojson_to_parquet(
        "tests/data/parks_a.geojson", tmp_path / "parks_a.parquet"
    )
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "diff2gdb",
            parquet_a,
            "tests/data/parks_b.geojson",
            "-pk",
            "id",
            "-o",
            str(os.path.join(tmp_path, "test.gdb")),
        ],
    )
    assert result.exit_code == 0, result.output
    df = geopandas.read_file(os.path.join(tmp_path, "test.gdb"), layer="MODIFIED_ATTR")
    assert len(df) == 4


def test_diff2gdb_parquet_layer_not_allowed(tmp_path):
    parquet_a = _geojson_to_parquet(
        "tests/data/parks_a.geojson", tmp_path / "parks_a.parquet"
    )
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "diff2gdb",
            parquet_a,
            "tests/data/parks_b.geojson",
            "-pk",
            "id",
            "--layer-a",
            "foo",
            "-o",
            str(os.path.join(tmp_path, "test.gdb")),
        ],
    )
    assert result.exit_code != 0
    assert "parquet" in str(result.exception)


def test_diff2gdb_hash(tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "diff2gdb",
            "tests/data/parks_a.geojson",
            "tests/data/parks_b.geojson",
            "-hf",
            "park_name,geometry",
            "-o",
            str(os.path.join(tmp_path, "test.gdb")),
        ],
    )
    change_counts = {
        "NEW": 6,
        "DELETED": 6,
        "MODIFIED_ATTR": 1,
    }
    assert result.exit_code == 0
    for layer, count in change_counts.items():
        df = geopandas.read_file(os.path.join(tmp_path, "test.gdb"), layer=layer)
        assert len(df) == count


def test_add_hash_key(tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "add-hash-key",
            "tests/data/parks_a.geojson",
            os.path.join(tmp_path, "test.gdb"),
            "-nln",
            "testlayer",
            "-hf",
            "park_name,geometry",
            "-hk",
            "hashed_key",
        ],
    )
    assert result.exit_code == 0
    df = geopandas.read_file(os.path.join(tmp_path, "test.gdb"), layer="testlayer")
    df["geometry_normalized"] = (
        df[df.geometry.name].normalize().set_precision(0.01, mode="pointwise")
    )
    assert "hashed_key" in df.columns
    assert (
        df["hashed_key"].iloc[0]
        == df[["park_name", "geometry_normalized"]]
        .apply(
            lambda x: hashlib.sha1(
                "|".join(x.astype(str).fillna("NULL").values).encode("utf-8")
            ).hexdigest(),
            axis=1,
        )
        .iloc[0]
    )


def test_add_hash_key_requires_hash_fields(tmp_path):
    """--hash-fields is required for add-hash-key - there's no primary key
    concept here, so fields must always be given explicitly (including the
    geometry field's name, to hash on geometry)."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "add-hash-key",
            "tests/data/parks_a.geojson",
            os.path.join(tmp_path, "test.gdb"),
            "-nln",
            "testlayer",
        ],
    )
    assert result.exit_code != 0
    assert "--hash-fields" in result.output


def test_add_hash_key_attrs_only(tmp_path):
    """Omitting the geometry field's name from --hash-fields hashes
    attributes only - see https://github.com/bcgov/FIT_changedetector/issues/120."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "add-hash-key",
            "tests/data/parks_a.geojson",
            os.path.join(tmp_path, "test.gdb"),
            "-nln",
            "testlayer",
            "-hf",
            "park_name",
            "-hk",
            "hashed_key",
        ],
    )
    assert result.exit_code == 0
    df = geopandas.read_file(os.path.join(tmp_path, "test.gdb"), layer="testlayer")
    assert "hashed_key" in df.columns
    assert (
        df["hashed_key"].iloc[0]
        == df[["park_name"]]
        .apply(
            lambda x: hashlib.sha1(
                "|".join(x.astype(str).fillna("NULL").values).encode("utf-8")
            ).hexdigest(),
            axis=1,
        )
        .iloc[0]
    )


def test_diff_no_primary_key_no_hash_fields_raises(tmp_path):
    """No --primary-key and no --hash-fields must raise, rather than
    silently defaulting to a geometry-only hash - fields to hash must now be
    given explicitly (including the geometry field's name, if geometry is to
    be included)."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "diff",
            "tests/data/parks_a.geojson",
            "tests/data/parks_b.geojson",
        ],
    )
    assert result.exit_code != 0
    assert "specify hash_fields" in str(result.exception)


def test_diff_drop_null_geometry_without_geometry_in_hash_raises(tmp_path):
    """--drop-null-geometry is only valid when the geometry field is
    included in --hash-fields."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "diff",
            "tests/data/parks_a.geojson",
            "tests/data/parks_b.geojson",
            "-hf",
            "park_name",
            "-d",
        ],
    )
    assert result.exit_code != 0
    assert "drop_null_geometry has no effect" in str(result.exception)


def test_diff_drop_null_geometry_with_primary_key_raises(tmp_path):
    """--drop-null-geometry has no effect when a --primary-key is supplied -
    an explicit primary key is always used directly, never hashed, so there
    is no hash key generation for the option to affect."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "diff",
            "tests/data/parks_a.geojson",
            "tests/data/parks_b.geojson",
            "-pk",
            "id",
            "-d",
        ],
    )
    assert result.exit_code != 0
    assert "drop_null_geometry has no effect when a primary_key is supplied" in str(
        result.exception
    )


def test_diff_primary_key_is_not_comma_split(tmp_path):
    """--primary-key takes a single field name, not a comma separated list -
    a comma in the value is treated as part of one literal field name
    (composite keys go through --hash-fields instead)."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "diff",
            "tests/data/parks_a.geojson",
            "tests/data/parks_b.geojson",
            "-pk",
            "id,park_name",
        ],
    )
    assert result.exit_code != 0
    assert "Field id,park_name is not present in" in str(result.exception)


def test_diff_missing_field_hints_geometry_name():
    """A misnamed field (eg "Shape"/"SHAPE" from ArcGIS habit) in --hash-fields
    raises with a hint at the dataset's real geometry field name."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "diff",
            "tests/data/parks_a.geojson",
            "tests/data/parks_b.geojson",
            "-hf",
            "park_name,Shape",
        ],
    )
    assert result.exit_code != 0
    assert "Field Shape is not present" in str(result.exception)
    assert "geometry field is named 'geometry'" in str(result.exception)


def test_add_hash_key_missing_field_hints_geometry_name(tmp_path):
    """A misnamed field (eg "Shape"/"SHAPE" from ArcGIS habit) in
    --hash-fields raises with a hint at the dataset's real geometry field
    name."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "add-hash-key",
            "tests/data/parks_a.geojson",
            os.path.join(tmp_path, "test.gdb"),
            "-nln",
            "testlayer",
            "-hf",
            "park_name,Shape",
        ],
    )
    assert result.exit_code != 0
    assert "Field Shape is not present" in str(result.exception)
    assert "geometry field is named 'geometry'" in str(result.exception)


# not yet functional,
# apparently cannot write non spatial tables to .gdb with pyogrio
# def test_compare_non_spatial(tmp_path):
#    runner = CliRunner()
#    result = runner.invoke(
#        cli,
#        [
#            "diff2gdb",
#            "tests/data/pets_1.geojson",
#            "tests/data/pets_2.geojson",
#            "-pk",
#            "id",
#            "-o",
#            str(tmp_path),
#        ],
#    )
#    # assert result.exit_code == 0
