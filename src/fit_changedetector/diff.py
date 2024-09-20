import hashlib
import logging

import geopandas
import fit_changedetector as fcd

LOG = logging.getLogger(__name__)


def add_synthetic_primary_key(df, columns, new_column):
    """add a synthetic primary key to provided dataframe based on hash of input columns"""
    # Fail if output column is already present in data
    if new_column in df.columns:
        raise ValueError(
            f"column {new_column} is present in input dataset, use some other column name"
        )

    # remove any duplicates
    n_dups = len(df) - len(df.drop_duplicates(subset=columns))
    if n_dups > 0:
        LOG.warning(f"Dropping {n_dups} duplicate rows")
        df = df.drop_duplicates(columns)

    # add sha1 hash of provided columns
    df[new_column] = df[columns].apply(
        lambda x: hashlib.sha1(
            "|".join(x.astype(str).fillna("NULL").values).encode("utf-8")
        ).hexdigest(),
        axis=1,
    )
    return df


def gdf_diff(
    df_a,
    df_b,
    primary_key,
    fields=None,
    precision=2,
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
    - additions
    - deletions
    - modifications - geometry only
    - modifications - attribute only
    - modifications - geometry and attribute

    The attribute change dataframes include values from both sources.
    """
    # standardize geometry column name
    if df_a.geometry.name != "geometry":
        df_a = df_a.rename_geometry("geometry")
    if df_b.geometry.name != "geometry":
        df_b = df_b.rename_geometry("geometry")

    # field names equivalent? (for fields of interest)
    fields_a = set([c for c in df_a.columns if c != "geometry"])
    fields_b = set([c for c in df_b.columns if c != "geometry"])
    fields_common = fields_a.intersection(fields_b)

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

    if len(fields) == 0:
        raise ValueError("Datasets have no field names in common, cannot compare")

    # remove all columns other than primary key, common fields of interest, and geometry
    df_a = df_a[fields + ["geometry"]]
    df_b = df_b[fields + ["geometry"]]

    # are general data types of the common fields equivalent?
    if list(df_a.dtypes) != list(df_b.dtypes):
        raise ValueError("Field types do not match")

    # are geometry data types equivalent (and valid)?
    geomtypes_a = set([t.upper() for t in df_a.geometry.geom_type.unique()])
    geomtypes_b = set([t.upper() for t in df_b.geometry.geom_type.unique()])

    if geomtypes_a != geomtypes_b:
        raise ValueError(
            f"Geometry types {','.join(list(geomtypes_a))} and {','.join(list(geomtypes_b))} are not equivalent"
        )

    # is CRS equivalent?
    if df_a.crs != df_b.crs:
        raise ValueError("Coordinate reference systems are not equivalent")

    # is primary key unique in both datasets?
    if len(df_a) != len(df_a[[primary_key]].drop_duplicates()):
        raise ValueError(
            f"Duplicate values exist for primary_key {primary_key}, in dataframe a, consider using another primary key or pre-processing to remove duplicates"
        )
    if len(df_b) != len(df_b[[primary_key]].drop_duplicates()):
        raise ValueError(
            f"Duplicate values exist for primary_key {primary_key}, in dataframe b, consider using another primary key or pre-processing to remove duplicates"
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
    additions = joined[joined["_merge"] == "right_only"]
    deletions = joined[joined["_merge"] == "left_only"]
    common = joined[joined["_merge"] == "both"]

    # clean column names in resulting dataframes
    columns = list(df_a.columns)
    column_name_remap_a = {k + "_a": k for k in columns}
    column_name_remap_b = {k + "_b": k for k in columns}
    # additions is data from source b
    additions = additions.rename(columns=column_name_remap_b)[columns]
    # deletions is data from source a
    deletions = deletions.rename(columns=column_name_remap_a)[columns]

    # create two dataframes holding records from respective source
    # that are common to both sources
    common_a = common.rename(columns=column_name_remap_a)[columns]
    common_b = common.rename(columns=column_name_remap_b)[columns]

    # compare the attributes
    common_a_attrib = common_a.drop("geometry", axis=1)
    common_b_attrib = common_b.drop("geometry", axis=1)
    modified_attributes = common_a_attrib.compare(
        common_b_attrib,
        result_names=(
            suffix_a,
            suffix_b,
        ),
        keep_shape=True,
    ).dropna(axis=0, how="all")

    # flatten the resulting data structure
    modified_attributes.columns = [
        "_".join(a) for a in modified_attributes.columns.to_flat_index()
    ]

    # join back to geometries in b, creating attribute diff
    modified_attributes = modified_attributes.merge(
        common_b["geometry"], how="inner", left_index=True, right_index=True
    ).set_geometry("geometry")

    # note the columns generated
    attribute_diff_columns = list(modified_attributes.columns.values)

    # find all rows with modified geometries, retaining new geometries only
    common_mod_geoms = common.rename(columns=column_name_remap_b)[columns]
    modified_geometries = common_mod_geoms[
        ~common_a.geom_equals_exact(common_b, precision)
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

    # generate the output mofications dataframes

    # modified attributes retains left geom from above join
    m_attributes = (
        modified_attributes_geometries[
            modified_attributes_geometries["_merge"] == "left_only"
        ]
        .rename(columns={"geometry_x": "geometry"})[attribute_diff_columns]
        .set_geometry("geometry")
    )

    # modified attributes and geometries retains either geometry
    m_attributes_geometries = (
        modified_attributes_geometries[
            modified_attributes_geometries["_merge"] == "both"
        ]
        .rename(columns={"geometry_x": "geometry"})[attribute_diff_columns]
        .set_geometry("geometry")
    )

    # modified geoms only, using source column names
    m_geometries = (
        modified_attributes_geometries[
            modified_attributes_geometries["_merge"] == "right_only"
        ]
        .rename(columns={"geometry_y": "geometry"})[columns]
        .set_geometry("geometry")
    )

    if return_type == "gdf":
        return {
            "NEW": additions,
            "DELETED": deletions,
            "UNCHANGED": [],
            "MODIFIED_BOTH": m_attributes_geometries,
            "MODIFIED_ATTR": m_attributes,
            "MODIFIED_GEOM": m_geometries,
            "MODIFIED_ALL": [],
            "ALL_CHANGES": [],
            "MODIFIED_BOTH_OBSLT": [],
            "MODIFIED_ATTR_OBSLT": [],
            "MODIFIED_GEOM_OBSLT": [],
        }
