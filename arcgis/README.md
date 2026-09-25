# ArcGIS Pro script tools

Two script tools wrap the `changedetector` CLI (see the [main README](../README.md) for what the CLI itself does):

- `changedetector_diff2json.py` - wraps `diff`, prints a JSON summary
- `changedetector_diff2gdb.py` - wraps `diff2gdb`, writes results to a .gdb

Both require `changedetector_common.py` (shared logic - subprocess invocation, logging, CLI arg building) alongside them, and both run the CLI via [`uv`](https://docs.astral.sh/uv/)'s `uvx`, which resolves and caches an isolated `fit_changedetector` environment on demand - no venv, no `pip install`, nothing else to set up.

## Prerequisite

[Install uv](https://docs.astral.sh/uv/getting-started/installation/) on the machine running ArcGIS Pro, so `uv`/`uvx` are available at the command prompt.

## Setup

1. Download `fit_changedetector-arcgis-tools-<version>.zip` from the [latest release](https://github.com/bcgov/FIT_changedetector/releases/latest) and extract `changedetector_common.py`, `changedetector_diff2json.py`, `changedetector_diff2gdb.py` (and this README) to a target folder - wherever you point the tool's Script File (ArcGIS Pro adds that script's own folder to `sys.path`). See [Releases & versioning](#releases--versioning) below for why this is the recommended source rather than copying the files straight out of the repo.
2. In ArcGIS Pro's Catalog pane, add a new **Script** tool to a toolbox, and set its **Script File** to the entry-point script (`changedetector_diff2json.py` or `changedetector_diff2gdb.py`).
3. Add the tool's parameters, in order, per the table below.
4. Paste `changedetector_toolvalidator.py`'s contents into the tool's **Validation** tab - the same code works unmodified for both tools (it only touches parameters 0-8, which are identical between them).
5. Repeat for the second tool, if you want both.

## Upgrades

For releases that change the ArcGIS tools' parameters or validation code, additional manual upgrade steps are required.
These release specific steps (beyond the usual file swap) are provided in [UPGRADING.md](UPGRADING.md).


## Parameters

Parameters 0-12 are identical for both tools. Each tool then adds its own tail, ending in a **Derived** output parameter that publishes the path of the file it wrote.

| # | Name | Suggested type | Required |
|---|------|-----------------|----------|
| 0 | original_fc | Feature Layer | Required |
| 1 | new_fc | Feature Layer | Required |
| 2 | out_folder | Folder | Required |
| 3 | primary_key | String | Optional |
| 4 | fields | String, multivalue | Optional |
| 5 | ignore_fields | String, multivalue | Optional |
| 6 | hash_key | String | Optional |
| 7 | hash_fields | String, multivalue | Optional |
| 8 | precision | Double | Optional |
| 9 | suffix_a | String | Optional |
| 10 | suffix_b | String | Optional |
| 11 | drop_null_geometry | Boolean | Optional |
| 12 | allow_duplicates | Boolean | Optional |

`changedetector_diff2json.py` (`diff`):

| # | Name | Suggested type | Required |
|---|------|-----------------|----------|
| 13 | out_name | String | Optional |
| 14 | debug | Boolean | Optional |
| 15 | out_file | File, **Derived**, Output | - |

`changedetector_diff2gdb.py` (`diff2gdb`):

| # | Name | Suggested type | Required |
|---|------|-----------------|----------|
| 13 | dump_inputs | Boolean | Optional |
| 14 | out_name | String | Optional |
| 15 | debug | Boolean | Optional |
| 16 | out_file | File, **Derived**, Output | - |

`out_name`, left blank, names the output (and its log file) with a timestamp automatically; set it to get a predictable filename instead - useful if you're calling the tool programmatically and want to know the output path in advance rather than reading it off the derived output parameter.

Note that unlike the CLI, the ArcGIS tools provide no `--crs` parameter (for overriding the coordinate reference system used when hashing geometries).

The file geodatabase written by `changedetector_diff2gdb.py` stores 64-bit integer fields as Big Integer, rather than as floating point (Double), which cannot exactly represent every large value - eg a large id. Big Integer fields require ArcGIS Pro 3.2 or later.

## Tool metadata

Suggested text for each tool's **Summary** and **Description** (Tool Properties > General tab) and **Usage**/**Syntax** (Edit Metadata - Syntax is per-parameter help).

### `changedetector_diff2json.py` (tool: diff2json)

**Summary:** Compares two feature classes and reports the differences as a JSON summary, with no spatial output.

**Description:** Compares an original and a new feature class - matched by primary key if one is given, otherwise by a generated hash key - and classifies every record as NEW, DELETED, UNCHANGED, MODIFIED_ATTR (attributes only), MODIFIED_GEOM (geometry only), or MODIFIED_BOTH. Writes a JSON file listing record counts per category, plus the primary key value(s) present in each category except UNCHANGED (a Duplicates category is added if duplicate primary keys are allowed). No spatial output is produced - use "Change Detector - Diff to GDB" instead if you need the actual changed features written out.

**Usage:** Wraps the `changedetector diff` command-line tool. Requires `uv` to be installed on this machine - the tool shells out to a `uv`-managed Python environment rather than running inside ArcGIS Pro's own Python (see Setup above). Original and New Feature Class are matched by primary key if one is supplied; otherwise records are matched by a hash key generated from Fields to Include in Hash (required in that case - include the geometry field to match by geometry). There is no parameter for overriding the coordinate reference system used when hashing - geometries are hashed in their native CRS. Leave Output File Name blank to auto-generate a timestamped file name.

**Syntax:**
- **Original Feature Class** - The "before" dataset to compare.
- **New Feature Class** - The "after" dataset to compare against Original Feature Class.
- **Output Folder** - Folder where the JSON summary and the run's log file are written.
- **Primary Key** - A single column, common to both datasets, that uniquely identifies each record. If left blank, records are matched by a generated hash key instead - **Fields to Include in Hash** is then required (use this to match on a composite of multiple fields). Hidden once **Fields to Include in Hash** has a selection - clear that to supply a primary key instead.
- **Fields to Compare** - Fields to compare for attribute changes; do not include the primary key. If left blank, all fields common to both datasets are compared.
- **Fields to Ignore** - Fields to exclude from the attribute comparison.
- **Hash Key** - Name of the column used to hold the generated hash key, when no primary key is supplied. Default: `fcd_hash_id`. Hidden when a primary key is supplied.
- **Fields to Include in Hash** - The complete list of fields to fold into the generated hash key. Required when no primary key is supplied; cleared and hidden when one is. Include the geometry field (Shape) in this list to match records by geometry - omit it to hash on attributes only.
- **Coordinate Precision** - Coordinate precision used when hashing and comparing geometries. Default: `0.01`.
- **Suffix - Original** - Suffix appended to column names from Original Feature Class when reporting attribute differences. Default: `original`.
- **Suffix - New** - Suffix appended to column names from New Feature Class when reporting attribute differences. Default: `new`.
- **Drop Null Geometry** - Drop records with null geometry before comparing. Only valid when the geometry field is included in **Fields to Include in Hash**. Cleared and hidden when a primary key is supplied.
- **Allow Duplicate Primary Keys** - Do not fail on a duplicated primary key - instead, keep the first occurrence of each duplicated key (per source) and report the dropped records under a Duplicates category. Not applied when matching by geometry alone (no primary key or hash fields) - a duplicate there always fails, since geometry alone can't reliably pair records when more than one shares a location.
- **Output File Name** - Optional. Names the output JSON file and its log file. Leave blank to auto-generate a timestamped name instead.
- **Debug Logging** - Enable verbose (DEBUG level) logging.
- **Output File** *(Derived)* - Path of the JSON summary file written by this run.

### `changedetector_diff2gdb.py` (tool: diff2gdb)

**Summary:** Compares two feature classes and writes the differences as layers in a new file geodatabase.

**Description:** Compares an original and a new feature class - matched by primary key if one is given, otherwise by a generated hash key - and writes the results to a new file geodatabase, one layer per category of change: NEW, DELETED, MODIFIED_ATTR (attributes only), MODIFIED_GEOM (geometry only), MODIFIED_BOTH, and DUPLICATES (if duplicate primary keys are allowed). Optionally also writes copies of the two input layers, with the hash key added, for reference. Use "Change Detector - Diff (JSON Summary)" instead if you just need a quick count/summary without spatial output.

**Usage:** Wraps the `changedetector diff2gdb` command-line tool. Requires `uv` to be installed on this machine - the tool shells out to a `uv`-managed Python environment rather than running inside ArcGIS Pro's own Python (see Setup above). Original and New Feature Class are matched by primary key if one is supplied; otherwise records are matched by a hash key generated from Fields to Include in Hash (required in that case - include the geometry field to match by geometry). Writes results as separate layers - NEW, DELETED, MODIFIED_ATTR, MODIFIED_GEOM, MODIFIED_BOTH, and DUPLICATES if duplicates are allowed - in a new file geodatabase. There is no parameter for overriding the coordinate reference system used when hashing - geometries are hashed in their native CRS. Leave Output File Name blank to auto-generate a timestamped name.

**Syntax:** same as diff2json for the parameters below, plus Dump Input Layers:
- **Original Feature Class**, **New Feature Class**, **Output Folder**, **Fields to Compare**, **Fields to Ignore**, **Hash Key**, **Fields to Include in Hash**, **Coordinate Precision**, **Suffix - Original**, **Suffix - New**, **Drop Null Geometry** - as in diff2json above.
- **Primary Key** - A single column, common to both datasets, that uniquely identifies each record. If left blank, records are matched by a generated hash key instead - **Fields to Include in Hash** is then required (use this to match on a composite of multiple fields). Leaving this blank forces **Dump Input Layers** on regardless of that parameter's own setting - see below. Hidden once **Fields to Include in Hash** has a selection - clear that to supply a primary key instead.
- **Allow Duplicate Primary Keys** - as in diff2json above.
- **Dump Input Layers** - Also write copies of the two input layers, with the generated hash key column added, into the output geodatabase for reference. Forced on automatically whenever a hash key had to be generated (Primary Key left blank) - the generated key only exists in that hashed copy, so dumping the inputs is how you can see which geometry/attribute values produced which hash. In that case, this happens regardless of how this parameter is set.
- **Output File Name** - Optional. Names the output `.gdb` and its log file. Leave blank to auto-generate a timestamped name instead.
- **Debug Logging** - Enable verbose (DEBUG level) logging.
- **Output File** *(Derived)* - Path of the file geodatabase written by this run.

## Releases & versioning

Each script tool shells out to a specific, pinned `fit_changedetector` version - `changedetector_common.py`'s `FIT_CHANGEDETECTOR_SPEC` - rather than "whatever's newest," so a tool's behavior can't shift between runs without someone explicitly changing that pin.

Note that the scripts in `arcgis/` as currently committed may be ahead of the pinned spec - `FIT_CHANGEDETECTOR_SPEC` only advances when a release is tagged, so between releases it still points at the last one. Every tagged release (`vX.Y.Z`) automatically builds a correctly-pinned copy and attaches it to the matching [GitHub Release](https://github.com/bcgov/FIT_changedetector/releases) as `fit_changedetector-arcgis-tools-vX.Y.Z.zip` - this is what is deployed to ArcGIS systems as above. That archive's `FIT_CHANGEDETECTOR_SPEC` is generated fresh from the tag at release time, so it's always version-matched to the `fit_changedetector` release published to PyPI in the same run. The release workflow also commits the same bump to `arcgis/changedetector_common.py` on `main` immediately afterward, so neither the archive nor the repo's own copy needs to be kept in sync by hand.

### Testing against unreleased fit_changedetector changes

To test changes that are not on PyPI yet, create a `spec_override.txt` file next to `changedetector_common.py` (gitignored - `git pull` never touches it, nothing to stash or revert) containing a git ref or a local wheel/checkout path instead of a released version (`uvx --from` accepts either):

    git+https://github.com/bcgov/FIT_changedetector.git@main

`get_spec()` reads that file fresh on every run if it exists, falling back to the committed `FIT_CHANGEDETECTOR_SPEC` otherwise - so editing it takes effect on the very next run (no ArcGIS Pro restart needed to pick up a *changed* override). Delete the file to go back to the pinned release default.
