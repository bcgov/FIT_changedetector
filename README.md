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

	import geopandas
	import fit_changedetector as fcd

	df_a = geopandas.read_file(in_file_a, layer=layer_a)
    df_b = geopandas.read_file(in_file_b, layer=layer_b)

	diff = fcd.gdf_diff(
        df_a,
        df_b,
        <primary_key>,
        fields=<fields_to_compare>,
        precision=<precision>,
        suffix_a="a",
        suffix_b="b",
    )

#### CLI

	changedetector <dataset_a> <dataset_b> -k <primary_key>

## Development and testing

Presuming that GDAL is already installed to your system:

	$ git clone git@github.com:bcgov/FIT_changedetector.git
	$ cd FIT_changedetector
	$ python -m venv .venv
	$ source .venv/bin/activate
	$ pip install -e .[test]
	(.venv) $ py.test