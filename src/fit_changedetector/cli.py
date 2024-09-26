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

@click.group()
@click.version_option(version=fcd.__version__, message="%(version)s")
def cli():
    pass

@cli.command()
@click.argument("in_file", type=click.Path(exists=True))
@click.option("--layer", help="Name of layer to add hashed primary key")
@click.option(
    "--fields",
    "-f",
    help="Comma separated list of fields to include in the hash (not including geometry)",
)
@click.option(
    "--out-file",
    "-o",
    type=click.Path(),
    help="Output filename",
)
@click.option(
    "--out-layer",
    "-nln",
    help="Output layer name",
)
@click.option(
    "--hash-column",
    "-k",
    default="fcd_hash_id",
    help="Name of new column containing hashed data",
)
@verbose_opt
@quiet_opt
def add_hash_key(in_file, layer, fields, out_file, out_layer, hash_column, verbose, quiet):
    """Add hash of input columns and geometry to new column
    """
    configure_logging((verbose - quiet))
    df = geopandas.read_file(in_file, layer=layer)
    # validate provide fields
    if fields:
        fields = fields.split(",")
        for field in fields:
            if field not in df.columns:
                src = os.path.join(in_file, layer)
                raise ValueError(f"Field {field} is not present in {src}")
    df = fcd.add_hash_key(df, hash_column, fields=fields, hash_geometry=True)
    # todo - support overwrite of existing files? appending to existing gdb?
    if os.path.exists(out_file):
        raise ValueError(f"Output file {out_file} exists.")
    # default to naming output layer the same as input layer (if supplied)
    if not out_layer and layer:
        LOG.warning(f"No output layer name specified, using {layer}")
        out_layer = layer
    elif not out_layer:
        raise ValueError(f"Output layer name is required if no input layer is specified")
    LOG.info(f"Writing new dataset {out_file} with new hash based column {hash_column}")
    df.to_file(out_file, driver="OpenFileGDB", layer=out_layer)


@cli.command()
@click.argument("in_file_a", type=click.Path(exists=True))
@click.argument("in_file_b", type=click.Path(exists=True))
@click.option("--layer_a", help="Name of layer to use within in_file_a")
@click.option("--layer_b", help="Name of layer to use within in_file_b")
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
    default=0.01,
    help="Coordinate precision to use when comparing geometries (defaults to .01)",
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
def compare(
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

    # default to not hashing geoms
    hash_geometry = False

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

        # is pk unique in both sources? If not, warn and create hash key based on pk AND geom
        if (len(df_a) != len(df_a[primary_key].drop_duplicates())) or (
            len(df_b) != len(df_b[primary_key].drop_duplicates())
        ):
            LOG.warning(
                f"Duplicate values exist for primary_key {primary_key}, appending geometry"
            )
            hash_geometry = True
    
    # if no pk supplied, simply hash on geometry
    else:
        hash_geometry = True

    # add hashed key if using geometry or if supplied with multi column pk (for simplicity)
    if hash_geometry or len(primary_key) > 1:
        LOG.info("Adding synthetic primary key to both sources as fc_id")
        df_a = fcd.add_hash_key(df_a, columns=primary_key, new_column="fcd_id", hash_geometry=hash_geometry, precision=precision)
        df_b = fcd.add_hash_key(df_b, columns=primary_key, new_column="fcd_id", hash_geometry=hash_geometry, precision=precision)
        primary_key = "fcd_id"
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
    cli()
