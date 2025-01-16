# FIT Change Detector

[![Lifecycle:Experimental](https://img.shields.io/badge/Lifecycle-Experimental-339999)](https://github.com/bcgov/repomountie/blob/master/doc/lifecycle-badges.md)

GeoBC Foundational Information and Technology (FIT) Section tool for reporting on chages to geodata over time.

## Installation

GDAL and Geopandas are required. If gdal and geopandas are already installed to your environment, install with pip:

    git clone git@github.com:bcgov/FIT_changedetector.git
    cd FIT_changedetector
    pip install .

For systems where gdal/geopandas are not already available, installing geopanadas with `conda` as per the [guide](https://geopandas.org/en/stable/getting_started/install.html#creating-a-new-environment) is likely the best option.


## Usage

#### Python module

The primary function of interest is `gdf_diff()`:

    import geopandas
    import fit_changedetector as fcd

    # read the data
    df_a = geopandas.read_file(in_file_a, layer=layer_a)
    df_b = geopandas.read_file(in_file_b, layer=layer_b)

    # compare the two dataframes
    diff = fcd.gdf_diff(
        df_a,
        df_b,
        <primary_key>,
        fields=<fields_to_compare>,
        precision=<precision>,
        suffix_a="a",
        suffix_b="b",
    )

`gdf_diff` returns a dictionary having the keys noted below. Dictionary values are geopandas GeoDataFrames holding the corresponding records.

Dictionary keys:

| key | description |
|-----|-------------|
| `NEW` | additions |
| `DELETED` | deleted records |
| `UNCHANGED` | unchanged records |
| `MODIFIED_BOTH` | records where attribute columns and geometries have changed |
| `MODIFIED_ATTR` | records where attribute columns have changed but geometries have not changed |
| `MODIFIED_GEOM` | records where geometries have changed but attribute columns have not |

Schemas for records contained in `NEW`, `DELETED`, `UNCHANGED` are as per the source data.
Schemas for records contained in the `MODIFIED` keys include only columns where a change has occured. For example, these are some "modified attributes" records, with "_a" suffix for values from the primary dataset, and "_b" suffix for values from the secondary dataset:

    >>> diff["MODIFIED_ATTR"]
      id       park_name_a                park_name_b parkclasscode_a parkclasscode_b
    0  3  Mars Street Park        Jupiter Street Park             NaN             NaN
    1  6      Mayfair Blue              Mayfair Green              BL             GRN
    2  7                    Quadra Heights Playground             NaN             NaN
    3  9               NaN                        NaN              RP             PND


#### CLI

    $ changedetector --help
    Usage: changedetector [OPTIONS] COMMAND [ARGS]...

    Options:
    --version  Show the version and exit.
    --help     Show this message and exit.

    Commands:
    add-hash-key  Read input data, compute hash, write to new file
    compare       Compare two datasets

    $ changedetector add-hash-key --help
    Usage: changedetector add-hash-key [OPTIONS] IN_FILE OUT_FILE

    Read input data, compute hash, write to new file

    Options:
    --in-layer TEXT           Name of layer to add hashed primary key
    -nln, --out-layer TEXT    Output layer name
    -hk, --hash-key TEXT      Name of new column containing hashed data
    -d, --drop-null-geometry  Drop records with null geometry
    -hf, --hash-fields TEXT   Comma separated list of fields to include in the
                                hash (not including geometry)
    --crs TEXT                Coordinate reference system to use when hashing
                                geometries (eg EPSG:3005)
    -v, --verbose             Increase verbosity.
    -q, --quiet               Decrease verbosity.
    --help                    Show this message and exit.

    $ changedetector compare --help
    Usage: changedetector compare [OPTIONS] IN_FILE_A IN_FILE_B

        Compare two datasets

    Options:
    --layer-a TEXT             Name of layer to use within in_file_a
    --layer-b TEXT             Name of layer to use within in_file_b
    -f, --fields TEXT          Comma separated list of fields to compare (do not
                               include primary key)
    -if, --ignore-fields TEXT  Comma separated list of fields to ignore
    -o, --out-file PATH        Path to output file, defaults to
                               ./changedetector_YYYYMMDD_HHMM.gdb
    -pk, --primary-key TEXT    Comma separated list of primary key column(s),
                               common to both datasets
    -hk, --hash-key TEXT       Name of new column to add as hash key
    -hf, --hash-fields TEXT    Comma separated list of fields to include in the
                               hash (in addition to geometry)
    -p, --precision FLOAT      Coordinate precision for geometry hash and
                               comparison. Default=0.01
    -a, --suffix-a TEXT        Suffix to append to column names from data source
                               A when comparing attributes
    -b, --suffix-b TEXT        Suffix to append to column names from data source
                               B when comparing attributes
    -d, --drop-null-geometry   Drop records with null geometry
    -i, --dump-inputs          Dump input layers (with new hash key) to output
                               .gdb
    --crs TEXT                 Coordinate reference system to use when hashing
                               geometries (eg EPSG:3005)
    -v, --verbose              Increase verbosity.
    -q, --quiet                Decrease verbosity.
    --help                     Show this message and exit.

##### Examples

Compare the test datasets using their known primary key:

    $ changedetector compare -v \
        tests/data/parks_a.geojson \
        tests/data/parks_b.geojson \
        -pk fcd_load_id 

Compare the test datasets, using a hash of geometry and the column `park_name` as synthetic primary key, 
written to `new_hash_column`:

    $ changedetector compare -v \
        tests/data/parks_a.geojson \
        tests/data/parks_b.geojson \
        -hf park_name \
        -hk new_hash_column


##### GTS

Note that the CLI is not currently available in the BC GTS Esri Python/conda environments.  
To use the CLI on GTS, open a "Python Command Prompt", initialize conda (if you have not already done so), deactivate the 
default environment, and activate the pre-built `changedetector_env` environment:

    > conda init cmd.exe  # if required

    <restart the Python Command Prompt>
    
    > conda deactivate
    > conda activate Q:\dss_workarea\_contractors\sinorris\conda_environments\changedetector_env
    (changedetector_env)> changedetector --help
    
## Development and testing

Presuming that GDAL is already installed to your system:

    $ git clone git@github.com:bcgov/FIT_changedetector.git
    $ cd FIT_changedetector
    $ python -m venv .venv
    $ source .venv/bin/activate
    $ pip install -e .[test]
    (.venv) $ py.test