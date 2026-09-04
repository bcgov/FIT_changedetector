"""Shared logic for the ArcGIS Pro script tools (changedetector_diff2gdb.py,
changedetector_diff.py).

Runs under ArcGIS Pro's own Python (which has arcpy but not fit_changedetector
or its dependencies), so this module is stdlib + arcpy only. It's imported by
the entry-point scripts as a plain sibling module - ArcGIS Pro adds a script
tool's own directory to sys.path, so no packaging/installation is needed;
just keep this file alongside the entry-point script(s) in the toolbox folder.

Requires `uv` - script runs the CLI via `uvx` (https://docs.astral.sh/uv/).
uv resolves/caches an isolated environment for the pinned version on demand.
"""

import logging
import os
import pprint
import subprocess
from datetime import datetime
from pathlib import Path

import arcpy

# the uvx --from spec for the fit_changedetector version to run. Pinned to a
# released version so a run always uses a known, tested version rather than
# silently picking up whatever's newest on PyPI - bump this with each
# release. For testing changes not yet on PyPI, temporarily point this at a
# git ref (e.g. "git+https://github.com/bcgov/FIT_changedetector.git@main")
# or a local wheel/checkout path instead, then revert before merging.
FIT_CHANGEDETECTOR_SPEC = "fit_changedetector==0.1.0a1"


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
    # extract path/layer from source feature class
    # There is probably an arcpy method for determining the source type,
    # but just looking at the extension is simple and seems safe
    for src in ["original", "new"]:
        if Path(param[f"{src}_fc"]).parent.suffix == ".gdb":
            param[src + "_file"] = Path(param[f"{src}_fc"]).parent
            param[src + "_layer"] = Path(param[f"{src}_fc"]).name
        elif Path(param[f"{src}_fc"]).suffix == ".shp":
            param[src + "_file"] = param[f"{src}_fc"]
            param[src + "_layer"] = Path(param[f"{src}_fc"]).stem
        else:
            arcpy.AddError("Only .gdb and .shp are supported")
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
        args += ["--primary-key", ",".join(param["primary_key"])]
    if param["fields"]:
        args += ["--fields", ",".join(param["fields"])]
    if param["ignore_fields"]:
        args += ["--ignore-fields", ",".join(param["ignore_fields"])]
    if param["hash_key"]:
        args += ["--hash-key", param["hash_key"]]
    if param["hash_fields"]:
        args += ["--hash-fields", ",".join(param["hash_fields"])]
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
    """Run `uvx --from FIT_CHANGEDETECTOR_SPEC changedetector <command> <cli_args>`.

    Streams subprocess output through LOG (arcpy messages + file log) and
    raises arcpy.ExecuteError with the real failure detail on a non-zero exit.
    """
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)

    proc = subprocess.Popen(
        ["uvx", "--from", FIT_CHANGEDETECTOR_SPEC, "changedetector", command]
        + cli_args,
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
    the run, invoke the CLI (via uvx), and clean up handlers afterwards -
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
