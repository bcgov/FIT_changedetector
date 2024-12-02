# ruff: noqa: F401
# ruff: noqa: E402
# ruff: noqa: I001

import sys

CHANGEDETECTOR_DEV = (
    r"\\spatialfiles.bcgov\work\ilmb\dss\dss_workarea\_contractors\sinorris\FIT_changedetector\src"
)
sys.path.append(CHANGEDETECTOR_DEV)
import fit_changedetector as fcd

sys.path.remove(CHANGEDETECTOR_DEV)

import logging
import os
import pprint
from datetime import datetime
from pathlib import Path

import arcpy

# do not name the logger, we want to add the handler to the root logger
LOG = logging.getLogger()


class ArcpyHandler(logging.Handler):
    """
    A minimal arcpy.AddMessage() logging handler.
    Taken from https://github.com/knu2xs/arcpy-logging
    """

    terminator = ""  # no newline character needed, everything goes through arcpy.AddMessage

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


def compare():
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
        "dump_inputs": arcpy.GetParameter(12),
        "debug": arcpy.GetParameter(13),
    }

    # generate output filenames with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
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
            param[src+"_file"] = Path(param[f"{src}_fc"]).parent
            param[src+"_layer"] = Path(param[f"{src}_fc"]).name
        elif Path(param[f"{src}_fc"]).suffix == ".shp":
            param[src+"_file"] = param[f"{src}_fc"]
            param[src+"_layer"] = Path(param[f"{src}_fc"]).stem
        else:
            arcpy.AddError("Only .gdb and .shp are supported")

    try:
        fcd.compare(
            file_a=param["original_file"],
            file_b=param["new_file"],
            layer_a=param["original_layer"],
            layer_b=param["new_layer"],
            out_file=out_file,
            primary_key=param["primary_key"],
            fields=param["fields"],
            ignore_fields=param["ignore_fields"],
            suffix_a=param["suffix_a"],
            suffix_b=param["suffix_b"],
            drop_null_geometry=param["drop_null_geometry"],
            hash_key=param["hash_key"],
            hash_fields=param["hash_fields"],
            precision=param["precision"],
            dump_inputs=param["dump_inputs"],
        )
    except arcpy.ExecuteError:
        arcpy.AddError(arcpy.GetMessages())
    except Exception as e:
        arcpy.AddError(e)


if __name__ == "__main__":
    compare()
