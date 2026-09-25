import functools
import logging
import os
import sys

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


def common_diff_options(f):
    """Shared IN_FILE_A/IN_FILE_B arguments and options for `diff`/`diff2gdb`.

    Everything the two commands have in common - only output-specific options
    (diff2gdb's --out-file/--dump-inputs, diff's --count) are declared separately
    on each command.
    """
    options = [
        click.argument("in_file_a", type=click.Path(exists=True, allow_dash=True)),
        click.argument("in_file_b", type=click.Path(exists=True)),
        click.option(
            "--layer-a",
            help="Name of layer to use within in_file_a (not valid if reading from stdin/parquet)",
        ),
        click.option(
            "--layer-b",
            help="Name of layer to use within in_file_b (not valid if reading from parquet)",
        ),
        click.option(
            "--fields",
            "-f",
            help="Comma separated list of fields to compare (do not include primary key)",
        ),
        click.option(
            "--ignore-fields",
            "-if",
            help="Comma separated list of fields to ignore",
        ),
        click.option(
            "--primary-key",
            "-pk",
            help="Name of primary key column, common to both datasets - for a composite "
            "key, use --hash-fields instead to generate one from multiple fields",
        ),
        click.option(
            "--hash-key",
            "-hk",
            default="fcd_hash_id",
            help="Name of new column to add as hash key",
        ),
        click.option(
            "--hash-fields",
            "-hf",
            help=(
                "Comma separated list of fields to hash, when no --primary-key is given - "
                "required in that case. Include the geometry field's name (typically "
                "'geometry') to include geometry in the hash"
            ),
        ),
        click.option(
            "--precision",
            "-p",
            default=0.01,
            help="Coordinate precision for geometry hash and comparison. Default=0.01",
        ),
        click.option(
            "--suffix-a",
            "-a",
            default="original",
            help="Suffix to append to column names from data source A when comparing attributes",
        ),
        click.option(
            "--suffix-b",
            "-b",
            default="new",
            help="Suffix to append to column names from data source B when comparing attributes",
        ),
        click.option(
            "--drop-null-geometry",
            "-d",
            is_flag=True,
            help=(
                "Drop records with null geometry. Only valid when the geometry field is "
                "included in --hash-fields - has no effect (and is rejected) when "
                "--primary-key is supplied, since no hash key is generated in that case"
            ),
        ),
        click.option(
            "--crs",
            help="Coordinate reference system to use when hashing geometries (eg EPSG:3005)",
        ),
        click.option(
            "--allow-duplicates",
            is_flag=True,
            help=(
                "Do not fail on a duplicated primary key - instead, drop all but the first "
                "occurrence of each duplicated key from the source it was found in, and "
                "include the dropped records in a DUPLICATES category/layer of the output. "
                "Not applied to a pure geometry hash (no primary key, and --hash-fields "
                "hashes on the geometry field alone) - a duplicate there always fails, "
                "since geometry alone can't reliably pair records between datasets when "
                "more than one shares a location"
            ),
        ),
        click.option(
            "--no-promote-multi",
            "promote_multi",
            is_flag=True,
            flag_value=False,
            default=True,
            help=(
                "Stricter geometry checking - compare geometries as-is. By default, "
                "when the sources mix single and multipart geometries of the same "
                "type (eg Point and MultiPoint), all geometries are promoted to "
                "multipart before comparing, so a feature stored single-part in one "
                "source and multi-part in the other is UNCHANGED - with this option "
                "it is MODIFIED_GEOM"
            ),
        ),
        click.option(
            "--strict-types",
            is_flag=True,
            help=(
                "Require compared field types to match exactly. By default, integer "
                "fields of differing width (eg Integer vs Integer64) are compared as "
                "the smallest integer type holding both, with a warning"
            ),
        ),
    ]
    return functools.reduce(lambda g, opt: opt(g), reversed(options), f)


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
    help=(
        "Drop records with null geometry. Only valid when the geometry field is "
        "included in --hash-fields"
    ),
)
@click.option(
    "--hash-fields",
    "-hf",
    required=True,
    help=(
        "Comma separated list of fields to hash. Include the geometry field's name "
        "(typically 'geometry') to include geometry in the hash"
    ),
)
@click.option(
    "--precision",
    "-p",
    default=0.01,
    help="Coordinate precision for geometry hash and comparison. Default=0.01",
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
    precision,
    drop_null_geometry,
    crs,
    verbose,
    quiet,
):
    """Read input data, compute hash, write to new file"""
    configure_logging(verbose - quiet)
    df = geopandas.read_file(in_file, layer=in_layer)

    # validate provided fields - hint at the actual geometry field name, in
    # case a misnamed geometry field (eg "Shape"/"SHAPE" from ArcGIS habit)
    # is the cause
    src = os.path.join(in_file, in_layer or "")
    hash_fields = hash_fields.split(",")
    for fieldname in hash_fields:
        if fieldname not in df.columns:
            hint = f" - this dataset's geometry field is named '{df.geometry.name}'"
            raise ValueError(f"Field {fieldname} is not present in {src}{hint}")

    # if specified, reproject
    if crs:
        df = df.to_crs(crs)

    df = fcd.add_hash_key(
        df,
        new_field=hash_key,
        fields=hash_fields,
        precision=precision,
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
    df.to_file(out_file, driver="OpenFileGDB", layer=out_layer, **fcd.gdb_write_options)


@cli.command()
@common_diff_options
@click.option(
    "--out-file",
    "-o",
    type=click.Path(),
    help="Path to output file, defaults to ./changedetector_YYYYMMDD_HHMM.gdb",
)
@click.option(
    "--dump-inputs",
    "-i",
    is_flag=True,
    help="Dump input layers (with new hash key) to output .gdb",
)
@verbose_opt
@quiet_opt
def diff2gdb(
    in_file_a,
    in_file_b,
    layer_a,
    layer_b,
    out_file,
    fields,
    ignore_fields,
    primary_key,
    hash_key,
    hash_fields,
    precision,
    suffix_a,
    suffix_b,
    drop_null_geometry,
    crs,
    dump_inputs,
    allow_duplicates,
    promote_multi,
    strict_types,
    verbose,
    quiet,
):
    """Compare two datasets, writing results to .gdb

    To read GeoJSON from stdin, specify "-" for IN_FILE_A
    """
    configure_logging(verbose - quiet)

    # parse multi-item parameters (primary_key is a single field, passed through as-is)
    fields = split_string(fields)
    ignore_fields = split_string(ignore_fields)
    hash_fields = split_string(hash_fields)

    fcd.diff_to_gdb(
        in_file_a,
        in_file_b,
        layer_a,
        layer_b,
        out_file,
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
        dump_inputs=dump_inputs,
        allow_duplicates=allow_duplicates,
        promote_multi=promote_multi,
        strict_types=strict_types,
    )


@cli.command()
@common_diff_options
@click.option(
    "--count",
    "-c",
    is_flag=True,
    help="Print the record count per category, instead of the primary key values",
)
@click.option(
    "--out-file",
    "-o",
    type=click.Path(),
    help="Path to write JSON summary to, instead of printing to stdout",
)
@verbose_opt
@quiet_opt
def diff(
    in_file_a,
    in_file_b,
    layer_a,
    layer_b,
    fields,
    ignore_fields,
    primary_key,
    hash_key,
    hash_fields,
    precision,
    suffix_a,
    suffix_b,
    drop_null_geometry,
    crs,
    count,
    out_file,
    allow_duplicates,
    promote_multi,
    strict_types,
    verbose,
    quiet,
):
    """Compare two datasets, printing a JSON summary to stdout

    Same comparison as `diff2gdb`, but for when spatial output isn't needed -
    prints a JSON summary instead of writing a .gdb: the primary key value(s)
    in each NEW/DELETED/MODIFIED_* category (use --count for the record count
    per category instead). Use --out-file to write the JSON to a file instead
    of stdout.

    To read GeoJSON from stdin, specify "-" for IN_FILE_A
    """
    configure_logging(verbose - quiet)

    # parse multi-item parameters (primary_key is a single field, passed through as-is)
    fields = split_string(fields)
    ignore_fields = split_string(ignore_fields)
    hash_fields = split_string(hash_fields)

    fcd.diff_to_json(
        in_file_a,
        in_file_b,
        layer_a,
        layer_b,
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
        counts_only=count,
        out_file=out_file,
        allow_duplicates=allow_duplicates,
        promote_multi=promote_multi,
        strict_types=strict_types,
    )


if __name__ == "__main__":
    cli()
