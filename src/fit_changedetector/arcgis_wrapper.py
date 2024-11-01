import sys

# start with trying to import from path
#CHANGEDETECTOR_DEV = (
#    r"\\spatialfiles.bcgov\work\ilmb\dss\dss_workarea\_contractors\sinorris\FIT_changedetector\src"
#)
#sys.path.append(CHANGEDETECTOR_DEV)

import arcpy

# required
data_original = arcpy.GetParameterAsText(0)
data_new = arcpy.GetParameterAsText(1)
out_folder = arcpy.GetParameter(2)

# optional
primary_key = arcpy.GetParameter(3)
fields = arcpy.GetParameter(4)
ignore_fields = arcpy.GetParameter(5)
out_folder = arcpy.GetParameterAsText(6)
precision = int(arcpy.GetParameterAsText(7))

# parse data source paths - gdb only
# gdb_original = Path(data_original).parent
layer_original = Path(data_original).name
gdb_new = Path(data_new).parent
layer_new = Path(data_new).name

result = subprocess.run(
    f"CALL conda.bat deactivate && conda activate {ENV} && changedetector compare {gdb_original} {gdb_new} --layer-a {layer_original} --layer-b {layer_new} -pk {primary_key} -o {out_file} -vv",
    shell=True,
    capture_output=True,
    text=True,
)
arcpy.AddMessage(result.stdout)
arcpy.AddMessage(result.stderr)
