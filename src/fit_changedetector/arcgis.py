import sys

# start with trying to import from path
CHANGEDETECTOR_DEV = (
    r"\\spatialfiles.bcgov\work\ilmb\dss\dss_workarea\_contractors\sinorris\FIT_changedetector\src"
)
sys.path.append(CHANGEDETECTOR_DEV)
import fit_changedetector as fcd

sys.path.remove(CHANGEDETECTOR_DEV)

# logging to arcpy translator
PYTHON_LIBRARY = r"\\spatialfiles.bcgov\work\ilmb\dss\dsswhse\Resources\Scripts\Python\Library"
sys.path.append(PYTHON_LIBRARY)
import custom_modules.arcpy_logging as arclog

sys.path.remove(PYTHON_LIBRARY)

import logging
import os

# import sys
from datetime import datetime
from pathlib import Path

import arcpy

LOG = logging.getLogger(__name__)
LOG.setLevel("INFO")
ah = arclog.ArcpyHandler()
LOG.addHandler(ah)


if __name__ == "__main__":
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
    }

    # break input feature class references into two strings: (gdb, layer)
    gdb_original = Path(param["data_original"]).parent
    layer_original = Path(param["data_original"]).name
    gdb_new = Path(param["data_new"]).parent
    layer_new = Path(param["data_new"]).name

    # generate output filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_file = os.path.join(param["out_folder"], f"changedetector_{timestamp}.gdb")

    # arcpy.AddMessage(param)

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
