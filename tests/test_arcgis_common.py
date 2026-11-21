"""Tests for fit_changedetector/arcgis/changedetector_common.py's pure
argument-building logic, and for changedetector_toolvalidator.py's validation
logic.

changedetector_common.py unconditionally `import arcpy`, which only exists
inside ArcGIS Pro's own Python - so it can't be imported normally in this
package's test environment. Stub arcpy out and load the module directly from
its file path instead, so the parts that don't actually touch arcpy (building
the CLI args passed to `changedetector`) get real test coverage.

This is a regression suite for github.com/bcgov/FIT_changedetector/issues/123:
a version of build_common_diff_args() shipped that did
`",".join(param["primary_key"])` on primary_key after it became a plain
string (not a list) - silently comma-joining its individual *characters* into
a garbage --primary-key value. No test caught it because nothing here ran
changedetector_common.py at all.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ARCGIS_DIR = (
    Path(__file__).resolve().parent.parent / "src" / "fit_changedetector" / "arcgis"
)


def _load_changedetector_common():
    sys.modules.setdefault("arcpy", MagicMock())
    spec = importlib.util.spec_from_file_location(
        "changedetector_common", ARCGIS_DIR / "changedetector_common.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cc = _load_changedetector_common()


def _base_param(**overrides):
    """A minimal, fully-populated param dict as build_common_diff_args expects
    it (mirrors what resolve_sources()/GetParameter() would produce), with
    everything optional left empty/None."""
    param = {
        "original_file": "original.gdb",
        "new_file": "new.gdb",
        "original_layer": None,
        "new_layer": None,
        "primary_key": None,
        "fields": [],
        "ignore_fields": [],
        "hash_key": None,
        "hash_fields": [],
        "precision": None,
        "suffix_a": None,
        "suffix_b": None,
        "drop_null_geometry": False,
        "allow_duplicates": False,
    }
    param.update(overrides)
    return param


def test_build_common_diff_args_minimal():
    args = cc.build_common_diff_args(_base_param())
    assert args == ["original.gdb", "new.gdb"]


def test_build_common_diff_args_primary_key_passed_through_as_single_token():
    """Regression test for #123: a single-field primary_key string must reach
    --primary-key as one literal argv token, never comma-split or iterated."""
    args = cc.build_common_diff_args(_base_param(primary_key="WATERBODY_POLY_ID"))
    assert args == ["original.gdb", "new.gdb", "--primary-key", "WATERBODY_POLY_ID"]


def test_build_common_diff_args_primary_key_containing_underscore_not_mangled():
    args = cc.build_common_diff_args(_base_param(primary_key="OBJECTID"))
    pk_index = args.index("--primary-key")
    assert args[pk_index + 1] == "OBJECTID"


def test_build_common_diff_args_fields_and_ignore_fields_comma_joined():
    args = cc.build_common_diff_args(
        _base_param(fields=["a", "b"], ignore_fields=["c", "d"])
    )
    assert "--fields" in args
    assert args[args.index("--fields") + 1] == "a,b"
    assert "--ignore-fields" in args
    assert args[args.index("--ignore-fields") + 1] == "c,d"


def test_build_common_diff_args_hash_fields_translates_geometry_field():
    param = _base_param(
        hash_fields=["Shape", "NAME"],
        original_shape_field="Shape",
        new_shape_field="Shape",
    )
    args = cc.build_common_diff_args(param)
    assert args[args.index("--hash-fields") + 1] == "geometry,NAME"


def test_build_common_diff_args_layers_precision_suffixes_and_flags():
    param = _base_param(
        original_layer="layer_a",
        new_layer="layer_b",
        hash_key="fcd_hash_id",
        precision=0.01,
        suffix_a="orig",
        suffix_b="new",
        drop_null_geometry=True,
        allow_duplicates=True,
    )
    args = cc.build_common_diff_args(param)
    assert args == [
        "original.gdb",
        "new.gdb",
        "--layer-a",
        "layer_a",
        "--layer-b",
        "layer_b",
        "--hash-key",
        "fcd_hash_id",
        "--precision",
        "0.01",
        "--suffix-a",
        "orig",
        "--suffix-b",
        "new",
        "--drop-null-geometry",
        "--allow-duplicates",
    ]


def test_build_common_diff_args_precision_zero_is_not_treated_as_falsy():
    """precision=0 is a valid, meaningful value - must not be dropped by an
    `if param["precision"]:` check (which is why the source checks `is not
    None` instead)."""
    args = cc.build_common_diff_args(_base_param(precision=0))
    assert args[args.index("--precision") + 1] == "0"


def test_translate_hash_fields_no_geometry():
    param = {"hash_fields": ["NAME", "STATUS"]}
    assert cc.translate_hash_fields(param) == ["NAME", "STATUS"]


def test_translate_hash_fields_translates_differently_named_shape_field():
    param = {
        "hash_fields": ["SHAPE", "NAME"],
        "original_shape_field": "Shape",
        "new_shape_field": "GEOMETRY",
    }
    assert cc.translate_hash_fields(param) == ["geometry", "NAME"]


def test_build_verbosity_args():
    assert cc.build_verbosity_args(debug=False) == ["-v"]
    assert cc.build_verbosity_args(debug=True) == ["-v", "-v"]


def test_build_output_stem_uses_out_name_if_given():
    assert cc.build_output_stem("my_output", "changedetector") == "my_output"


def test_build_output_stem_falls_back_to_timestamped_prefix():
    stem = cc.build_output_stem("", "changedetector")
    assert stem.startswith("changedetector_")
    assert len(stem) == len("changedetector_") + len("20260101_0000")


def _install_common_into(monkeypatch, root, interpreter=None):
    """Point cc.__file__ at root/Lib/site-packages/fit_changedetector/arcgis/
    (the Windows venv layout), optionally making root a venv with the given
    interpreter (relative path)."""
    arcgis_dir = root / "Lib" / "site-packages" / "fit_changedetector" / "arcgis"
    arcgis_dir.mkdir(parents=True)
    monkeypatch.setattr(cc, "__file__", str(arcgis_dir / "changedetector_common.py"))
    if interpreter:
        (root / "pyvenv.cfg").write_text("home = C:\\Python314\n")
        (root / interpreter).parent.mkdir(parents=True)
        (root / interpreter).touch()


def test_find_venv_python_windows_venv(monkeypatch, tmp_path):
    _install_common_into(monkeypatch, tmp_path, "Scripts/python.exe")
    assert cc.find_venv_python() == tmp_path / "Scripts" / "python.exe"


def test_find_venv_python_posix_venv(monkeypatch, tmp_path):
    _install_common_into(monkeypatch, tmp_path, "bin/python")
    assert cc.find_venv_python() == tmp_path / "bin" / "python"


def test_find_venv_python_not_in_a_venv(monkeypatch, tmp_path):
    _install_common_into(monkeypatch, tmp_path)
    assert cc.find_venv_python() is None


class _ExecuteError(Exception):
    pass


def test_run_cli_errors_clearly_outside_a_venv(monkeypatch, tmp_path):
    _install_common_into(monkeypatch, tmp_path)
    monkeypatch.setattr(cc.arcpy, "ExecuteError", _ExecuteError)
    monkeypatch.setattr(cc.subprocess, "Popen", MagicMock())
    with pytest.raises(_ExecuteError):
        cc.run_cli("diff", [])
    assert "pyvenv.cfg" in cc.arcpy.AddError.call_args.args[0]
    cc.subprocess.Popen.assert_not_called()


def test_run_cli_runs_venv_python_with_clean_env(monkeypatch, tmp_path):
    _install_common_into(monkeypatch, tmp_path, "Scripts/python.exe")
    monkeypatch.setenv("PYTHONHOME", "C:\\ArcGIS\\Pro\\bin\\Python")
    monkeypatch.setenv("PYTHONPATH", "C:\\ArcGIS\\Pro\\Resources\\ArcPy")
    popen = MagicMock()
    popen.return_value.stdout = iter(["line one\n", "line two\n"])
    popen.return_value.returncode = 0
    monkeypatch.setattr(cc.subprocess, "Popen", popen)

    assert cc.run_cli("diff", ["a.gdb", "b.gdb"]) == ["line one", "line two"]

    args, kwargs = popen.call_args
    assert args[0] == [
        str(tmp_path / "Scripts" / "python.exe"),
        "-u",
        "-m",
        "fit_changedetector",
        "diff",
        "a.gdb",
        "b.gdb",
    ]
    assert "PYTHONHOME" not in kwargs["env"]
    assert "PYTHONPATH" not in kwargs["env"]


def _load_toolvalidator():
    spec = importlib.util.spec_from_file_location(
        "changedetector_toolvalidator", ARCGIS_DIR / "changedetector_toolvalidator.py"
    )
    module = importlib.util.module_from_spec(spec)
    # the validator is pasted into ArcGIS Pro, where arcpy is a builtin, so
    # the file never imports it - provide the stub directly
    module.arcpy = sys.modules["arcpy"]
    spec.loader.exec_module(module)
    return module


def _validator(**values):
    """A ToolValidator whose params are stand-ins with the given values, by
    parameter index (eg p3="id")."""
    validator = _load_toolvalidator().ToolValidator()
    validator.params = [MagicMock(value=None) for _ in range(17)]
    for key, value in values.items():
        validator.params[int(key[1:])].value = value
    return validator


def test_validator_requires_primary_key_or_hash_fields():
    """#130: no Primary Key and no Fields to Include in Hash is flagged on
    both at validation, rather than failing at run time."""
    validator = _validator(p0="a.gdb/fc", p1="b.gdb/fc")
    validator.updateMessages()
    validator.params[3].setErrorMessage.assert_called_once()
    validator.params[4].setErrorMessage.assert_called_once()


def test_validator_primary_key_or_hash_fields_satisfies_requirement():
    for values in ({"p3": "id"}, {"p4": ["NAME"]}):
        validator = _validator(p0="a.gdb/fc", p1="b.gdb/fc", **values)
        validator.updateMessages()
        validator.params[3].setErrorMessage.assert_not_called()
        validator.params[4].setErrorMessage.assert_not_called()


def test_validator_key_requirement_not_flagged_before_sources_chosen():
    validator = _validator(p0="a.gdb/fc")
    validator.updateMessages()
    validator.params[3].setErrorMessage.assert_not_called()
    validator.params[4].setErrorMessage.assert_not_called()
