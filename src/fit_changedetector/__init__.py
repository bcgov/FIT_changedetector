from .changedetector import add_hash_key as add_hash_key
from .changedetector import diff_to_gdb as diff_to_gdb
from .changedetector import diff_to_json as diff_to_json
from .changedetector import gdf_diff as gdf_diff

__version__ = "0.0.1a2"

area_length_fields = [
    "SHAPE_LENGTH",
    "SHAPE_LENG",
    "SHAPE_AREA",
    "GEOMETRY_LENGTH",
    "GEOMETRY_AREA",
]

# ESRI-reserved id fields: unlike area_length_fields (dropped only from the
# attribute-comparison copies), these are dropped everywhere a matching field
# is found, including from copies written to output - a field literally named
# OBJECTID/FID is auto-mapped by GDAL's OpenFileGDB writer to the layer's
# actual feature id, so if the source's own values for it aren't unique
# (common - it's often just row order, not a stable identifier), writing any
# output that retains it fails outright ("Cannot create feature of ID <n>
# because one already exists"). Kept in sync by hand with IGNORE_FIELDS in
# arcgis_ToolValidator.py, which can't import this package (it runs inside
# ArcGIS Pro's own Python, not the tool's venv).
id_fields = [
    "OBJECTID",
    "OID_",  # ArcPro adds this to csv files
    "FID",
]

valid_precisions = [
    1,
    0.1,
    0.01,  # default
    0.001,
    0.0001,
    0.00001,
    0.000001,  # use v fine precisions when units are degrees
    0.0000001,
    0.00000001,
]
