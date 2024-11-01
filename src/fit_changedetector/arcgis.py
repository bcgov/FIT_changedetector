# start with trying to import from path
# CHANGEDETECTOR_DEV = (
#    r"\\spatialfiles.bcgov\work\ilmb\dss\dss_workarea\_contractors\sinorris\FIT_changedetector\src"
# )
# sys.path.append(CHANGEDETECTOR_DEV)
# logging to arcpy translator
# PYTHON_LIBRARY = r"\\spatialfiles.bcgov\work\ilmb\dss\dsswhse\Resources\Scripts\Python\Library"
# sys.path.append(PYTHON_LIBRARY)
# import custom_modules.arcpy_logging as arclog
# sys.path.remove(PYTHON_LIBRARY)
import logging
import os

# import sys
from datetime import datetime
from pathlib import Path

import arcpy

import fit_changedetector as fcd

# ah = arclog.ArcpyHandler()
# LOG.addHandler(ah)

if __name__ == "__main__":
    # required
    data_original = arcpy.GetParameterAsText(0)
    data_new = arcpy.GetParameterAsText(1)
    out_folder = arcpy.GetParameter(2)

    # optional
    primary_key = arcpy.GetParameter(3)
    fields = arcpy.GetParameter(4)
    ignore_fields = arcpy.GetParameter(5)
    hash_key = arcpy.GetParameterAsText(6)
    hash_fields = arcpy.GetParameterAsText(7)
    precision = arcpy.GetParameterAsText(8)
    suffix_a = arcpy.GetParameterAsText(9)
    suffix_b = arcpy.GetParameterAsText(10)
    drop_null_geometry = arcpy.GetParameterAsText(11)
    dump_inputs = arcpy.GetParameterAsText(12)

    # parse parameters
    gdb_original = Path(data_original).parent
    layer_original = Path(data_original).name
    gdb_new = Path(data_new).parent
    layer_new = Path(data_new).name

    # setup logging
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s:%(levelname)s:%(name)s: %(message)s",
    )

    # generate output filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_file = os.path.join(out_folder, f"changedetector_{timestamp}.gdb")

    try:
        fcd.compare(
            gdb_original,
            gdb_new,
            layer_original,
            layer_new,
            out_file=out_file,
            primary_key=primary_key,
            fields=fields,
            suffix_a=suffix_a,
            suffix_b=suffix_b,
            drop_null_geometry=drop_null_geometry,
            hash_key=hash_key,
            hash_fields=hash_fields,
            precision=precision,
            dump_inputs=dump_inputs,
        )
    except arcpy.ExecuteError:
        print((arcpy.GetMessages()))
        arcpy.AddError(arcpy.GetMessages())
    except Exception as e:
        print(e)
        arcpy.AddError(e)
