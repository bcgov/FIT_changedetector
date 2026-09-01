# ruff: noqa: I001

import logging
import os
import pprint
from datetime import datetime
from pathlib import Path
import subprocess

import arcpy

# path to the virtualenv's python.exe, set as a system/user environment
# variable so this file doesn't need editing after every install/update
VENV_PYTHON_ENV_VAR = "FIT_CHANGEDETECTOR_VENV_PYTHON"


# do not name the logger, we want to add the handler to the root logger
LOG = logging.getLogger()


def build_cli_args(param, out_file):
    args = [param["original_file"], param["new_file"], "--out-file", str(out_file)]
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
    if param["dump_inputs"]:
        args.append("--dump-inputs")
    args.append("-v")  # always INFO level, matches current default
    if param["debug"]:
        args.append("-v")  # second -v -> DEBUG (cligj count option)
    return args


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
    - handlers are added to the root logger (for auto-handling of messages from modules)
    - because handlers are added to the root logger, they must be cleared to avoid duplication
      when the tool is run multiple times in the same arcgis session

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


def get_venv_python():
    venv_python = os.environ.get(VENV_PYTHON_ENV_VAR)
    if venv_python:
        return venv_python
    config_file = Path(__file__).parent / "venv_python.txt"
    if config_file.exists():
        return config_file.read_text().strip()
    return None


def changedetector():
    venv_python = get_venv_python()
    if not venv_python:
        arcpy.AddError(
            f"Environment variable {VENV_PYTHON_ENV_VAR} is not set, and no "
            f"{Path(__file__).parent / 'venv_python.txt'} file was found. "
            "Set the environment variable (preferred) or create that file "
            "containing the path to python.exe within the virtualenv where "
            "fit_changedetector is installed."
        )
        raise arcpy.ExecuteError

    param = {
        "original_fc": arcpy.GetParameterAsText(0),
        "new_fc": arcpy.GetParameterAsText(1),
        "out_folder": arcpy.GetParameterAsText(2),
        "primary_key": arcpy.GetParameter(3),
        "fields": arcpy.GetParameter(4),
        "ignore_fields": arcpy.GetParameter(5),
        "hash_key": arcpy.GetParameter(6),
        "hash_fields": arcpy.GetParameter(7),
        "precision": arcpy.GetParameter(8),
        "suffix_a": arcpy.GetParameter(9),
        "suffix_b": arcpy.GetParameter(10),
        "drop_null_geometry": arcpy.GetParameter(11),
        "allow_duplicates": arcpy.GetParameter(12),
        "dump_inputs": arcpy.GetParameter(13),
        "debug": arcpy.GetParameter(14),
    }

    # generate output filenames with timestamp (local time, human readable)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")  # noqa: DTZ005
    out_file = os.path.join(param["out_folder"], f"changedetector_{timestamp}.gdb")
    logfile = os.path.join(param["out_folder"], f"changedetector_{timestamp}.txt")

    # setup logging to arcgis and file
    setup_logging(logfile, param["debug"])

    # note all parameters supplied to tool
    LOG.info(f"Script tool parameters: {pprint.pformat(param)}")
    # note target file
    LOG.info(f"Output file: {out_file}")

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

    cli_args = build_cli_args(param, out_file)

    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)

    proc = subprocess.Popen(
        [venv_python, "-u", "-m", "fit_changedetector.cli", "diff2gdb"] + cli_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )

    for line in proc.stdout:
        LOG.info(line.rstrip())
    proc.wait()

    if proc.returncode != 0:
        arcpy.AddError(
            "External changedetector diff2gdb script failed — see messages above."
        )
        raise arcpy.ExecuteError


if __name__ == "__main__":
    changedetector()
