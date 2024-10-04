import hashlib
import os

import geopandas
from click.testing import CliRunner

from fit_changedetector.cli import cli


def test_compare_pk(tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "compare",
            "tests/data/parks_a.geojson",
            "tests/data/parks_b.geojson",
            "-pk",
            "id",
            "-o",
            str(tmp_path),
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
    for layer in change_counts:
        df = geopandas.read_file(
            os.path.join(tmp_path, "changedetector.gdb"), layer=layer
        )
        assert len(df) == change_counts[layer]


def test_compare_hash(tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "compare",
            "tests/data/parks_a.geojson",
            "tests/data/parks_b.geojson",
            "-hf",
            "park_name",
            "-o",
            str(tmp_path),
        ],
    )
    change_counts = {
        "NEW": 6,
        "DELETED": 6,
        "MODIFIED_ATTR": 1,
    }
    assert result.exit_code == 0
    for layer in change_counts:
        df = geopandas.read_file(
            os.path.join(tmp_path, "changedetector.gdb"), layer=layer
        )
        assert len(df) == change_counts[layer]


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
