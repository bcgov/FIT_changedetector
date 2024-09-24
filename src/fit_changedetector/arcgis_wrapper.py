import subprocess

import arcpy

dataset_a = arcpy.GetParameterAsText(0)
dataset_b = arcpy.GetParameterAsText(1)
primary_key = arcpy.GetParameter(2)
#fields = arcpy.GetParameter(3)
#exclude_fields = arcpy.GetParameter(3)
#out_folder = arcpy.GetParameterAsText(4)
#precision = int(arcpy.GetParameterAsText(5))
#debug = arcpy.GetParameter(6)

#env_path = "Q:\dss_workarea\_contractors\sinorris\FIT_changedetector\\fcd_env"
#dataset_a = "Q:\dss_workarea\_contractors\sinorris\FIT_changedetector\\tests\data\\test_parks_a.geojson"
#dataset_b = "Q:\dss_workarea\_contractors\sinorris\FIT_changedetector\\tests\data\\test_parks_b.geojson"
#primary_key = "fcd_load_id"
subprocess.run(f'CALL conda.bat deactivate && conda activate {env_path} && changedetector {dataset_a} {dataset_b} -k {primary_key}', shell=True)
