from .diff import add_hash_key as add_hash_key
from .diff import compare as compare
from .diff import gdf_diff as gdf_diff

__version__ = "0.0.1a1"

area_length_fields = [
    "SHAPE_LENGTH",
    "SHAPE_LENG",
    "SHAPE_AREA",
    "GEOMETRY_LENGTH",
    "GEOMETRY_AREA",
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
