import sys

# start with trying to import from path
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
from typing import Union

import arcpy

LOG = logging.getLogger(__name__)


class ArcpyHandler(logging.Handler):
    """A minimal stdlib logging to arcpy.AddMessage() handler.

    Taken from:
      https://github.com/knu2xs/arcpy-logging;
      https://knu2xs.github.io/arcpy-logging

    Logging message handler capable of routing logging through ArcPy AddMessage, AddWarning and
    AddError methods.
    DEBUG and INFO logging messages are be handled by the AddMessage method. WARNING logging
    messages are handled by the AddWarning method. ERROR and CRITICAL logging messages are handled
    by the AddError method.

    Basic use consists of the following:

    .. code-block:: python

        log = logging.getLogger(__name__)
        log.setLevel('INFO')
        ah = ArcpyHandler()
        log.addHandler(ah)
        log.info("my log message")
    """

    terminator = ""  # no newline character needed, everything goes through arcpy.AddMessage

    def emit(self, record: logging.LogRecord) -> None:
        """
        Args:
            record: Record containing all information needed to emit a new logging event.

        .. note::

            This method should not be called directly, but rather enables the ``Logger`` methods to
            be able to use this handler correctly.

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


def setup_logging(debug):
    LOG.handlers.clear()  # required to avoid duplicate messages in arcgis window
    ah = ArcpyHandler()
    if debug:
        ah.setLevel(logging.DEBUG)
    else:
        ah.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    ah.setFormatter(formatter)
    LOG.addHandler(ah)


def compare():
    param = {
        "data_original": arcpy.GetParameterAsText(0),
        "data_new": arcpy.GetParameterAsText(1),
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
    # setup logging to arcgis
    setup_logging(param["debug"])

    # note parameters supplied to tool
    LOG.debug(f"supplied parameters: {pprint.pformat(param)}")

    # break input feature class references into two strings: (gdb, layer)
    gdb_original = Path(param["data_original"]).parent
    layer_original = Path(param["data_original"]).name
    gdb_new = Path(param["data_new"]).parent
    layer_new = Path(param["data_new"]).name

    # generate output filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_file = os.path.join(param["out_folder"], f"changedetector_{timestamp}.gdb")

    try:
        fcd.compare(
            gdb_original,
            gdb_new,
            layer_original,
            layer_new,
            out_file=out_file,
            primary_key=param["primary_key"],
            fields=param["fields"],
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
