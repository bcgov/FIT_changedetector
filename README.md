# FIT Open Data Downloader

[![Lifecycle:Experimental](https://img.shields.io/badge/Lifecycle-Experimental-339999)](https://github.com/bcgov/repomountie/blob/master/doc/lifecycle-badges.md)

GeoBC Foundational Information and Technology (FIT) Section tool for downloading open data and reporting on changes since last download.

## Workflow

1. Based on sources and schedule defined in a provided config file, download spatial data from the internet
2. Compare downloaded data to cached version on object storage
3. If changes are detected, write the latest download to object storage along with a change report


## Installation

Using `pip` managed by the target Python environment:

	git clone git@github.com:bcgov/FIT_opendatadownloader.git
	cd FIT_opendatadownloader
	pip install .


## Usage

A command line interface is provided:

```
$ fit_downloader process --help
Usage: fit_downloader process [OPTIONS] CONFIG_FILE

  For each configured layer - download latest, detect changes, write to file

Options:
  -l, --layer TEXT            Layer to process in provided config.
  -o, --out-path PATH         Output path or s3 prefix.
  -f, --force                 Force download to out-path without running
                              change detection.
  -s, --schedule [D|W|M|Q|A]  Process only sources with given schedule tag.
  -V, --validate              Validate configuration
  -v, --verbose               Increase verbosity.
  -q, --quiet                 Decrease verbosity.
  --help                      Show this message and exit.

```

Examples:

1. Validate a configuration file for a given source:
	
		fit_downloader process -vV example_config.json

2. Download and process layers defined in `example_config.json` configuration file, saving to `/my/output/path` on the local filesystem:

		fit_downloader process -o my/output/path example_config.json 


## Configuration

Layers for downloaded are configured per jusrisdiction in [sources](sources). 
Each config .json file has several tag defining how to handle data for the given jurisdiciton:

| tag            | required              | description                                                                          |
|----------------| --------------------- |--------------------------------------------------------------------------------------|
| `out_layer`    |  Y                    | Name of target file/layer (`parks`, `roads`, etc)                                    |
| `source`       |  Y                    | url or file path to file based source, format readable by GDAL/OGR (required)        |
| `protocol`     |  Y                    | Type of download (`http` - file via http, `esri` - ESRI REST API endpoint, `bcgw` - download BCGW table via WFS)          |
| `fields`       |  Y                    | List of source field(s) to retain in the download (required)                         |
| `schedule   `  |  Y                    | Download frequency (required, must be one of: [`D, W, M, Q, A`] - daily/weekly/monthly/quarterly/annual) |
| `source_layer` |  N                    | Name of layer to use within source (optional, defaults to first layer in file)       |
| `query`        |  N                    | Query to subset data in source/layer (OGR SQL) (optional, currently only supported for sources where `protocol` is `http`) | 
| `primary_key`  |  N                    | List of source field(s) used as primary key (optional, must be a subset of `fields`) |
| `metadata_url` |  N                    | Link to source metadata                                                    |


For the full schema definition, see [`source.schema.json`](source.schema.json).

## Development and testing

### virtual environment

Using GDAL on your system:

	$ git clone git@github.com:bcgov/FIT_opendatadownloader.git
	$ cd FIT_opendatadownloader
	$ python -m venv .venv
	$ source .venv/bin/activate
	$ pip install -e .[test]
	(.venv) $ py.test

### Dockerized environment

Using GDAL on a docker image:

To build:

	$ git clone git@github.com:bcgov/FIT_opendatadownloader.git
	$ cd FIT_opendatadownlaoder
	$ docker build -t fit_opendatadownloader .

Drop in to a bash session:

	$ docker run --rm -it -v ./:/home/fit_opendatadownloader fit_opendatadownloader  bash
