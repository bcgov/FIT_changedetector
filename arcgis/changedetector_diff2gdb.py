# ruff: noqa: I001
# an arcgis script tool wrapping `changedetector diff2gdb` CLI
import os

import arcpy

import changedetector_common


def build_cli_args(param, out_file):
    args = changedetector_common.build_common_diff_args(param)
    args += ["--out-file", str(out_file)]
    if param["dump_inputs"]:
        args.append("--dump-inputs")
    args += changedetector_common.build_verbosity_args(param["debug"])
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
        "out_name": arcpy.GetParameterAsText(14),
        "debug": arcpy.GetParameter(15),
    }

    # out_name (if supplied) names both the output file and its log; otherwise
    # both fall back to a timestamped default
    stem = changedetector_common.build_output_stem(param["out_name"], "changedetector")
    out_file = os.path.join(param["out_folder"], f"{stem}.gdb")
    logfile = os.path.join(param["out_folder"], f"{stem}.txt")

    changedetector_common.resolve_sources(param)
    cli_args = build_cli_args(param, out_file)
    changedetector_common.run_tool(
        "diff2gdb", param, logfile, cli_args, out_file=out_file
    )

    # publish the .gdb path as this tool's derived output parameter
    arcpy.SetParameterAsText(16, str(out_file))


if __name__ == "__main__":
    changedetector()
