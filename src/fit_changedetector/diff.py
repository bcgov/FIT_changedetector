import hashlib
import logging
import os
import shutil
from datetime import datetime

import geopandas
import pandas

import fit_changedetector as fcd

LOG = logging.getLogger(__name__)


def add_hash_key(
    df,
    new_field,
    fields=[],
    hash_geometry=True,
    drop_null_geometry=True,
    precision=0.01,
):
    """Add new column to input dataframe, containing hash of input columns and/or geometry"""
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
    if not fields and not hash_geometry:
        raise ValueError("Nothing to hash, specify hash_geometry and/or columns to hash")

    # Fail if attempting include a geometry based column in fields [],
    # this information wil be captured by the geometry
    for f in fields:
        if f in fcd.area_length_fields:
            raise ValueError(
                f"Cannot hash field {f}, hashing on area/length fields is not supported"
            )

    # If using default precision of 1cm on data using degrees,
    # presume this is an oversight, warn and adjust.
    # (if non-default precision is provided, presume that the user is right)
    if df.geometry.crs.is_geographic and precision == 0.01:
        LOG.warning(
            "Data is projected in degrees, default precision of 0.01m specified. "
            "Adjusting to .0000001 degrees"
        )
        precision = 0.0000001

    # if hashing the geometry, ensure no nulls are present and standardize ring order/precision
    if hash_geometry:
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
        df["geometry_normalized"] = (
            df[df.geometry.name].normalize().set_precision(precision, mode="pointwise")
        )
        fields = fields + ["geometry_normalized"]

    # add sha1 hash of provided fields
    df[new_field] = df[fields].apply(
        lambda x: hashlib.sha1(
            "|".join(x.astype(str).fillna("NULL").values).encode("utf-8")
        ).hexdigest(),
        axis=1,
    )

    # remove the normalized/reduced precision geometry
    if hash_geometry:
        df = df.drop(columns=["geometry_normalized"])

    # fail if hashes are not unique
    if len(df) != len(df[new_field].drop_duplicates()):
        if fields == ["geometry_normalized"]:
            raise ValueError(
                "Duplicate geometries are present in source, consider adding more columns to hash "
                "or editing data"
            )
        else:
            raise ValueError(
                "Duplicate values for output hash are present, consider adding more columns to hash "
                "or editing data"
            )
    return df


def gdf_diff(
    df_a,
    df_b,
    primary_key,
    fields=[],
    ignore_fields=[],
    precision=0.01,
    suffix_a="a",
    suffix_b="b",
    return_type="gdf",
):
    """
    Compare two geodataframes and generate a diff.

    Sources MUST:
    - have valid, compatible primary keys
    - have at least one equivalent column (ok if this is just the primary key)
    - equivalent column names must be of equivalent types
    - have equivalent geometry types and coordinate reference systems

    Output diff is represented by five dataframes:
    - additions (with same schema as dataset b)
    - deletions (with same schema as dataset a)
    - modifications - geometry only (with )
    - modifications - attribute only
    - modifications - geometry and attribute

    The attribute change dataframes include values from both sources.
    """
    # are input datasets spatial?
    if isinstance(df_a, geopandas.GeoDataFrame) and isinstance(df_b, geopandas.GeoDataFrame):
        spatial = True
    elif isinstance(df_a, geopandas.GeoDataFrame) and not isinstance(df_b, geopandas.GeoDataFrame):
        raise ValueError(
            "Cannot compare spatial and non-spatial sources - spatial component found in source 1 "
            "but not in source 2."
        )
    elif isinstance(df_b, geopandas.GeoDataFrame) and not isinstance(df_a, geopandas.GeoDataFrame):
        raise ValueError(
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

    # standardize geometry column name
    if spatial and df_a.geometry.name != "geometry":
        df_a = df_a.rename_geometry("geometry")
    if spatial and df_b.geometry.name != "geometry":
        df_b = df_b.rename_geometry("geometry")

    # drop esri generated area/length fields
    for f in df_a.columns:
        if f.upper() in fcd.area_length_fields:
            df_a = df_a.drop(columns=[f])
    for f in df_b.columns:
        if f.upper() in fcd.area_length_fields:
            df_b = df_b.drop(columns=[f])

    # after making above tweaks, retain a full copy of sources for writing
    # all source fields to NEW/UNCHANGED/DELETED (not just common fields
    # used for comparison)
    df_a_src = df_a.copy()
    df_b_src = df_b.copy()

    ignore_fields = list(set([f.upper() for f in ignore_fields]))

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
        fields = list(set(fields + [primary_key]))
        if len(set(fields).intersection(fields_common)) != len(fields):
            raise ValueError("Provided fields are not common to both datasets")
    else:
        fields = list(fields_common)

    # remove ignore_fields from comparison
    for f in fields:
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

    # are general data types of the common fields equivalent?
    if list(df_a.dtypes) != list(df_b.dtypes):
        raise ValueError("Field types do not match")

    # are geometry data types equivalent?
    if spatial:
        geomtypes_a = set(
            [t.upper() for t in df_a.geometry.geom_type.dropna(axis=0, how="all").unique()]
        )
        geomtypes_b = set(
            [t.upper() for t in df_b.geometry.geom_type.dropna(axis=0, how="all").unique()]
        )

        if geomtypes_a != geomtypes_b:
            raise ValueError(
                f"Geometry types {','.join(list(geomtypes_a))} and {','.join(list(geomtypes_b))} "
                "are not equivalent"
            )

        # are CRS equivalent?
        if df_a.crs != df_b.crs:
            raise ValueError("Coordinate reference systems are not equivalent")

    # is primary key unique in both datasets?
    if len(df_a) != len(df_a[[primary_key]].drop_duplicates()):
        raise ValueError(
            f"Duplicate values exist for primary_key {primary_key}, in dataframe a, consider using "
            "another primary key or pre-processing to remove duplicates"
        )
    if len(df_b) != len(df_b[[primary_key]].drop_duplicates()):
        raise ValueError(
            f"Duplicate values exist for primary_key {primary_key}, in dataframe b, consider using "
            "another primary key or pre-processing to remove duplicates"
        )

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
    modified_attributes.columns = ["_".join(a) for a in modified_attributes.columns.to_flat_index()]

    # join back to geometries in b, creating attribute diff
    if spatial:
        modified_attributes = modified_attributes.merge(
            common_b["geometry"], how="inner", left_index=True, right_index=True
        ).set_geometry("geometry")

        # note the columns generated
        attribute_diff_columns = list(modified_attributes.columns.values)

        # find all rows with modified geometries, retaining new geometries only
        common_mod_geoms = common.rename(columns=column_name_remap_b)[columns]
        modified_geometries = common_mod_geoms[~common_a.geom_equals_exact(common_b, precision)]

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

        # generate the output mofications dataframes

        # modified attributes retains left geom from above join
        m_attributes = (
            modified_attributes_geometries[modified_attributes_geometries["_merge"] == "left_only"]
            .rename(columns={"geometry_x": "geometry"})[attribute_diff_columns]
            .set_geometry("geometry")
            .reset_index(drop=False)
        )

        # modified attributes and geometries retains either geometry
        m_attributes_geometries = (
            modified_attributes_geometries[modified_attributes_geometries["_merge"] == "both"]
            .rename(columns={"geometry_x": "geometry"})[attribute_diff_columns]
            .set_geometry("geometry")
            .reset_index(drop=False)
        )

        # modified geoms only, using source column names
        m_geometries = (
            modified_attributes_geometries[modified_attributes_geometries["_merge"] == "right_only"]
            .rename(columns={"geometry_y": "geometry"})[columns]
            .set_geometry("geometry")
            .reset_index(drop=False)
        )
    else:
        m_attributes = modified_attributes.reset_index(drop=False)
        # no spatial changes, return empty geodataframes for geometry diffs
        m_attributes_geometries = geopandas.GeoDataFrame(columns=["geometry"], geometry="geometry")
        m_geometries = geopandas.GeoDataFrame(columns=["geometry"], geometry="geometry")

    # generate unchanged dataframe
    # (there is probably a more concise method to do this)
    # tag status of rows in each source dataframe
    if spatial:
        modifications = modified_attributes_geometries
    else:
        modifications = modified_attributes

    modifications["status"] = "modifications"
    additions["status"] = "additions"
    deletions["status"] = "deletions"
    # concatenate ids of all changes into a single dataframe, tagged by status of change
    changes = pandas.concat(
        [
            additions["status"],
            deletions["status"],
            modifications["status"],
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

    additions = df_b_src.merge(additions, how="inner", left_index=True, right_index=True)
    additions[primary_key] = additions.index
    additions = additions[fields_b_src].reset_index(drop=True)

    deletions = df_a_src.merge(deletions, how="inner", left_index=True, right_index=True)
    deletions[primary_key] = deletions.index
    deletions = deletions[fields_a_src].reset_index(drop=True)

    if return_type == "gdf":
        return {
            "NEW": additions,
            "DELETED": deletions,
            "UNCHANGED": unchanged,
            "MODIFIED_BOTH": m_attributes_geometries,
            "MODIFIED_ATTR": m_attributes,
            "MODIFIED_GEOM": m_geometries,
        }


def compare(
    in_file_a,
    in_file_b,
    layer_a,
    layer_b,
    out_file,
    primary_key=[],
    fields=None,
    suffix_a="a",
    suffix_b="b",
    drop_null_geometry=True,
    crs=None,
    hash_key=None,
    hash_fields=[],
    precision=0.01,
    dump_inputs=False,
):
    # shortcuts to source layer paths for logging
    src_a = os.path.join(in_file_a, layer_a or "")
    src_b = os.path.join(in_file_b, layer_b or "")

    # load source data
    df_a = geopandas.read_file(in_file_a, layer=layer_a)
    df_b = geopandas.read_file(in_file_b, layer=layer_b)

    # default output is changedetector_YYYYMMDD_HHMM.gdb
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    if not out_file:
        out_file = f"changedetector_{timestamp}.gdb"

    # any time a pk is supplied, presume that we do not hash geometry
    if primary_key:
        hash_geometry = False

        # and ignore any supplied hash fields
        if hash_fields:
            LOG.warning(
                f"Using supplied primary key {primary_key} and ignoring supplied hash_fields {hash_fields}"
            )
            hash_fields = []

    # if no primary key provided, link the two datasets by presuming geometries are the same
    # (hash on geometry)
    else:
        LOG.warning(
            "No primary key supplied, script will attempt to hash on geometries (and hash_fields, "
            "if specified)"
        )
        # are there geometries in both datasets?
        if isinstance(df_a, geopandas.GeoDataFrame) and isinstance(df_a, geopandas.GeoDataFrame):
            hash_geometry = True
        else:
            raise ValueError(
                "Cannot compare the datasets - if no primary key is available, geometries must be "
                "present in both source datasets"
            )

    # validate that provided fields/pk/hash columns are present in data
    for source in [(src_a, df_a), (src_b, df_b)]:
        for fieldname in fields + hash_fields + primary_key:
            if fieldname not in source[1].columns:
                raise ValueError(f"Field {fieldname} is not present in {source[0]}")

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

    # add hashed key
    # - hash multi column primary keys (without geom) for simplicity
    # - hash with geometry if no primary key specified
    if hash_geometry or len(primary_key) > 1:
        LOG.info(f"Adding hashed key (synthetic primary key) to {src_a} as {hash_key}")
        df_a = fcd.add_hash_key(
            df_a,
            new_field=hash_key,
            fields=primary_key + hash_fields,
            hash_geometry=hash_geometry,
            precision=precision,
            drop_null_geometry=drop_null_geometry,
        )
        LOG.info(f"Adding hashed key (synthetic primary key) to {src_b} as {hash_key}")
        df_b = fcd.add_hash_key(
            df_b,
            new_field=hash_key,
            fields=primary_key + hash_fields,
            hash_geometry=hash_geometry,
            precision=precision,
            drop_null_geometry=drop_null_geometry,
        )
        primary_key = [hash_key]
        dump_inputs = True

    # run the diff
    diff = fcd.gdf_diff(
        df_a,
        df_b,
        primary_key[0],  # pk is always a single column after above processing
        fields=fields,
        precision=precision,
        suffix_a=suffix_a,
        suffix_b=suffix_b,
    )

    # write output data
    mode = "w"  # for writing the first non-empty layer, subsequent writes are appends

    if os.path.exists(out_file):
        LOG.warning(f"{out_file} exists in - overwriting")
        shutil.rmtree(out_file)

    for key in ["NEW", "DELETED", "MODIFIED_BOTH", "MODIFIED_ATTR", "MODIFIED_GEOM"]:
        LOG.info(f"{key}: {len(diff[key])} records")
        if len(diff[key]) > 0:
            # add empty geometry column for writing non-spatial data to .gpkg
            # (does not work for .gdb driver, .gdb output fails with non-spatial data)
            if "geometry" not in diff[key].columns:
                diff[key] = geopandas.GeoDataFrame(
                    diff[key], geometry=geopandas.GeoSeries([None] * len(diff[key]))
                )
            diff[key].to_file(out_file, driver="OpenFileGDB", layer=key, mode=mode)
            mode = "a"

    # re-write source datasets if new pk generated (and some kind of output generated)
    if dump_inputs and mode == "a":
        LOG.info(f"Writing source data to {out_file}, with geometry hash key {hash_key}")
        df_a.to_file(out_file, driver="OpenFileGDB", layer="source_" + suffix_a, mode="a")
        df_b.to_file(out_file, driver="OpenFileGDB", layer="source_" + suffix_b, mode="a")
