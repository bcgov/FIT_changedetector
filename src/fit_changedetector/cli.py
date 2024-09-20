import logging
import os
import sys
import shutil

import click
from cligj import verbose_opt, quiet_opt
import geopandas

import fit_changedetector as fcd

LOG = logging.getLogger(__name__)

def configure_logging(verbosity):
    log_level = max(10, 30 - 10 * verbosity)
    logging.basicConfig(
        stream=sys.stderr,
        level=log_level,
        format="%(asctime)s:%(levelname)s:%(name)s: %(message)s",
    )

@click.command()
@click.argument("in_file_a", type=click.Path(exists=True))
@click.argument("in_file_b", type=click.Path(exists=True))
@click.option("--layer_a")
@click.option("--layer_b")
@click.option(
    "--fields",
    "-f",
    help="Comma separated list of fields to compare (do not include primary key)",
)
@click.option(
    "--out-path",
    "-o",
    type=click.Path(),
    default=".",
    help="Output path",
)
@click.option(
    "--primary-key",
    "-k",
    multiple=True,
    help="Primary key column(s), common to both datasets",
)
@click.option(
    "--precision",
    "-p",
    default=0.001,
    help="Precision to use when comparing geometries",
)
@click.option(
    "--suffix_a",
    "-a",
    default="a",
    help="Suffix to append to column names from data source A when comparing attributes",
)
@click.option(
    "--suffix_b",
    "-b",
    default="b",
    help="Suffix to append to column names from data source B when comparing attributes",
)
@verbose_opt
@quiet_opt
def changedetector(
    in_file_a,
    in_file_b,
    layer_a,
    layer_b,
    primary_key,
    fields,
    out_path,
    precision,
    suffix_a,
    suffix_b,
    verbose,
    quiet,
):
    """Compare two datasets"""
    configure_logging((verbose - quiet))

    # load source data
    df_a = geopandas.read_file(in_file_a, layer=layer_a)
    df_b = geopandas.read_file(in_file_b, layer=layer_b)

    # is pk present in both sources?
    if primary_key:
        primary_key = list(primary_key)
        if not bool(set(primary_key) & set(df_a.columns)):
            raise ValueError(
                f"Primary key {','.join(primary_key)} not present in {in_file_a}"
            )
        if not bool(set(primary_key) & set(df_b.columns)):
            raise ValueError(
                f"Primary key {','.join(primary_key)} not present in {in_file_b}"
            )

        # is pk unique in both sources? If not, append geom to pk
        if (len(df_a) != len(df_a[primary_key].drop_duplicates())) or (
            len(df_b) != len(df_b[primary_key].drop_duplicates())
        ):
            LOG.warning(
                f"Duplicate values exist for primary_key {primary_key}, appending geometry"
            )
            primary_key = primary_key + ["geometry_p"]
    else:
        primary_key = ["geometry_p"]

    # add slightly generalized geometry to primary key columns
    if "geometry_p" in primary_key:
        df_a["geometry_p"] = (
            df_a[df_a.geometry.name]
            .normalize()
            .set_precision(precision, mode="pointwise")
        )
        df_b["geometry_p"] = (
            df_b[df_b.geometry.name]
            .normalize()
            .set_precision(precision, mode="pointwise")
        )

    # generate new synthentic pk
    if "geometry_p" in primary_key or len(primary_key) > 1:
        LOG.info("Adding synthetic primary key fcd_id to both sources")
        df_a = fcd.add_synthetic_primary_key(df_a, primary_key, new_column="fcd_id")
        df_b = fcd.add_synthetic_primary_key(df_b, primary_key, new_column="fcd_id")
        primary_key = "fcd_id"
        # remove the temp geom
        df_a = df_a.drop(columns=["geometry_p"])
        df_b = df_b.drop(columns=["geometry_p"])
        dump_inputs_with_new_pk = True

    # otherwise, pick the pk from first (and only) item in the pk list
    else:
        primary_key = primary_key[0]
        dump_inputs_with_new_pk = False

    # if string of fields is provided, parse into list
    if fields:
        fields = fields.split(",")

    # run the diff
    diff = fcd.gdf_diff(
        df_a,
        df_b,
        primary_key,
        fields=fields,
        precision=precision,
        suffix_a=suffix_a,
        suffix_b=suffix_b,
    )

    # write output data
    mode = "w"  # for writing the first non-empty layer, subsequent writes are appends
    out_gdb = os.path.join(out_path, "changedetector.gdb")
    if os.path.exists(out_gdb):
        LOG.warning(f"changedetector.gdb exists in {out_path}, overwriting")
        shutil.rmtree(out_gdb)

    for key in [
        "NEW",
        "DELETED",
        "MODIFIED_BOTH",
        "MODIFIED_ATTR",
        "MODIFIED_GEOM",
        "MODIFIED_ALL",
    ]:
        if len(diff[key]) > 0:
            LOG.info(f"writing {key} to {out_gdb}")
            diff[key].to_file(out_gdb, driver="OpenFileGDB", layer=key, mode=mode)
            mode = "a"

    # re-write source datasets if new pk generated (and some kind of output generated)
    if dump_inputs_with_new_pk and mode == "a":
        df_a.to_file(
            out_gdb, driver="OpenFileGDB", layer="source_" + suffix_a, mode="a"
        )
        df_b.to_file(
            out_gdb, driver="OpenFileGDB", layer="source_" + suffix_b, mode="a"
        )

if __name__ == "__main__":
    changedetector()