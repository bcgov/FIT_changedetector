"""Shared logic for the ArcGIS Pro script tools (changedetector_diff2gdb.py,
changedetector_diff2json.py).

Runs under ArcGIS Pro's own Python (which has arcpy but not fit_changedetector
or its dependencies), so this module is stdlib + arcpy only. It's imported by
the entry-point scripts as a plain sibling module - ArcGIS Pro adds a script
tool's own directory to sys.path.

These scripts ship inside the fit_changedetector package, and a tool's
Script File points at the copy installed in a venv's site-packages. The CLI
then runs as a subprocess using that same venv's Python (see
find_venv_python()), so the scripts always run the CLI version they were
installed with.
"""

import logging
import os
import pprint
import subprocess
from datetime import datetime
from pathlib import Path

import arcpy


def find_venv_python():
    """Path to the Python of the venv this script is installed in, or None.

    Walks up from this file to the first directory holding a pyvenv.cfg (the
    venv root - eg <venv>/Lib/site-packages/fit_changedetector/arcgis/ ->
    <venv>), then returns its interpreter: Scripts/python.exe on Windows,
    bin/python elsewhere. None if this file isn't inside a venv, eg when run
    straight from a repo checkout.

    Uses abspath rather than resolve(): on Windows resolve() turns a mapped
    drive path (P:\\...) into its UNC equivalent, and the interpreter should
    be called by the same path the tool's Script File uses.
    """
    here = Path(os.path.abspath(__file__)).parent
    for parent in [here, *here.parents]:
        if (parent / "pyvenv.cfg").is_file():
            for interpreter in ("Scripts/python.exe", "bin/python"):
                if (parent / interpreter).is_file():
                    return parent / interpreter
            return None
    return None


# use a logger scoped to fit_changedetector.arcgis (not the root logger) so
# our handlers don't intercept log records from unrelated code sharing this
# ArcGIS Pro session (eg other script tools/toolboxes using the root logger).
# Shared by both entry-point scripts - each clears/re-adds handlers via
# setup_logging() at the start of its own run, so running diff2gdb then diff
# (or vice versa) in the same session doesn't leak handlers between them.
LOG = logging.getLogger("fit_changedetector.arcgis")
LOG.propagate = False


class ArcpyHandler(logging.Handler):
    """
    A minimal arcpy.AddMessage() logging handler.
    Taken from https://github.com/knu2xs/arcpy-logging
    """

    terminator = (
        ""  # no newline character needed, everything goes through arcpy.AddMessage
    )

    def emit(self, record: logging.LogRecord) -> None:
        """
        Args:
            record: Record containing all information needed to emit a new logging event.
        """
        # run through the formatter to honor logging formatter settings
        msg = self.format(record)

        # route anything NOTSET (0), DEBUG (10) or INFO (20) through AddMessage
        if record.levelno <= 20:
            arcpy.AddMessage(msg)

        # route all WARN (30) messages through AddWarning
        elif record.levelno == 30:
            arcpy.AddWarning(msg)

        # everything else; ERROR (40), FATAL (50) and CRITICAL (50), route through AddError
        else:
            arcpy.AddError(msg)


def setup_logging(logfile, debug=False):
    """
    Log to arcpy api and to file

    Note
    - handlers must be cleared to avoid duplication when the tool is run
      multiple times in the same arcgis session

    """
    # debug and info are the only levels supported
    if debug:
        LOG.setLevel(logging.DEBUG)
    else:
        LOG.setLevel(logging.INFO)

    # clear existing handlers
    LOG.handlers.clear()

    # set format
    log_frmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # add arcpy handler, logging to arcpy.AddMessage/AddWarning/AddError
    ah = ArcpyHandler()
    ah.setFormatter(log_frmt)
    LOG.addHandler(ah)

    # add file handler, presuming that logfile path is valid/exists
    # (valid assumption as long as the script is called via the arcgis tool)
    fh = logging.FileHandler(logfile)
    fh.setFormatter(log_frmt)
    LOG.addHandler(fh)


def resolve_sources(param):
    """Add file/layer keys to param, derived from its original_fc/new_fc keys.

    Mutates and returns param.
    """
    # use arcpy.Describe to determine source type, rather than sniffing the
    # path's file extension - the extension-based check broke for a feature
    # class nested inside a .gdb feature dataset, since its immediate parent
    # directory isn't the .gdb itself (github.com/bcgov/FIT_changedetector/issues/116)
    for src in ["original", "new"]:
        desc = arcpy.Describe(param[f"{src}_fc"])
        # arcpy's own name for the geometry field (typically "Shape") - used
        # by build_common_diff_args() to translate a geometry field picked
        # from the Fields to Include in Hash parameter into the literal
        # "geometry" the CLI actually expects, see below
        param[src + "_shape_field"] = getattr(desc, "shapeFieldName", None)
        if desc.dataType == "FeatureClass":
            # desc.path is the fc's immediate parent workspace - if the fc
            # sits inside a feature dataset, that's the feature dataset's own
            # path, not the .gdb itself, and a feature dataset isn't a real
            # openable filesystem path on its own. Walk up until we reach
            # the actual .gdb workspace.
            workspace = desc.path
            while arcpy.Describe(workspace).dataType == "FeatureDataset":
                workspace = arcpy.Describe(workspace).path
            param[src + "_file"] = workspace
            param[src + "_layer"] = desc.name
        elif desc.dataType == "ShapeFile":
            param[src + "_file"] = desc.catalogPath
            param[src + "_layer"] = desc.baseName
        else:
            # AddError alone doesn't stop execution - raise too, otherwise
            # the caller hits a confusing KeyError on the missing _file/
            # _layer keys instead of this clear message
            arcpy.AddError(
                f"{param[f'{src}_fc']} is a {desc.dataType}, only geodatabase "
                "feature classes and shapefiles are supported"
            )
            raise arcpy.ExecuteError
    return param


def build_output_stem(out_name, default_prefix):
    """Base filename (no extension) for a script tool's output + log files.

    Uses out_name as-is if supplied; otherwise falls back to
    "<default_prefix>_<timestamp>" (local time, human readable).
    """
    if out_name:
        return out_name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")  # noqa: DTZ005
    return f"{default_prefix}_{timestamp}"


def translate_hash_fields(param):
    """param["hash_fields"] (from the Fields to Include in Hash parameter),
    with the geometry field's arcpy name (eg "Shape" - see resolve_sources())
    translated to the literal "geometry".

    Expects param to already have *_shape_field keys from resolve_sources().

    geopandas/pyogrio (what the `changedetector` CLI actually reads sources
    with) always normalizes the active geometry column to "geometry" on
    read, regardless of what the source format itself calls it internally -
    so a hash field picked in ArcGIS Pro's UI under arcpy's own name for
    that column (eg "Shape") would not be found by the CLI unless translated
    here first.
    """
    shape_fields = {
        f.upper()
        for f in (param.get("original_shape_field"), param.get("new_shape_field"))
        if f
    }
    return [
        "geometry" if f.upper() in shape_fields else f for f in param["hash_fields"]
    ]


def build_common_diff_args(param):
    """CLI args shared by `diff` and `diff2gdb` - mirrors cli.py's common_diff_options.

    Expects param to already have file/layer keys from resolve_sources().
    """
    args = [param["original_file"], param["new_file"]]
    if param["original_layer"]:
        args += ["--layer-a", param["original_layer"]]
    if param["new_layer"]:
        args += ["--layer-b", param["new_layer"]]
    if param["primary_key"]:
        args += ["--primary-key", param["primary_key"]]
    if param["fields"]:
        args += ["--fields", ",".join(param["fields"])]
    if param["ignore_fields"]:
        args += ["--ignore-fields", ",".join(param["ignore_fields"])]
    if param["hash_key"]:
        args += ["--hash-key", param["hash_key"]]
    if param["hash_fields"]:
        args += ["--hash-fields", ",".join(translate_hash_fields(param))]
    if param["precision"] is not None:
        args += ["--precision", str(param["precision"])]
    if param["suffix_a"]:
        args += ["--suffix-a", param["suffix_a"]]
    if param["suffix_b"]:
        args += ["--suffix-b", param["suffix_b"]]
    if param["drop_null_geometry"]:
        args.append("--drop-null-geometry")
    if param["allow_duplicates"]:
        args.append("--allow-duplicates")
    return args


def build_verbosity_args(debug):
    args = ["-v"]  # always INFO level, matches current default
    if debug:
        args.append("-v")  # second -v -> DEBUG (cligj count option)
    return args


def run_cli(command, cli_args):
    """Run `<venv python> -m fit_changedetector <command> <cli_args>`, using
    the Python of the venv this script is installed in (find_venv_python()).

    Streams subprocess output through LOG (arcpy messages + file log) and
    raises arcpy.ExecuteError with the real failure detail on a non-zero exit.
    """
    python = find_venv_python()
    if python is None:
        arcpy.AddError(
            f"No Python environment found for {Path(__file__).parent} (no "
            "pyvenv.cfg in any parent folder). Set the tool's Script File to "
            "the copy of this script installed in the fit_changedetector "
            "venv's site-packages, and restart ArcGIS Pro - see README.md alongside the tool scripts."
        )
        raise arcpy.ExecuteError

    # strip ArcGIS Pro's own Python settings, which would otherwise make the
    # venv's interpreter load Pro's stdlib/site-packages
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)

    proc = subprocess.Popen(
        # -u: unbuffered, so output streams to the tool's messages as it
        # happens rather than in blocks
        [str(python), "-u", "-m", "fit_changedetector", command] + cli_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )

    lines = []
    for line in proc.stdout:
        line = line.rstrip()
        lines.append(line)
        LOG.info(line)
    proc.wait()

    if proc.returncode != 0:
        # surface the actual failure as an AddError to make it prominent
        error_detail = lines[-1] if lines else "(no output captured)"
        arcpy.AddError(
            f"External changedetector {command} script failed: {error_detail}"
        )
        raise arcpy.ExecuteError
    return lines


def run_tool(command, param, logfile, cli_args, out_file=None):
    """Shared entry-point body for the script tools: set up logging, log
    the run, invoke the CLI (via the venv's Python), and clean up handlers afterwards -
    regardless of which command is being run.
    """
    setup_logging(logfile, param.get("debug", False))
    try:
        LOG.info(f"Script tool parameters: {pprint.pformat(param)}")
        if out_file:
            LOG.info(f"Output file: {out_file}")
        run_cli(command, cli_args)
    finally:
        # release handlers (and the file handle) so they don't linger on
        # this logger for the rest of the ArcGIS Pro session
        for handler in LOG.handlers[:]:
            LOG.removeHandler(handler)
            handler.close()
