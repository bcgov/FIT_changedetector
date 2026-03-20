"""Utility helpers shared by plugin dialogs and processing algorithms."""

import shutil
import subprocess
import sys


def check_fit_changedetector():
    """Check how fit_changedetector is available.

    Returns a tuple (mode, detail) where mode is one of:
        'library'   - importable directly (best)
        'cli'       - 'changedetector' executable found on PATH
        'unavailable' - neither found
    """
    try:
        import fit_changedetector  # noqa: F401

        return ("library", fit_changedetector.__version__)
    except ImportError:
        pass

    cli = shutil.which("changedetector")
    if cli:
        try:
            result = subprocess.run([cli, "--version"], capture_output=True, text=True, timeout=5)
            return ("cli", result.stdout.strip())
        except Exception:
            return ("cli", "unknown version")

    return ("unavailable", "")


def run_compare_via_library(params: dict) -> dict:
    """Call fit_changedetector.compare() and return the diff dict."""
    import fit_changedetector as fcd

    return fcd.compare(
        file_a=params["file_a"],
        file_b=params["file_b"],
        layer_a=params.get("layer_a"),
        layer_b=params.get("layer_b"),
        out_file=params["out_file"],
        primary_key=_parse_list(params.get("primary_key")),
        fields=_parse_list(params.get("fields")),
        ignore_fields=_parse_list(params.get("ignore_fields")),
        suffix_a=params.get("suffix_a", "original"),
        suffix_b=params.get("suffix_b", "new"),
        drop_null_geometry=params.get("drop_null_geometry", False),
        crs=params.get("crs") or None,
        hash_key=params.get("hash_key", "fcd_hash_id"),
        hash_fields=_parse_list(params.get("hash_fields")),
        precision=float(params.get("precision", 0.01)),
        dump_inputs=params.get("dump_inputs", False),
    )


def run_compare_via_cli(params: dict) -> subprocess.CompletedProcess:
    """Call the 'changedetector compare' CLI and return the CompletedProcess."""
    cmd = [shutil.which("changedetector") or "changedetector", "compare"]
    cmd += [params["file_a"], params["file_b"]]

    if params.get("layer_a"):
        cmd += ["--layer-a", params["layer_a"]]
    if params.get("layer_b"):
        cmd += ["--layer-b", params["layer_b"]]
    if params.get("out_file"):
        cmd += ["--out-file", params["out_file"]]
    if params.get("primary_key"):
        cmd += ["--primary-key", params["primary_key"]]
    if params.get("fields"):
        cmd += ["--fields", params["fields"]]
    if params.get("ignore_fields"):
        cmd += ["--ignore-fields", params["ignore_fields"]]
    if params.get("hash_key"):
        cmd += ["--hash-key", params["hash_key"]]
    if params.get("hash_fields"):
        cmd += ["--hash-fields", params["hash_fields"]]
    if params.get("precision"):
        cmd += ["--precision", str(params["precision"])]
    if params.get("suffix_a"):
        cmd += ["--suffix-a", params["suffix_a"]]
    if params.get("suffix_b"):
        cmd += ["--suffix-b", params["suffix_b"]]
    if params.get("drop_null_geometry"):
        cmd += ["--drop-null-geometry"]
    if params.get("dump_inputs"):
        cmd += ["--dump-inputs"]
    if params.get("crs"):
        cmd += ["--crs", params["crs"]]

    return subprocess.run(cmd, capture_output=True, text=True)


def run_add_hash_key_via_library(params: dict):
    """Call fit_changedetector.add_hash_key() path through compare wrapper."""
    import geopandas

    import fit_changedetector as fcd

    df = geopandas.read_file(params["in_file"], layer=params.get("in_layer"))
    if params.get("crs"):
        df = df.to_crs(params["crs"])

    df = fcd.add_hash_key(
        df,
        new_field=params.get("hash_key", "fcd_hash_id"),
        fields=_parse_list(params.get("hash_fields")),
        hash_geometry=True,
        precision=float(params.get("precision", 0.01)),
        drop_null_geometry=params.get("drop_null_geometry", False),
    )

    out_layer = params.get("out_layer") or params.get("in_layer") or "output"
    df.to_file(params["out_file"], driver="OpenFileGDB", layer=out_layer)


def run_add_hash_key_via_cli(params: dict) -> subprocess.CompletedProcess:
    """Call the 'changedetector add-hash-key' CLI."""
    cmd = [shutil.which("changedetector") or "changedetector", "add-hash-key"]
    cmd += [params["in_file"], params["out_file"]]

    if params.get("in_layer"):
        cmd += ["--in-layer", params["in_layer"]]
    if params.get("out_layer"):
        cmd += ["--out-layer", params["out_layer"]]
    if params.get("hash_key"):
        cmd += ["--hash-key", params["hash_key"]]
    if params.get("hash_fields"):
        cmd += ["--hash-fields", params["hash_fields"]]
    if params.get("precision"):
        cmd += ["--precision", str(params["precision"])]
    if params.get("crs"):
        cmd += ["--crs", params["crs"]]
    if params.get("drop_null_geometry"):
        cmd += ["--drop-null-geometry"]

    return subprocess.run(cmd, capture_output=True, text=True)


def _parse_list(value) -> list:
    """Convert a comma-separated string to a list, or pass through if already list."""
    if not value:
        return []
    if isinstance(value, list):
        return value
    return [v.strip() for v in value.split(",") if v.strip()]


def python_executable():
    """Return the Python executable for the current environment."""
    return sys.executable
