import os

import geopandas
import pytest
from click.testing import CliRunner

# Skip the entire module if tkinter is not installed (e.g. headless server without
# the python3-tk package).  pytest.importorskip must run before any gui import.
pytest.importorskip("tkinter", reason="tkinter not available")

from fit_changedetector.cli import cli  # noqa: E402
from fit_changedetector.gui import (  # noqa: E402
    AddHashKeyTab,
    CompareTab,
    OutputConsole,
    _list_fields,
    _list_layers,
)

# ---------------------------------------------------------------------------
# Helper tests (exercise _list_layers / _list_fields directly)
# ---------------------------------------------------------------------------

PARKS_A = "tests/data/parks_a.geojson"
PARKS_B = "tests/data/parks_b.geojson"
PARKS_LAYER = "parks"
PARKS_FIELDS = ["id", "park_name", "parkclasscode"]


def test_list_layers():
    assert _list_layers(PARKS_A) == [PARKS_LAYER]


def test_list_fields():
    assert _list_fields(PARKS_A, PARKS_LAYER) == PARKS_FIELDS


# ---------------------------------------------------------------------------
# Full GUI integration test
# ---------------------------------------------------------------------------


def test_compare(tmp_path):
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()

    try:
        console = OutputConsole(root)
        tab = CompareTab(root, console)

        path_a = os.path.abspath(PARKS_A)
        path_b = os.path.abspath(PARKS_B)

        # Set file paths and trigger layer + field loading
        tab.file_a.delete(0, tk.END)
        tab.file_a.insert(0, path_a)
        tab._populate_layers(path_a, tab.layer_a)

        tab.file_b.delete(0, tk.END)
        tab.file_b.insert(0, path_b)
        tab._populate_layers(path_b, tab.layer_b)

        # Layers should be auto-selected
        assert tab.layer_a.get() == PARKS_LAYER
        assert tab.layer_b.get() == PARKS_LAYER

        # All four field pickers should have the common fields as choices
        for widget in (tab.primary_key, tab.hash_fields, tab.fields, tab.ignore_fields):
            assert widget._choices == PARKS_FIELDS

        # Set primary key and output folder
        tab.primary_key.entry.insert(0, "id")
        tab.out_file.delete(0, tk.END)
        tab.out_file.insert(0, str(tmp_path))

        # Verify the assembled command
        cmd = tab._build_cmd()
        assert path_a in cmd
        assert path_b in cmd
        assert "-pk" in cmd
        assert "id" in cmd

        # Derive the output .gdb path from the command
        out_path = cmd[cmd.index("-o") + 1]

        # Run the CLI with the same args (strip the leading "changedetector" token)
        runner = CliRunner()
        result = runner.invoke(cli, cmd[1:])
        assert result.exit_code == 0, result.output

        # Verify output change counts
        change_counts = {
            "NEW": 1,
            "DELETED": 1,
            "MODIFIED_BOTH": 1,
            "MODIFIED_ATTR": 4,
            "MODIFIED_GEOM": 1,
        }
        for layer, expected in change_counts.items():
            df = geopandas.read_file(out_path, layer=layer)
            assert len(df) == expected, f"{layer}: expected {expected} rows, got {len(df)}"

    finally:
        root.destroy()


def test_add_hash_key(tmp_path):
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()

    try:
        console = OutputConsole(root)
        tab = AddHashKeyTab(root, console)

        path_in = os.path.abspath(PARKS_A)
        out_path = str(tmp_path / "out.gdb")

        # Set input file and trigger layer + field loading
        tab.in_file.delete(0, tk.END)
        tab.in_file.insert(0, path_in)
        tab._populate_layers(path_in, tab.in_layer)

        # Layer should be auto-selected
        assert tab.in_layer.get() == PARKS_LAYER

        # Hash fields picker should have the available fields as choices
        assert tab.hash_fields._choices == PARKS_FIELDS

        # Set output path
        tab.out_file.delete(0, tk.END)
        tab.out_file.insert(0, out_path)

        # Verify the assembled command
        cmd = tab._build_cmd()
        assert path_in in cmd
        assert out_path in cmd

        # Run the CLI
        runner = CliRunner()
        result = runner.invoke(cli, cmd[1:])
        assert result.exit_code == 0, result.output

        # Verify the output layer contains the expected hash for the first record
        df = geopandas.read_file(out_path)
        assert "fcd_hash_id" in df.columns
        assert df["fcd_hash_id"].iloc[0] == "fe370ca2e67ae006d003a2448eba4d2797f9ec03"

    finally:
        root.destroy()
