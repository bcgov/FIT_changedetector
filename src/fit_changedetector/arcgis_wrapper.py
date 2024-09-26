import subprocess

import arcpy

ENV = "Q:\\dss_workarea\\_contractors\\sinorris\\FIT_changedetector\\fcd_env"

dataset_a = arcpy.GetParameterAsText(0)
dataset_b = arcpy.GetParameterAsText(1)
primary_key = arcpy.GetParameter(2)

# -- todo --
# fields = arcpy.GetParameter(3)
# exclude_fields = arcpy.GetParameter(3)
# out_folder = arcpy.GetParameterAsText(4)
# precision = int(arcpy.GetParameterAsText(5))
# debug = arcpy.GetParameter(6)

subprocess.run(
    f"CALL conda.bat deactivate && conda activate {ENV} && changedetector {dataset_a} {dataset_b} -k {primary_key}",
    shell=True,
)
