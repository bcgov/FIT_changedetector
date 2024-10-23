import subprocess
from pathlib import Path

import arcpy

ENV = "Q:\\dss_workarea\\_contractors\\sinorris\\FIT_changedetector\\fcd_env"

data_original = arcpy.GetParameterAsText(0)
data_new = arcpy.GetParameterAsText(1)
primary_key = arcpy.GetParameter(2)
out_file = arcpy.GetParameter(3)

# -- todo --
# fields = arcpy.GetParameter(3)
# exclude_fields = arcpy.GetParameter(3)
# out_folder = arcpy.GetParameterAsText(4)
# precision = int(arcpy.GetParameterAsText(5))
# debug = arcpy.GetParameter(6)

# parse data source paths - gdb only
gdb_original = Path(data_original).parent
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
