# ruff: noqa: I001

import os
from datetime import datetime

import arcpy

import arcgis_common


def build_cli_args(param, out_file):
    args = arcgis_common.build_common_diff_args(param)
    args += ["--out-file", str(out_file)]
    args += arcgis_common.build_verbosity_args(param["debug"])
    return args


def changedetector():
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
        "debug": arcpy.GetParameter(13),
    }

    # generate output filenames with timestamp (local time, human readable)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")  # noqa: DTZ005
    out_file = os.path.join(
        param["out_folder"], f"changedetector_diff_{timestamp}.json"
    )
    logfile = os.path.join(param["out_folder"], f"changedetector_diff_{timestamp}.txt")

    arcgis_common.resolve_sources(param)
    cli_args = build_cli_args(param, out_file)
    arcgis_common.run_tool("diff", param, logfile, cli_args, out_file=out_file)

    # publish the JSON summary path as this tool's derived output parameter
    arcpy.SetParameterAsText(14, str(out_file))


if __name__ == "__main__":
    changedetector()
