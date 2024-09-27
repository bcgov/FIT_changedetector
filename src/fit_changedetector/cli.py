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
def add_hash_key(in_file, out_file, in_layer, out_layer, hash_key, hash_fields, drop_null_geometry, crs, verbose, quiet):
    """Add hash of input columns and geometry to new column, write data to new file
    """
    configure_logging((verbose - quiet))
    df = geopandas.read_file(in_file, layer=in_layer)
    
    # validate provided fields
    if fields:
        fields = fields.split(",")
        for field in fields:
            if field not in df.columns:
                src = os.path.join(in_file, in_layer)
                raise ValueError(f"Field {field} is not present in {src}")
    else:
        fields = []
    
    # if specified, reproject
    if crs:
        df = df.to_crs(crs)

    df = fcd.add_hash_key(df, new_field=hash_key, fields=hash_fields, hash_geometry=True, drop_null_geometry=drop_null_geometry)
    
    # todo - support overwrite of existing files? appending to existing gdb?
    if os.path.exists(out_file):
        raise ValueError(f"Output file {out_file} exists.")
    
    # default to naming output layer the same as input layer (if supplied)
    if not out_layer and in_layer:
        LOG.warning(f"No output layer name specified, using {in_layer}")
        out_layer = in_layer
    elif not out_layer:
        raise ValueError(f"Output layer name is required if no input layer is specified")
    
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
    "--out-path",
    "-o",
    type=click.Path(),
    default=".",
    help="Output path",
)
@click.option(
    "--primary-key",
    "-pk",
    multiple=True,
    help="Primary key column(s), common to both datasets",
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
    default="a",
    help="Suffix to append to column names from data source A when comparing attributes",
)
@click.option(
    "--suffix-b",
    "-b",
    default="b",
    help="Suffix to append to column names from data source B when comparing attributes",
)
@click.option(
    "--drop-null-geometry",
    "-d",
    is_flag=True,
    help="Drop records with null geometry",
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
    primary_key,
    hash_key,
    fields,
    out_path,
    precision,
    suffix_a,
    suffix_b,
    drop_null_geometry,
    crs,
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

    # default to not dumping input datasets to new files
    dump_inputs = False

    # shortcuts to source layer paths for logging
    src_a = os.path.join(in_file_a, layer_a or "")
    src_b = os.path.join(in_file_b, layer_b or "")
    
    # if specified, reproject both sources (even if not hashing on geoms)
    if crs:
        df_a = df_a.to_crs(crs)
        df_b = df_b.to_crs(crs)

    # is pk present and unique in both sources?
    if primary_key:
        primary_key = list(primary_key)
        if not bool(set(primary_key) & set(df_a.columns)):
            raise ValueError(
                f"Primary key {','.join(primary_key)} not present in {src_a}"
            )
        if not bool(set(primary_key) & set(df_b.columns)):
            raise ValueError(
                f"Primary key {','.join(primary_key)} not present in {src_b}"
            )
        
    # if no pk supplied, set it as empty list, trigger hash on geometry
    else:
        primary_key = []
        hash_geometry = True

    # add hashed key 
    # - hash multi column primary keys (without geom) for simplicity
    # - hash with geometry if no primary key specified
    if hash_geometry or len(primary_key) > 1:
        LOG.info(f"Adding hashed key (synthetic primary key) to {src_a} as {hash_key}")
        df_a = fcd.add_hash_key(df_a, new_field=hash_key, fields=primary_key, hash_geometry=hash_geometry, precision=precision, drop_null_geometry=drop_null_geometry)
        LOG.info(f"Adding hashed key (synthetic primary key) to {src_b} as {hash_key}")
        df_b = fcd.add_hash_key(df_b, new_field=hash_key, fields=primary_key, hash_geometry=hash_geometry, precision=precision, drop_null_geometry=drop_null_geometry)
        primary_key = [hash_key]
        dump_inputs = True
    
    # convert primary key from list to column name string
    # (it is always only a single column after above processing)
    primary_key = primary_key[0]
    
    # verify pk is unique in each source, fail otherwise
    if len(df_a) != len(df_a[[primary_key]].drop_duplicates()):
        raise ValueError(
            f"Primary key {primary_key} is not unique in {src_a}"
        )
    if len(df_b) != len(df_b[[primary_key]].drop_duplicates()):
        raise ValueError(
            f"Primary key {primary_key} is not unique in {src_b}"
        )

    # if string of fields to diff is provided, parse into list
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
    if dump_inputs and mode == "a":
        df_a.to_file(
            out_gdb, driver="OpenFileGDB", layer="source_" + suffix_a, mode="a"
        )
        df_b.to_file(
            out_gdb, driver="OpenFileGDB", layer="source_" + suffix_b, mode="a"
        )


if __name__ == "__main__":
    cli()
