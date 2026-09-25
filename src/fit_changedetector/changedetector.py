import hashlib
import io
import json
import logging
import os
import shutil
import sys
from datetime import datetime

import geopandas
import numpy
import pandas
import pyarrow
import pyarrow.parquet
import pyogrio
from shapely.geometry.linestring import LineString
from shapely.geometry.multilinestring import MultiLineString
from shapely.geometry.multipoint import MultiPoint
from shapely.geometry.multipolygon import MultiPolygon
from shapely.geometry.point import Point
from shapely.geometry.polygon import Polygon

import fit_changedetector as fcd

LOG = logging.getLogger(__name__)

# Mapping from OGR field types to pandas nullable equivalents.
# Ensures null-tolerant dtypes are used regardless of whether nulls are present,
# avoiding silent upcasts (e.g. int → float64) or inconsistent NA representations.
_NULLABLE_OGR_MAP = {
    "OFTInteger": "Int32",
    "OFTInteger64": "Int64",
    "OFTString": "string",
    "OFTWideString": "string",
}

# Curve types (e.g. CircularString, CompoundCurve, CurvePolygon - as found in some
# .gdb sources) are not supported. shapely itself has no curve geometry classes, so
# GDAL always segments curves into a linear approximation before a geometry can even
# become a shapely object - at a precision this tool does not control - so reject the
# source outright rather than silently comparing an unvalidated approximation.
# https://github.com/bcgov/FIT_changedetector/issues/66
_SUPPORTED_GEOMETRY_TYPES = {
    "Point",
    "LineString",
    "Polygon",
    "MultiPoint",
    "MultiLineString",
    "MultiPolygon",
}


def _check_geometry_type(geometry_type, src):
    """Raise if *geometry_type* (from pyogrio.read_info) is not supported.

    None (non-spatial source) and "Unknown" (mixed simple types within one layer,
    e.g. Point + MultiPoint together - handled separately via promote_to_multi)
    are allowed through unchecked.
    """
    if geometry_type is None or geometry_type == "Unknown":
        return
    base_type = geometry_type.split(" ")[
        0
    ]  # strip " Z"/" M"/" ZM" dimensionality suffix
    if base_type not in _SUPPORTED_GEOMETRY_TYPES:
        raise ValueError(
            f"Geometry type '{geometry_type}' in {src} is not supported "
            f"(no curves) - only {sorted(_SUPPORTED_GEOMETRY_TYPES)} are supported."
        )


def _cast_dtypes(df, path, layer=None, src=None):
    """Cast *df* columns to pandas nullable dtypes matching the source OGR field types.

    Uses pyogrio.read_info to retrieve OGR field types from *path*/*layer* and
    re-casts integer and string columns to their pandas nullable equivalents.
    Also validates the source's geometry type, see _check_geometry_type.
    """
    kw = {"layer": layer} if layer else {}
    info = pyogrio.read_info(path, **kw)
    _check_geometry_type(info["geometry_type"], src if src is not None else path)
    ogr_types = dict(zip(info["fields"], info["ogr_types"]))
    for col, ogr_type in ogr_types.items():
        if col not in df.columns:
            continue
        target = _NULLABLE_OGR_MAP.get(ogr_type)
        if target and str(df[col].dtype) != target:
            df[col] = df[col].astype(target)
    return df


_PARQUET_EXTENSIONS = (".parquet", ".geoparquet")


def _nullable_int_dtype(name):
    """Pandas nullable integer dtype name for a numpy/arrow integer type name,
    eg "int32" -> "Int32", "uint8" -> "UInt8".
    """
    return "UInt" + name[4:] if name.startswith("u") else "Int" + name[3:]


def _common_int_dtype(dtype_a, dtype_b):
    """Smallest pandas nullable integer dtype holding all values of both integer
    dtypes (eg Int16/Int32 -> Int32, UInt16/Int16 -> Int32), or None if there is
    none (uint64 with any signed type).
    """
    common = numpy.promote_types(
        getattr(dtype_a, "numpy_dtype", dtype_a),
        getattr(dtype_b, "numpy_dtype", dtype_b),
    )
    if common.kind not in "iu":
        return None
    return _nullable_int_dtype(common.name)


def _cast_parquet_int_dtypes(df, path):
    """Cast *df*'s integer columns to pandas nullable dtypes matching the parquet schema.

    The parquet equivalent of _cast_dtypes: without pandas metadata in the file
    (eg parquet written by GDAL or duckdb), geopandas.read_parquet() reads an integer
    column containing nulls as float64 - which then fails gdf_diff's dtype check
    against the same field from another source.
    """
    for field in pyarrow.parquet.read_schema(path):
        if field.name in df.columns and pyarrow.types.is_integer(field.type):
            target = _nullable_int_dtype(str(field.type))
            if str(df[field.name].dtype) != target:
                df[field.name] = df[field.name].astype(target)
    return df


def _normalize_string_dtypes(df):
    """Cast string-like columns to pandas' "string" dtype.

    geopandas.read_parquet() and _cast_dtypes() (OGR string fields) can produce
    different StringDtype storage variants for equivalent string columns (e.g.
    pandas 3's default arrow-backed variant vs. the classic one) - these compare
    unequal in gdf_diff's dtype check despite being equivalent, so normalize to
    one consistent spelling regardless of source format.
    """
    for col in df.columns:
        if col != df.geometry.name and pandas.api.types.is_string_dtype(df[col]):
            df[col] = df[col].astype("string")
    return df


def _read_source(path, layer, label):
    """Read a diff_to_gdb()/diff_to_json() source, casting dtypes as per _cast_dtypes.

    A path of "-" reads GeoJSON from stdin instead of a file (no layer support,
    since a stream has no concept of multiple layers). A .parquet/.geoparquet path
    reads via geopandas.read_parquet() (pyarrow) instead of the OGR-based
    geopandas.read_file() - GDAL's Parquet driver is optional (requires GDAL built
    with Apache Arrow), and the GDAL bundled in pyogrio's wheels is built without it.
    With no OGR field types available, _cast_dtypes is not applicable; integer
    columns are instead cast per the parquet schema (see
    _cast_parquet_int_dtypes), and string dtypes normalized (see
    _normalize_string_dtypes).
    """
    if path == "-":
        if layer:
            raise ValueError(
                f"--layer-{label} cannot be used when reading source {label} from stdin"
            )
        data = sys.stdin.buffer.read()
        df = _cast_dtypes(
            geopandas.read_file(io.BytesIO(data)), io.BytesIO(data), src="stdin"
        )
        return df, "stdin"
    if path.lower().endswith(_PARQUET_EXTENSIONS):
        if layer:
            raise ValueError(
                f"--layer-{label} cannot be used when reading source {label} from parquet"
            )
        df = _cast_parquet_int_dtypes(geopandas.read_parquet(path), path)
        return _normalize_string_dtypes(df), path
    src = os.path.join(path, layer or "")
    df = _cast_dtypes(geopandas.read_file(path, layer=layer), path, layer, src=src)
    return df, src


def promote_to_multi(df):
    """Promote all geometries in the dataframe to multipart"""
    df.geometry = [
        MultiPoint([feature]) if isinstance(feature, Point) else feature
        for feature in df.geometry
    ]
    df.geometry = [
        MultiLineString([feature]) if isinstance(feature, LineString) else feature
        for feature in df.geometry
    ]
    df.geometry = [
        MultiPolygon([feature]) if isinstance(feature, Polygon) else feature
        for feature in df.geometry
    ]
    return df


def _geom_types(df):
    """Set of geometry type names (e.g. "Point", "MultiPoint") present in df."""
    return set(df.geometry.geom_type.dropna().unique())


def _check_geom_types(df, label):
    """Raise if df holds a geometry type not in _SUPPORTED_GEOMETRY_TYPES.

    Complements _check_geometry_type (source layer metadata, the only place
    curves are still detectable - GDAL linearizes them on read) by checking the
    geometries themselves, so gdf_diff() callers and parquet sources are covered
    too.
    """
    unsupported = _geom_types(df) - _SUPPORTED_GEOMETRY_TYPES
    if unsupported:
        raise ValueError(
            f"Geometry type(s) {sorted(unsupported)} in source {label} not supported "
            f"- only {sorted(_SUPPORTED_GEOMETRY_TYPES)} are supported."
        )


def _has_mixed_single_multipart(types):
    """True if types (from _geom_types) contains both a base type and its
    Multi* equivalent, e.g. {"LineString", "MultiLineString"} - regardless of
    any other types present.
    """
    return any("Multi" + t in types for t in types)


def _promote_if_mixed(df_a, df_b):
    """If df_a and df_b between them mix single/multipart geometries of the
    same base type (e.g. Point in df_a, MultiPoint in df_b - or both within
    one source), promote all geometries in both df_a and df_b to multipart, so
    a feature stored single-part in one source and multi-part in the other
    compares as unchanged, and every downstream output sees consistent types.
    No-op (returns df_a/df_b unchanged) if no mix is present.
    """
    if _has_mixed_single_multipart(_geom_types(df_a) | _geom_types(df_b)):
        LOG.info(
            "Mixed singlepart/multipart geometries found, promoting all to multipart"
        )
        df_a = promote_to_multi(df_a)
        df_b = promote_to_multi(df_b)
    return df_a, df_b


def _prepare_sources(
    df_a, df_b, keep_fields, label_a="a", label_b="b", promote_multi=True
):
    """
    - promote mixed single/multipart geometries (unless not promote_multi)
    - drop ESRI-reserved id fields not in keep_fields

    Shared by _read_and_diff() and _validate_and_prepare_diff_inputs()

    keep_fields is a set of upper-cased field names to exclude from the
    id-field drop even if they match fcd.id_fields - e.g. a caller-chosen
    primary key or comparison field.
    """
    if isinstance(df_a, geopandas.GeoDataFrame) and isinstance(
        df_b, geopandas.GeoDataFrame
    ):
        _check_geom_types(df_a, label_a)
        _check_geom_types(df_b, label_b)
        if promote_multi:
            df_a, df_b = _promote_if_mixed(df_a, df_b)

    for f in list(df_a.columns):
        if f.upper() in fcd.id_fields and f.upper() not in keep_fields:
            LOG.info(f"Dropping reserved id field {f} from source_{label_a}")
            df_a = df_a.drop(columns=[f])
    for f in list(df_b.columns):
        if f.upper() in fcd.id_fields and f.upper() not in keep_fields:
            LOG.info(f"Dropping reserved id field {f} from source_{label_b}")
            df_b = df_b.drop(columns=[f])
    return df_a, df_b


def add_hash_key(
    df,
    new_field,
    fields: list,
    drop_null_geometry=None,
    allow_duplicates=False,
    precision=0.01,
):
    """Add new column to input dataframe, containing hash of the provided fields.

    fields must be provided and lists every column to fold into the hash -
    to include geometry, add the geometry column's name (df.geometry.name,
    typically "geometry") to fields explicitly; omit it to hash on
    attributes only.

    drop_null_geometry only has meaning when the geometry field is included
    in fields - specifying it otherwise raises, rather than silently having
    no effect. When applicable, it defaults to True (drop null geometries
    with a warning) if not specified.

    allow_duplicates does not apply to a geometry-only hash (fields is just
    the geometry column) - a duplicate hash always raises there, since geometry
    alone can't reliably pair records between datasets when more than one
    shares a location.
    """
    pandas.options.mode.chained_assignment = None

    # validate precision
    if precision not in fcd.valid_precisions:
        raise ValueError(
            f"Precision {precision} is not supported, use one of {fcd.valid_precisions}"
        )

    # Fail if output column is already present in data
    if new_field in df.columns:
        raise ValueError(
            f"Field {new_field} is present in input dataset, use some other column name"
        )

    # Fail if nothing provided to hash
    if not fields:
        raise ValueError(
            "Nothing to hash, specify fields to hash (include the geometry field's name "
            "to hash on geometry)"
        )

    # is the geometry field named in fields? if so, hash on geometry too
    geom_field = df.geometry.name if isinstance(df, geopandas.GeoDataFrame) else None
    hash_geometry = geom_field is not None and geom_field in fields

    # Fail if a requested field isn't actually present - a misnamed geometry
    # field (eg "Shape"/"SHAPE" from ArcGIS habit, when this source's
    # geometry column is actually named something else) is the most likely
    # cause, so hint at the real name to save a confusing round trip
    missing = [f for f in fields if f not in df.columns]
    if missing:
        hint = (
            f" - this dataset's geometry field is named '{geom_field}'"
            if geom_field
            else ""
        )
        raise ValueError(f"Field(s) {missing} not present in input data{hint}")

    # drop_null_geometry only applies when hashing the geometry field
    if not hash_geometry and drop_null_geometry:
        raise ValueError(
            "drop_null_geometry has no effect unless the geometry field is included in "
            "fields - remove one or the other"
        )

    # Fail if attempting include a geometry based column in fields [],
    # this information will be captured by the geometry
    for f in fields:
        if f in fcd.area_length_fields:
            raise ValueError(
                f"Cannot hash field {f}, hashing on area/length fields is not supported"
            )

    # if hashing the geometry, ensure no nulls are present and standardize ring order/precision
    if hash_geometry:
        # If using default precision of 1cm on data using degrees,
        # presume this is an oversight, warn and adjust.
        # (if non-default precision is provided, presume that the user is right)
        if df.geometry.crs.is_geographic and precision == 0.01:
            LOG.warning(
                "Data is projected in degrees, default precision of 0.01m specified. "
                "Adjusting to .0000001 degrees"
            )
            precision = 0.0000001

        if drop_null_geometry is None:
            drop_null_geometry = True

        # check for null geometries, drop if specified
        if len(df[df.geometry.isnull()]) > 0:
            LOG.warning("Null geometries are present in source")
            if drop_null_geometry:
                LOG.warning("Dropping null geometries from source")
                df = df[df.geometry.notnull()]
            else:
                raise ValueError(
                    "Cannot reliably hash null geometries, specify drop_null_geometry or remove "
                    "nulls from source dataset before re-processing"
                )

        # normalize the geometry to ensure consistent comparisons/hashes on equivalent features
        df = df.copy()  # copy so the original df does not get the new column
        df["_geometry_normalized_"] = (
            df[geom_field].normalize().set_precision(precision, mode="pointwise")
        )
        hash_fields = [
            "_geometry_normalized_" if f == geom_field else f for f in fields
        ]
    else:
        df = df.copy()  # copy so the original df does not get the new column
        hash_fields = fields

    # add sha1 hash of provided fields
    df[new_field] = df[hash_fields].apply(
        lambda x: hashlib.sha1(
            "|".join(x.astype(str).fillna("NULL").values).encode("utf-8")
        ).hexdigest(),
        axis=1,
    )

    # remove the normalized/reduced precision geometry
    if hash_geometry:
        df = df.drop(columns=["_geometry_normalized_"])

    # fail if hashes are not unique. A pure geometry hash (no other fields
    # contributing) always fails here regardless of allow_duplicates: with
    # no other attributes to go on, geometry alone can't reliably pair a
    # record in one dataset with its counterpart in the other once more than
    # one record shares a location, so the comparison itself becomes
    # unreliable. allow_duplicates only applies once at least one non-geometry
    # field also contributes to the hash (or is used directly as
    # primary_key), since that gives gdf_diff a much more solid basis for
    # pairing records across datasets.
    hash_is_geometry_only = hash_fields == ["_geometry_normalized_"]
    if len(df) != len(df[new_field].drop_duplicates()) and (
        not allow_duplicates or hash_is_geometry_only
    ):
        if hash_is_geometry_only:
            raise ValueError(
                "Duplicate geometries are present in source, consider including more fields in the hash "
                "or editing the data. Option allow_duplicates does not apply to a geometry-only hash, since "
                "geometry alone can't reliably pair records between datasets when more than one shares "
                "a location"
            )
        else:
            raise ValueError(
                "Duplicate values for output hash are present, consider including more fields in the hash "
                "or editing the data"
            )
    return df


def _validate_and_prepare_diff_inputs(
    df_a,
    df_b,
    primary_key,
    fields,
    ignore_fields,
    precision,
    allow_duplicates=False,
    promote_multi=True,
    strict_types=False,
):
    """Validate df_a/df_b are comparable and prepare them for gdf_diff.

    Checks: valid precision, primary key present/unique (unless allow_duplicates)
    in both datasets and not also an ignore_field, fields provided (if any) common
    to both datasets, equivalent field dtypes (unless strict_types, integers of
    differing width are cast to their smallest common type with a warning), and
    (for spatial sources) supported geometry types and equivalent CRS - raising
    ValueError/TypeError on the first violation found.

    If allow_duplicates, rather than raising on a duplicated primary key, drop
    all but the first occurrence of each duplicated key (independently in each
    dataset) before comparison - the dropped records (full, unfiltered schema)
    are returned separately so callers can report/write them out as duplicates.

    Also resolves *fields* to its final list (common fields when none given,
    always including the primary key and geometry), standardizes the geometry
    column name, drops esri-generated area/length and reserved id fields (see
    fcd.area_length_fields/fcd.id_fields), and (for spatial sources, if
    promote_multi) promotes mixed single/multipart geometries to multipart (see
    _prepare_sources).

    Returns (df_a, df_b, df_a_src, df_b_src, fields, spatial, duplicates_a,
    duplicates_b), where df_a/df_b are filtered to the resolved fields,
    df_a_src/df_b_src are unfiltered copies retained by gdf_diff for
    rebuilding full-schema outputs later, and duplicates_a/duplicates_b are
    the (unfiltered schema) records dropped from df_a_src/df_b_src due to a
    duplicated primary key (empty if allow_duplicates was not needed).
    """
    if fields is None:
        fields = []
    if ignore_fields is None:
        ignore_fields = []

    # are input datasets spatial?
    if isinstance(df_a, geopandas.GeoDataFrame) and isinstance(
        df_b, geopandas.GeoDataFrame
    ):
        spatial = True
    elif isinstance(df_a, geopandas.GeoDataFrame) and not isinstance(
        df_b, geopandas.GeoDataFrame
    ):
        raise TypeError(
            "Cannot compare spatial and non-spatial sources - spatial component found in source 1 "
            "but not in source 2."
        )
    elif isinstance(df_b, geopandas.GeoDataFrame) and not isinstance(
        df_a, geopandas.GeoDataFrame
    ):
        raise TypeError(
            "Cannot compare spatial and non-spatial sources - spatial component found in source 2 "
            "but not in source 1."
        )
    else:
        spatial = False

    # is precision supported?
    if precision not in fcd.valid_precisions:
        raise ValueError(
            f"Precision {precision} is not supported, use one of {fcd.valid_precisions}"
        )

    # promote mixed single/multipart geometries and drop ESRI-reserved id
    # fields - see _prepare_sources. Must happen before the df_a_src/df_b_src
    # copy below, since those (used to rebuild full-schema NEW/DELETED/
    # MODIFIED_GEOM outputs) need the same fix, not just the comparison-only
    # df_a/df_b. (When called via _read_and_diff, its own df_a/df_b already
    # went through this, so it's a no-op here; it still matters for gdf_diff()
    # called directly with raw/mixed-type input.)
    keep_fields = {primary_key.upper()} | {f.upper() for f in fields}
    df_a, df_b = _prepare_sources(df_a, df_b, keep_fields, promote_multi=promote_multi)

    # retain a full copy of both sources for writing unchanged source schemas (apart from above
    # geometry adjustment) to NEW/UNCHANGED/DELETED/MODIFIED_GEOM (not the fields used for attribute
    # change detection)
    df_a_src = df_a.copy()
    df_b_src = df_b.copy()

    # standardize geometry column name
    if spatial and df_a.geometry.name != "geometry":
        df_a = df_a.rename_geometry("geometry")
    if spatial and df_b.geometry.name != "geometry":
        df_b = df_b.rename_geometry("geometry")

    # drop esri generated area/length fields (comparison copies only - unlike
    # id_fields above, these are harmless to retain in the *_src copies used
    # to rebuild full-schema outputs, so are left there)
    for f in df_a.columns:
        if f.upper() in fcd.area_length_fields:
            df_a = df_a.drop(columns=[f])
    for f in df_b.columns:
        if f.upper() in fcd.area_length_fields:
            df_b = df_b.drop(columns=[f])

    ignore_fields = list({f.upper() for f in ignore_fields})

    # ignore fields cannot be specified as pk, fail
    if primary_key.upper() in ignore_fields:
        raise ValueError(f"Field {primary_key} cannot be used as a primary key")

    # find fields common to both input datasets
    fields_common = set(df_a.columns).intersection(set(df_b.columns))

    # is primary key present in both datasets?
    if primary_key not in fields_common:
        raise ValueError(f"Primary key {primary_key} must be present in both datasets")

    # if provided a list of fields to work with, validate that list
    if fields:
        fields = list(set(fields + [primary_key, "geometry"]))
        if len(set(fields).intersection(fields_common)) != len(fields):
            raise ValueError("Provided fields are not common to both datasets")
    else:
        fields = list(fields_common)

    # remove ignore_fields from comparison
    for f in list(fields):
        if f.upper() in ignore_fields:
            LOG.warning(
                f"Field {f} is ignored by changedetector and will not be included in results"
            )
            fields.remove(f)

    if len(fields) == 0:
        raise ValueError("Datasets have no field names in common, cannot compare")

    # retain only common fields of interest
    df_a = df_a[fields]
    df_b = df_b[fields]

    # are data types equivalent for fields to be compared? Unless strict_types,
    # integers of differing width (eg OGR Integer/Integer64 -> Int32/Int64) are a
    # minor difference - warn, and compare both as their smallest common type
    # rather than making the user edit their data (#128)
    for f in df_a.columns:
        if df_a[f].dtype == df_b[f].dtype:
            continue
        common = None
        if (
            not strict_types
            and pandas.api.types.is_integer_dtype(df_a[f])
            and pandas.api.types.is_integer_dtype(df_b[f])
        ):
            common = _common_int_dtype(df_a[f].dtype, df_b[f].dtype)
        if common:
            LOG.warning(
                f"Integer field types differ, comparing as {common}. {f}: "
                f"({df_a[f].dtype}, {df_b[f].dtype})"
            )
            df_a[f] = df_a[f].astype(common)
            df_b[f] = df_b[f].astype(common)
            # results are joined back to the full-schema sources on the primary
            # key, which fails for mismatched index types (eg uint16 vs Int64)
            if f == primary_key:
                df_a_src[f] = df_a_src[f].astype(common)
                df_b_src[f] = df_b_src[f].astype(common)
        else:
            raise ValueError(
                f"Field types do not match. {f}: ({df_a[f].dtype}, {df_b[f].dtype})"
            )

    # are CRS equivalent?
    if spatial and df_a.crs != df_b.crs:
        raise ValueError("Coordinate reference systems are not equivalent")

    # is primary key unique in both datasets? if allow_duplicates, retain the records
    # to be dropped (full, unfiltered schema) so callers can report/write them out
    duplicates_a = df_a_src.iloc[0:0]
    duplicates_b = df_b_src.iloc[0:0]
    if len(df_a) != len(df_a[[primary_key]].drop_duplicates()):
        if not allow_duplicates:
            raise ValueError(
                f"Duplicate values exist for primary_key {primary_key}, in dataframe a, consider using "
                "another primary key or pre-processing to remove duplicates"
            )
        duplicates_a = df_a_src[
            df_a_src.duplicated(subset=[primary_key], keep="first")
        ].copy()
        LOG.warning(
            f"{duplicates_a[primary_key].nunique()} duplicate value(s) exist for primary_key "
            f"{primary_key} in dataframe a ({len(duplicates_a)} record(s) dropped) - keeping "
            "first occurrence of each; see the DUPLICATES output for details"
        )
        df_a = df_a.drop_duplicates(subset=[primary_key], keep="first")
        df_a_src = df_a_src.drop_duplicates(subset=[primary_key], keep="first")
    if len(df_b) != len(df_b[[primary_key]].drop_duplicates()):
        if not allow_duplicates:
            raise ValueError(
                f"Duplicate values exist for primary_key {primary_key}, in dataframe b, consider using "
                "another primary key or pre-processing to remove duplicates"
            )
        duplicates_b = df_b_src[
            df_b_src.duplicated(subset=[primary_key], keep="first")
        ].copy()
        LOG.warning(
            f"{duplicates_b[primary_key].nunique()} duplicate value(s) exist for primary_key "
            f"{primary_key} in dataframe b ({len(duplicates_b)} record(s) dropped) - keeping "
            "first occurrence of each; see the DUPLICATES output for details"
        )
        df_b = df_b.drop_duplicates(subset=[primary_key], keep="first")
        df_b_src = df_b_src.drop_duplicates(subset=[primary_key], keep="first")

    return df_a, df_b, df_a_src, df_b_src, fields, spatial, duplicates_a, duplicates_b


def gdf_diff(
    df_a: geopandas.GeoDataFrame,
    df_b: geopandas.GeoDataFrame,
    primary_key: str,
    *,
    fields=None,
    ignore_fields=None,
    precision=0.01,
    suffix_a="a",
    suffix_b="b",
    return_type="gdf",
    allow_duplicates=False,
    promote_multi=True,
    strict_types=False,
):
    """
    Compare two geodataframes and generate a diff.

    Sources MUST:
    - have valid, compatible primary keys (unique, unless allow_duplicates - see
      below)
    - have at least one equivalent column (ok if this is just the primary key)
    - equivalent column names must be of equivalent types (unless strict_types,
      integers of differing width are accepted with a warning, and compared as
      their smallest common type - eg Int16/Int32 as Int32)
    - have supported geometry types and equivalent coordinate reference systems

    If allow_duplicates, a duplicated primary key does not raise - instead, all
    but the first occurrence of each duplicated key are dropped (independently
    in each source) before diffing, and returned separately as "DUPLICATES"
    (full source schema, plus a "_fcd_source_" column set to suffix_a/suffix_b
    identifying which source each record was dropped from).

    If promote_multi (the default) and the sources between them mix single and
    multipart geometries of the same base type (e.g. Point and MultiPoint),
    all geometries are promoted to multipart before comparison - so a feature
    stored single-part in one source and multi-part in the other compares as
    unchanged. Set promote_multi=False for stricter checking: geometries are
    compared as-is, and such a feature is reported as MODIFIED_GEOM.

    If strict_types, field types must match exactly - integer fields of
    differing width (e.g. Int32 vs Int64) raise rather than being compared as
    their smallest common type.

    Output diff is represented by six dataframes:
    - additions (with same schema as dataset b)
    - deletions (with same schema as dataset a)
    - modifications - geometry only (with same schema as dataset b)
    - modifications - attribute only (modified schema)
    - modifications - geometry and attribute (modified schema)
    - duplicates - records dropped due to a duplicated primary key (only
      non-empty if allow_duplicates)

    The attribute change dataframes include columns common to both sources, and
    for columns where changes have occurred, values from both sources (a column
    for each source).
    """
    (
        df_a,
        df_b,
        df_a_src,
        df_b_src,
        fields,
        spatial,
        duplicates_a,
        duplicates_b,
    ) = _validate_and_prepare_diff_inputs(
        df_a,
        df_b,
        primary_key,
        fields,
        ignore_fields,
        precision,
        allow_duplicates,
        promote_multi,
        strict_types,
    )
    duplicates_a["_fcd_source_"] = suffix_a
    duplicates_b["_fcd_source_"] = suffix_b
    if spatial:
        # duplicates_a/duplicates_b keep df_a_src's/df_b_src's own geometry
        # field name (almost always "geometry", but can genuinely differ for
        # a GeoParquet source - see the MODIFIED_GEOM handling below) - the
        # combined DUPLICATES table needs one consistent geometry column
        # regardless, since rows from both sources land in the same table
        if duplicates_a.geometry.name != "geometry":
            duplicates_a = duplicates_a.rename_geometry("geometry")
        if duplicates_b.geometry.name != "geometry":
            duplicates_b = duplicates_b.rename_geometry("geometry")
    duplicates = pandas.concat([duplicates_a, duplicates_b], ignore_index=True)
    if spatial and not isinstance(duplicates, geopandas.GeoDataFrame):
        duplicates = geopandas.GeoDataFrame(duplicates, geometry="geometry")

    # set pandas dataframe index to primary key
    df_a = df_a.set_index(primary_key)
    df_b = df_b.set_index(primary_key)

    # find additions / deletions by joining on indexes
    joined = df_a.merge(
        df_b,
        how="outer",
        left_index=True,
        right_index=True,
        suffixes=["_a", "_b"],
        indicator=True,
    )

    # extract additions/deletions, and retain just the primary key.
    # We join back to sources later - in order to retain all columns,
    # not just those being compared/common to both sources.
    additions = pandas.DataFrame(index=joined[joined["_merge"] == "right_only"].index)
    deletions = pandas.DataFrame(index=joined[joined["_merge"] == "left_only"].index)

    # create two dataframes holding records from respective source
    # that are common to both sources (modifications/unchanged)
    common = joined[joined["_merge"] == "both"]
    columns = list(df_a.columns)
    column_name_remap_a = {k + "_a": k for k in columns}
    column_name_remap_b = {k + "_b": k for k in columns}
    common_a = common.rename(columns=column_name_remap_a)[columns]
    common_b = common.rename(columns=column_name_remap_b)[columns]

    # compare the attributes
    if spatial:
        common_a_attrib = common_a.drop("geometry", axis=1)
        common_b_attrib = common_b.drop("geometry", axis=1)
        modified_attributes = common_a_attrib.compare(
            common_b_attrib,
            result_names=(
                suffix_a,
                suffix_b,
            ),
            keep_shape=False,
        ).dropna(axis=0, how="all")
    else:
        modified_attributes = common_a.compare(
            common_b,
            result_names=(
                suffix_a,
                suffix_b,
            ),
            keep_shape=False,
        ).dropna(axis=0, how="all")

    # flatten the resulting data structure
    modified_attributes.columns = [
        "_".join(a) for a in modified_attributes.columns.to_flat_index()
    ]

    # join back to geometries in b, creating attribute diff
    if spatial:
        modified_attributes = modified_attributes.merge(
            common_b["geometry"], how="inner", left_index=True, right_index=True
        ).set_geometry("geometry")

        # note the columns generated
        attribute_diff_columns = list(modified_attributes.columns.values)

        # find all rows with modified geometries, retaining new geometries only
        common_mod_geoms = common.rename(columns=column_name_remap_b)[columns]
        modified_geometries = common_mod_geoms[
            ~common_a.normalize().geom_equals_exact(common_b.normalize(), precision)
        ]

        # join modified attributes to modified geometries,
        # creating a data structure containing all modifications, where _merge indicates
        # into which set we want to place the modifications:
        # - "both": attributes and geometries have been modified
        # - "left_only": only attributes have been modified
        # - "right_only": only geometries have been modified
        # the dataframe includes two sets of geometries -
        # _x: from modified_attributes
        # _y: from modified_geometries
        modified_attributes_geometries = modified_attributes.merge(
            modified_geometries,
            how="outer",
            left_index=True,
            right_index=True,
            indicator=True,
        )

        # generate the output modifications dataframes

        # modified attributes retains left geom from above join
        m_attributes = (
            modified_attributes_geometries[
                modified_attributes_geometries["_merge"] == "left_only"
            ]
            .rename(columns={"geometry_x": "geometry"})[attribute_diff_columns]
            .set_geometry("geometry")
            .reset_index(drop=False)
        )

        # modified attributes and geometries retains either geometry
        m_attributes_geometries = (
            modified_attributes_geometries[
                modified_attributes_geometries["_merge"] == "both"
            ]
            .rename(columns={"geometry_x": "geometry"})[attribute_diff_columns]
            .set_geometry("geometry")
            .reset_index(drop=False)
        )

        # modified geoms only - retain just geometry (and primary key as index)
        m_geometries = (
            modified_attributes_geometries[
                modified_attributes_geometries["_merge"] == "right_only"
            ]
            .rename(columns={"geometry_y": "geometry"})[["geometry"]]
            .set_geometry("geometry")
            .reset_index(drop=False)
            .set_index(primary_key)
        )
    else:
        m_attributes = modified_attributes.reset_index(drop=False)
        # no spatial changes, return empty geodataframes for geometry diffs
        m_attributes_geometries = geopandas.GeoDataFrame(
            columns=["geometry"], geometry="geometry"
        )
        m_geometries = geopandas.GeoDataFrame(columns=["geometry"], geometry="geometry")

    # generate unchanged dataframe
    # (there is probably a more concise method to do this)
    # tag status of rows in each source dataframe
    if spatial:
        modifications = modified_attributes_geometries
    else:
        modifications = modified_attributes

    modifications["_fcd_status_"] = "modifications"
    additions["_fcd_status_"] = "additions"
    deletions["_fcd_status_"] = "deletions"
    # concatenate ids of all changes into a single dataframe, tagged by status of change
    changes = pandas.concat(
        [
            additions["_fcd_status_"],
            deletions["_fcd_status_"],
            modifications["_fcd_status_"],
        ]
    )

    # Where we have just the pk/indexes (additions/deletions/modifications),
    # join back to source datasets to include all source fields in the output

    # first, note fields and order in sources
    fields_a_src = list(df_a_src.columns)
    fields_b_src = list(df_b_src.columns)

    # next, set index of source datasets to enable joining back to results
    df_a_src = df_a_src.set_index(primary_key)
    df_b_src = df_b_src.set_index(primary_key)

    # do the joins, retain columns of interest, drop index
    unchanged = df_a_src.merge(
        changes, how="outer", left_index=True, right_index=True, indicator=True
    )
    unchanged = unchanged[unchanged["_merge"] == "left_only"]
    unchanged[primary_key] = unchanged.index
    unchanged = unchanged[fields_a_src].reset_index(drop=True)

    additions = df_b_src.merge(
        additions, how="inner", left_index=True, right_index=True
    )
    additions[primary_key] = additions.index
    additions = additions[fields_b_src].reset_index(drop=True)

    deletions = df_a_src.merge(
        deletions, how="inner", left_index=True, right_index=True
    )
    deletions[primary_key] = deletions.index
    deletions = deletions[fields_a_src].reset_index(drop=True)

    # also join modifications_geom back to source b layer (to preserve source schema)
    # this output will be empty for non-spatial comparisons - and therefore not written to file.
    # so, for non-spatial, matching the schema is not required
    if spatial:
        # df_b_src's own geometry field name (fields_b_src, captured above,
        # already reflects it) - almost always "geometry", but can genuinely
        # differ from df_a_src's/the "geometry"-named comparison copies' for
        # a GeoParquet source read with its native column name preserved
        # (every other format is normalized to "geometry" on read regardless
        # of its own internal name, so this only matters for parquet)
        geom_field_b = df_b_src.geometry.name
        df_b_src = df_b_src.drop(columns=[geom_field_b])
        m_geometries = df_b_src.merge(
            m_geometries.rename(columns={"geometry": geom_field_b}),
            how="inner",
            left_index=True,
            right_index=True,
        )
        m_geometries[primary_key] = m_geometries.index
        m_geometries = m_geometries[fields_b_src].reset_index(drop=True)
        m_geometries = geopandas.GeoDataFrame(m_geometries, geometry=geom_field_b)

    if return_type == "gdf":
        return {
            "NEW": additions,
            "DELETED": deletions,
            "UNCHANGED": unchanged,
            "MODIFIED_BOTH": m_attributes_geometries,
            "MODIFIED_ATTR": m_attributes,
            "MODIFIED_GEOM": m_geometries,
            "DUPLICATES": duplicates,
        }


def _read_and_diff(
    file_a,
    file_b,
    *,
    layer_a,
    layer_b,
    primary_key,
    fields,
    ignore_fields,
    suffix_a,
    suffix_b,
    drop_null_geometry,
    crs,
    hash_key,
    hash_fields,
    precision,
    allow_duplicates=False,
    promote_multi=True,
    strict_types=False,
):
    """Read both sources, resolve/hash the primary key, and run gdf_diff.

    Shared by diff_to_gdb() (writes results to .gdb) and diff_to_json() (prints a JSON
    summary) - everything up to producing the diff dict is identical between them;
    only what they do with the result differs.

    Returns (diff, df_a, df_b, primary_key, hashed) - df_a/df_b are the loaded,
    hash-keyed (if applicable) sources; primary_key is always a single field name
    on return (a generated hash_key if none was supplied); hashed indicates
    whether a hash key was generated (diff_to_gdb() uses this to force dump_inputs).
    """
    if fields is None:
        fields = []
    if ignore_fields is None:
        ignore_fields = []
    if hash_fields is None:
        hash_fields = []

    if file_a == "-" and file_b == "-":
        raise ValueError("Only one of file_a/file_b may be read from stdin")

    # load source data (src_a/src_b are shortcuts to source layer paths for logging)
    df_a, src_a = _read_source(file_a, layer_a, "a")
    df_b, src_b = _read_source(file_b, layer_b, "b")

    # promote mixed single/multipart geometries and drop ESRI-reserved id
    # fields (see _prepare_sources) before anything else: this df_a/df_b pair
    # is what dump_inputs writes directly to .gdb, and (for the geometry
    # promotion) also what gets hashed below - a mixed source hashed on raw
    # (unpromoted) geometry would hash a feature stored single-part in one
    # source and multi-part in the other to different values, spuriously
    # reporting it as NEW+DELETED instead of UNCHANGED (unless promote_multi
    # is disabled, in which case that is the intended, stricter, result).
    keep_fields = {f.upper() for f in fields + hash_fields}
    if primary_key:
        keep_fields.add(primary_key.upper())
    df_a, df_b = _prepare_sources(
        df_a, df_b, keep_fields, suffix_a, suffix_b, promote_multi=promote_multi
    )

    if primary_key:
        # hash_fields only has meaning when hashing (no primary key given) -
        # reject the combination outright rather than silently ignoring it
        if hash_fields:
            raise ValueError(
                f"hash_fields {hash_fields} has no effect when a primary_key is supplied - "
                "remove one or the other"
            )
        # drop_null_geometry only has meaning once a hash key is generated -
        # an explicit primary_key is always used directly (never hashed), so
        # the option has nothing to act on
        if drop_null_geometry:
            raise ValueError(
                "drop_null_geometry has no effect when a primary_key is supplied "
                "(no hash key is generated in that case) - remove it"
            )

    # if no primary key provided, link the two datasets by hashing on
    # hash_fields - the complete list of fields to include in the hash,
    # including the geometry field's name (df_a.geometry.name/df_b.geometry.name,
    # typically "geometry") if geometry is to be included
    else:
        if not hash_fields:
            raise ValueError(
                "No primary_key supplied - specify hash_fields (the complete list of "
                "fields to hash on, including the geometry field's name if geometry is "
                "to be included) to generate a hash key for linking datasets"
            )
        LOG.warning(f"No primary key supplied, hashing on fields {hash_fields}")

    # validate that provided fields/pk/hash columns are present in data
    for source in [(src_a, df_a), (src_b, df_b)]:
        # fail if fields/hash fields/pk are not present - hint at the actual
        # geometry field name, in case a misnamed geometry field (eg
        # "Shape"/"SHAPE" from ArcGIS habit) is the cause
        for fieldname in fields + hash_fields + ([primary_key] if primary_key else []):
            if fieldname not in source[1].columns:
                hint = ""
                if isinstance(source[1], geopandas.GeoDataFrame):
                    hint = f" - this dataset's geometry field is named '{source[1].geometry.name}'"
                raise ValueError(
                    f"Field {fieldname} is not present in {source[0]}{hint}"
                )

        # if ignore_fields are not present in data, just warn
        for fieldname in ignore_fields:
            if fieldname not in source[1].columns:
                LOG.warning(
                    f"Field {fieldname} is not present in {source[0]}, nothing to ignore"
                )

    # if specified, reproject both sources
    if crs:
        if isinstance(df_a, geopandas.GeoDataFrame):
            df_a = df_a.to_crs(crs)
        else:
            raise ValueError(f"Cannot reproject {src_a}, no geometries present")
        if isinstance(df_b, geopandas.GeoDataFrame):
            df_b = df_b.to_crs(crs)
        else:
            raise ValueError(f"Cannot reproject {src_b}, no geometries present")

    # add hashed key, on hash_fields, if no primary key was given (hash_fields
    # must include the geometry field's name to hash on geometry). allow_duplicates
    # is passed through so a hash collision (two records hashing identically
    # within one source) is deferred to gdf_diff's own duplicate-primary-key
    # handling below, rather than raising here
    hashed = False
    if not primary_key:
        LOG.info(f"Adding hashed key to source_{suffix_a} as {hash_key}")
        df_a = fcd.add_hash_key(
            df_a,
            new_field=hash_key,
            fields=hash_fields,
            precision=precision,
            drop_null_geometry=drop_null_geometry,
            allow_duplicates=allow_duplicates,
        )
        LOG.info(f"Adding hashed key to source_{suffix_b} as {hash_key}")
        df_b = fcd.add_hash_key(
            df_b,
            new_field=hash_key,
            fields=hash_fields,
            precision=precision,
            drop_null_geometry=drop_null_geometry,
            allow_duplicates=allow_duplicates,
        )
        primary_key = hash_key
        hashed = True

    # run the diff
    diff = fcd.gdf_diff(
        df_a,
        df_b,
        primary_key,
        fields=fields,
        ignore_fields=ignore_fields,
        precision=precision,
        suffix_a=suffix_a,
        suffix_b=suffix_b,
        allow_duplicates=allow_duplicates,
        promote_multi=promote_multi,
        strict_types=strict_types,
    )

    return diff, df_a, df_b, primary_key, hashed


def diff_to_json(
    file_a,
    file_b,
    layer_a,
    layer_b,
    *,
    primary_key=None,
    fields=None,
    ignore_fields=None,
    suffix_a="a",
    suffix_b="b",
    drop_null_geometry=None,
    crs=None,
    hash_key="fcd_hash_id",
    hash_fields=None,
    precision=0.01,
    counts_only=False,
    out_file=None,
    allow_duplicates=False,
    promote_multi=True,
    strict_types=False,
):
    """
    Compare two datasets, print a JSON summary to stdout (or write it to
    out_file, if provided).

    By default, includes record counts per category plus a "keys" section
    listing the primary key value(s) present in each category except UNCHANGED
    (the tool reports changes - unchanged keys would just be clutter, and
    diff_to_gdb() doesn't write them either). If counts_only, print just the
    counts.

    The "DUPLICATES" category (see allow_duplicates) is only included when
    allow_duplicates is True - otherwise it's always empty (a duplicated
    primary key raises instead), so including it would just be clutter.

    See gdf_diff for promote_multi and strict_types.
    """
    result, _, _, resolved_primary_key, _ = _read_and_diff(
        file_a,
        file_b,
        layer_a=layer_a,
        layer_b=layer_b,
        primary_key=primary_key,
        fields=fields,
        ignore_fields=ignore_fields,
        suffix_a=suffix_a,
        suffix_b=suffix_b,
        drop_null_geometry=drop_null_geometry,
        crs=crs,
        hash_key=hash_key,
        hash_fields=hash_fields,
        precision=precision,
        allow_duplicates=allow_duplicates,
        promote_multi=promote_multi,
        strict_types=strict_types,
    )
    if not allow_duplicates:
        del result["DUPLICATES"]
    summary = {key: len(df) for key, df in result.items()}
    if not counts_only:
        summary["keys"] = {
            key: df[resolved_primary_key].tolist()
            for key, df in result.items()
            if key != "UNCHANGED"
        }
    if out_file:
        LOG.info(f"Writing JSON summary to {out_file}")
        with open(out_file, "w") as f:
            json.dump(summary, f)
    else:
        print(json.dumps(summary))


def diff_to_gdb(
    file_a,
    file_b,
    layer_a,
    layer_b,
    out_file,
    *,
    primary_key=None,
    fields=None,
    ignore_fields=None,
    suffix_a="a",
    suffix_b="b",
    drop_null_geometry=None,
    crs=None,
    hash_key="fcd_hash_id",
    hash_fields=None,
    precision=0.01,
    dump_inputs=False,
    allow_duplicates=False,
    promote_multi=True,
    strict_types=False,
):
    """
    Compare two datasets:
      - open two data sources, load to geopandas dataframes (gdf)
      - if no primary key specified, add one to each gdf as new column based
        on a hash of hash_fields (the complete list of fields to hash,
        including the geometry field's name if geometry is to be included)
      - compare the datasets with gdf_diff, assigning input records to one of:
         + NEW
         + DELETED
         + UNCHANGED
         + MODIFIED_BOTH
         + MODIFIED_ATTR
         + MODIFED_GEOM
         + DUPLICATES (only if allow_duplicates - records dropped due to a
           duplicated primary key)
      - write results to .gdb

    See gdf_diff for promote_multi and strict_types.
    """
    diff, df_a, df_b, primary_key, hashed = _read_and_diff(
        file_a,
        file_b,
        layer_a=layer_a,
        layer_b=layer_b,
        primary_key=primary_key,
        fields=fields,
        ignore_fields=ignore_fields,
        suffix_a=suffix_a,
        suffix_b=suffix_b,
        drop_null_geometry=drop_null_geometry,
        crs=crs,
        hash_key=hash_key,
        hash_fields=hash_fields,
        precision=precision,
        allow_duplicates=allow_duplicates,
        promote_multi=promote_multi,
        strict_types=strict_types,
    )
    if hashed:
        dump_inputs = True

    # a .gdb layer holds a single geometry type, so sources mixing base types
    # (within or between them - e.g. DUPLICATES combines records from both)
    # are not supported. Single/multipart of one base type are fine - they
    # were already promoted to multipart, unless promote_multi is disabled,
    # in which case promote them on write (the comparison is already done,
    # so this affects output only). See fcd.gdb_write_options for the rest.
    write_opts = dict(fcd.gdb_write_options)
    if isinstance(df_a, geopandas.GeoDataFrame):
        types = _geom_types(df_a) | _geom_types(df_b)
        base_types = {t.removeprefix("Multi") for t in types}
        if len(base_types) > 1:
            raise ValueError(
                f"Sources mix geometry types {sorted(base_types)} - .gdb output "
                "requires a single geometry type across both sources"
            )
        if _has_mixed_single_multipart(types):
            write_opts["promote_to_multi"] = True

    # default output is changedetector_YYYYMMDD_HHMM.gdb (local time, human readable)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")  # noqa: DTZ005
    if not out_file:
        out_file = f"changedetector_{timestamp}.gdb"

    # write output data
    mode = "w"  # for writing the first non-empty layer, subsequent writes are appends

    if os.path.exists(out_file):
        LOG.warning(f"{out_file} exists in - overwriting")
        shutil.rmtree(out_file)

    # squelch pyogrio INFO logs
    logging.getLogger("pyogrio._io").setLevel(logging.WARNING)

    for key in [
        "NEW",
        "DELETED",
        "MODIFIED_BOTH",
        "MODIFIED_ATTR",
        "MODIFIED_GEOM",
        "DUPLICATES",
    ]:
        LOG.info(f"{key}: {len(diff[key])} records")
        if len(diff[key]) > 0:
            # add empty geometry column for writing non-spatial data to .gpkg
            # (does not work for .gdb driver, .gdb output fails with non-spatial data).
            # Checked via isinstance rather than a literal "geometry" column
            # name - a spatial result's geometry column is not always named
            # "geometry" (NEW/DELETED/UNCHANGED/MODIFIED_GEOM preserve each
            # source's own schema, which for a GeoParquet source can
            # genuinely use a different name)
            if not isinstance(diff[key], geopandas.GeoDataFrame):
                diff[key] = geopandas.GeoDataFrame(
                    diff[key], geometry=geopandas.GeoSeries([None] * len(diff[key]))
                )
            diff[key].to_file(
                out_file, driver="OpenFileGDB", layer=key, mode=mode, **write_opts
            )
            mode = "a"

    # re-write source datasets if new pk generated (and some kind of output generated)
    if dump_inputs and mode == "a":
        LOG.info(
            f"Writing source data to {out_file}, with geometry hash key {hash_key}"
        )
        df_a.to_file(
            out_file,
            driver="OpenFileGDB",
            layer="source_" + suffix_a,
            mode="a",
            **write_opts,
        )
        df_b.to_file(
            out_file,
            driver="OpenFileGDB",
            layer="source_" + suffix_b,
            mode="a",
            **write_opts,
        )
