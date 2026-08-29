import hashlib
import json
import os

import geopandas
from click.testing import CliRunner

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
    """diff produces the same counts as diff2gdb(), as JSON to stdout, and
    writes no output file at all. By default, also includes a "keys" section
    listing the primary key value(s) present in each category."""
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
    output = json.loads(result.output)
    counts = {k: v for k, v in output.items() if k != "keys"}
    assert counts == {
        "NEW": 1,
        "DELETED": 1,
        "UNCHANGED": 1,
        "MODIFIED_BOTH": 1,
        "MODIFIED_ATTR": 4,
        "MODIFIED_GEOM": 1,
    }
    assert set(output["keys"].keys()) == set(counts.keys())
    for key, count in counts.items():
        assert len(output["keys"][key]) == count


def test_diff_pk_count(tmp_path, monkeypatch):
    """--count omits the "keys" section, printing just the record counts."""
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
    counts = json.loads(result.output)
    assert counts == {
        "NEW": 1,
        "DELETED": 1,
        "UNCHANGED": 1,
        "MODIFIED_BOTH": 1,
        "MODIFIED_ATTR": 4,
        "MODIFIED_GEOM": 1,
    }
    assert "keys" not in counts


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
            "park_name",
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
            "park_name",
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
