import logging
import os
import shutil
import sys
from datetime import datetime

import click
import geopandas
from cligj import quiet_opt, verbose_opt

import fit_changedetector as fcd

LOG = logging.getLogger(__name__)


def split_string(input_string):
    if input_string:
        return input_string.split(",")
    else:
        return []


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
@click.argument("out_file")
@click.option("--in-layer", help="Name of layer to add hashed primary key")
@click.option(
    "--out-layer",
    "-nln",
    help="Output layer name",
)
@click.option(
    "--hash-key",
    "-hk",
    default="fcd_hash_id",
    help="Name of new column containing hashed data",
)
@click.option(
    "--drop-null-geometry",
    "-d",
    is_flag=True,
    help="Drop records with null geometry",
)
@click.option(
    "--hash-fields",
    "-hf",
    help="Comma separated list of fields to include in the hash (not including geometry)",
)
@click.option(
    "--crs",
    help="Coordinate reference system to use when hashing geometries (eg EPSG:3005)",
)
@verbose_opt
@quiet_opt
def add_hash_key(
    in_file,
    out_file,
    in_layer,
    out_layer,
    hash_key,
    hash_fields,
    drop_null_geometry,
    crs,
    verbose,
    quiet,
):
    """Read input data, compute hash, write to new file"""
    configure_logging((verbose - quiet))
    df = geopandas.read_file(in_file, layer=in_layer)

    # validate provided fields
    src = os.path.join(in_file, in_layer or "")
    if hash_fields:
        hash_fields = hash_fields.split(",")
        for fieldname in hash_fields:
            if fieldname not in df.columns:
                raise ValueError(f"Field {fieldname} is not present in {src}")
    else:
        hash_fields = []

    # if specified, reproject
    if crs:
        df = df.to_crs(crs)

    df = fcd.add_hash_key(
        df,
        new_field=hash_key,
        fields=hash_fields,
        hash_geometry=True,
        drop_null_geometry=drop_null_geometry,
    )

    # todo - support overwrite of existing files? appending to existing gdb?
    if os.path.exists(out_file):
        raise ValueError(f"Output file {out_file} exists.")

    # default to naming output layer the same as input layer (if supplied)
    if not out_layer and in_layer:
        LOG.warning(f"No output layer name specified, using {in_layer}")
        out_layer = in_layer
    elif not out_layer:
        raise ValueError("Output layer name is required if no input layer is specified")

    LOG.info(f"Writing new dataset {out_file} with new hash based column {hash_key}")
    df.to_file(out_file, driver="OpenFileGDB", layer=out_layer)


@cli.command()
@click.argument("in_file_a", type=click.Path(exists=True))
@click.argument("in_file_b", type=click.Path(exists=True))
@click.option("--layer-a", help="Name of layer to use within in_file_a")
@click.option("--layer-b", help="Name of layer to use within in_file_b")
@click.option(
    "--fields",
    "-f",
    help="Comma separated list of fields to compare (do not include primary key)",
)
@click.option(
    "--out-file",
    "-o",
    type=click.Path(),
    help="Path to output file, defaults to ./changedetector_YYYYMMDD_HHMM.gdb",
)
@click.option(
    "--primary-key",
    "-pk",
    help="Comma separated list of primary key column(s), common to both datasets",
)
@click.option(
    "--hash-key",
    "-hk",
    default="fcd_hash_id",
    help="Name of new column to add as hash key",
)
@click.option(
    "--hash-fields",
    "-hf",
    help="Comma separated list of fields to include in the hash (in addition to geometry)",
)
@click.option(
    "--precision",
    "-p",
    default=0.01,
    help="Coordinate precision for geometry hash and comparison. Default=0.01",
)
@click.option(
    "--suffix-a",
    "-a",
    default="original",
    help="Suffix to append to column names from data source A when comparing attributes",
)
@click.option(
    "--suffix-b",
    "-b",
    default="new",
    help="Suffix to append to column names from data source B when comparing attributes",
)
@click.option(
    "--drop-null-geometry",
    "-d",
    is_flag=True,
    help="Drop records with null geometry",
)
@click.option(
    "--dump-inputs",
    "-i",
    is_flag=True,
    help="Dump input layers (with new hash key) to output .gdb",
)
@click.option(
    "--crs",
    help="Coordinate reference system to use when hashing geometries (eg EPSG:3005)",
)
@verbose_opt
@quiet_opt
def compare(
    in_file_a,
    in_file_b,
    layer_a,
    layer_b,
    out_file,
    fields,
    primary_key,
    hash_key,
    hash_fields,
    precision,
    suffix_a,
    suffix_b,
    drop_null_geometry,
    crs,
    dump_inputs,
    verbose,
    quiet,
):
    """Compare two datasets"""
    configure_logging((verbose - quiet))

    # parse multi-item parameters
    fields = split_string(fields)
    primary_key = split_string(primary_key)
    hash_fields = split_string(hash_fields)

    fcd.compare(
        in_file_a,
        in_file_b,
        layer_a,
        layer_b,
        out_file,
        primary_key=primary_key,
        fields=fields,
        suffix_a=suffix_a,
        suffix_b=suffix_b,
        drop_null_geometry=drop_null_geometry,
        crs=crs,
        hash_key=hash_key,
        hash_fields=hash_fields,
        dump_inputs=dump_inputs,
    )


if __name__ == "__main__":
    cli()
