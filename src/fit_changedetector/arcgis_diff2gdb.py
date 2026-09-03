# ruff: noqa: I001

import os
from datetime import datetime

import arcpy

import arcgis_common


def build_cli_args(param, out_file):
    args = arcgis_common.build_common_diff_args(param)
    args += ["--out-file", str(out_file)]
    if param["dump_inputs"]:
        args.append("--dump-inputs")
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
        "dump_inputs": arcpy.GetParameter(13),
        "debug": arcpy.GetParameter(14),
    }

    # generate output filenames with timestamp (local time, human readable)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")  # noqa: DTZ005
    out_file = os.path.join(param["out_folder"], f"changedetector_{timestamp}.gdb")
    logfile = os.path.join(param["out_folder"], f"changedetector_{timestamp}.txt")

    arcgis_common.resolve_sources(param)
    cli_args = build_cli_args(param, out_file)
    arcgis_common.run_tool("diff2gdb", param, logfile, cli_args, out_file=out_file)


if __name__ == "__main__":
    changedetector()
