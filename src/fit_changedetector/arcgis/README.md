# ArcGIS Pro script tools

Two script tools wrap the `changedetector` CLI (see the [main README](../../../README.md) for what the CLI itself does):

- `changedetector_diff2json.py` - wraps `diff`, prints a JSON summary
- `changedetector_diff2gdb.py` - wraps `diff2gdb`, writes results to a .gdb

Both require `changedetector_common.py` (shared logic - subprocess invocation, logging, CLI arg building) alongside them. All of these scripts, plus `changedetector_toolvalidator.py`, ship inside the `fit_changedetector` package itself, in this folder. Each tool's Script File points at the copy installed in a dedicated Python environment (venv), and the tool runs the CLI as a subprocess using that same venv's Python - never inside ArcGIS Pro's own Python.

## Locations

| | Path |
|---|---|
| Base Python | `\\GISWHSE.ENV.GOV.BC.CA\WHSE_NP\corp\central_python\Python_314` |
| Venv | `\\GISWHSE.ENV.GOV.BC.CA\WHSE_NP\corp\central_venv\fit_changedetector` |

Users need read access to both. The base Python must stay in place - a venv's `python.exe` is only a launcher for its base install.

Always use the UNC paths above, not a mapped drive letter (`P:` is `\\GISWHSE.ENV.GOV.BC.CA\WHSE_NP`). The venv records its base Python's path exactly as it was given when the venv was built, so the venv, its base Python and the tools' Script Files must all use the same form. A venv can't be moved or renamed - if either folder changes, build a new venv.

## Setup

### 1. Create the environment

At a Windows command prompt:

    REM point to base python
    set PY=\\GISWHSE.ENV.GOV.BC.CA\WHSE_NP\corp\central_python\Python_314\python.exe

    REM point to target virtualenv
    set VENV=\\GISWHSE.ENV.GOV.BC.CA\WHSE_NP\corp\central_venv\fit_changedetector

    REM venv is on a network share, so copy files rather than hardlink from uv's local cache
    set UV_LINK_MODE=copy

    REM ensure uv is present, install if not
    %PY% -m uv --version || %PY% -m pip install uv

    REM create the virtual environment
    %PY% -m uv venv %VENV% --python %PY%

    REM install the change detector package - replace <version> with the release number, e.g. 0.1.0
    %PY% -m uv pip install --python %VENV% fit_changedetector==<version>

    REM check that everything worked
    %VENV%\Scripts\python.exe -m fit_changedetector --version

[uv](https://docs.astral.sh/uv/) is only used to build the environment - the tools themselves never call it. Without uv, the standard library could do the same job:

    %PY% -m venv %VENV%
    %VENV%\Scripts\python.exe -m pip install fit_changedetector==<version>

### 2. Add the tools

1. In ArcGIS Pro's Catalog pane, add a new **Script** tool to a toolbox, and set its **Script File** to the installed entry-point script:

       \\GISWHSE.ENV.GOV.BC.CA\WHSE_NP\corp\central_venv\fit_changedetector\Lib\site-packages\fit_changedetector\arcgis\changedetector_diff2json.py
       \\GISWHSE.ENV.GOV.BC.CA\WHSE_NP\corp\central_venv\fit_changedetector\Lib\site-packages\fit_changedetector\arcgis\changedetector_diff2gdb.py

   Point at this installed copy - the tool finds its Python by looking upward from the script for the venv, and stops with an error if there isn't one.
2. Add the tool's parameters, in order, per the [Parameters](#parameters) tables below.
3. Paste the contents of `changedetector_toolvalidator.py` (in the same installed folder) into the tool's **Validation** tab - the same code works unmodified for both tools (it only touches parameters 0-8, which are identical between them).
4. Repeat for the second tool.
5. Restart ArcGIS Pro if a tool in this session had previously run from a different Script File (see [Restarting ArcGIS Pro](#restarting-arcgis-pro)).

## Maintenance

### Upgrades

Make sure nobody is running a tool - Windows locks files in use, so an upgrade mid-run can fail partway. Then upgrade the package in place:

    %PY% -m uv pip install --python %VENV% fit_changedetector==<new version>

and restart ArcGIS Pro. Always give the exact version (`==<version>`): without it, uv may treat whatever is already installed as good enough and change nothing.

The Script File paths don't change, so there's nothing to update in the toolbox for most releases. If a release changes the tools' help text, re-apply it with the metadata script - see Tool metadata below.
A release that changes the tools' parameters or validation code should say so in its release notes (with the steps to update each tool by hand).

### Checking the installed version

    %VENV%\Scripts\python.exe -m fit_changedetector --version

### Restarting ArcGIS Pro

Pro caches the imported `changedetector_common.py` for the life of a session, from the location it was first loaded from. After an upgrade, or after changing a tool's Script File, restart Pro before the next run - otherwise the tool keeps running the old copy. If the old copy has since been deleted, the tool fails with `No Python environment found for <old path> ... (no pyvenv.cfg in any parent folder)`.

### Testing unreleased changes

Install the version to test into a separate venv (eg `\\GISWHSE.ENV.GOV.BC.CA\WHSE_NP\corp\central_venv\fit_changedetector_test`), and point a separate test toolbox's Script Files at that venv's installed scripts:

    set TESTVENV=\\GISWHSE.ENV.GOV.BC.CA\WHSE_NP\corp\central_venv\fit_changedetector_test
    %PY% -m uv venv %TESTVENV% --python %PY%
    %PY% -m uv pip install --python %TESTVENV% git+https://github.com/bcgov/FIT_changedetector.git@main

A branch name, tag or commit works after the `@`; installing from a git ref needs `git` available on the machine - otherwise install a built wheel instead. To pick up new commits, re-run the install with `--reinstall` and restart ArcGIS Pro.

## Parameters

Parameters 0-12 are identical for both tools. Each tool then adds its own tail, ending in a **Derived** output parameter that publishes the path of the file it wrote.

| # | Name | Suggested type | Required |
|---|------|-----------------|----------|
| 0 | original_fc | Feature Layer | Required |
| 1 | new_fc | Feature Layer | Required |
| 2 | out_folder | Folder | Required |
| 3 | primary_key | String | Optional |
| 4 | hash_fields | String, multivalue | Optional |
| 5 | fields | String, multivalue | Optional |
| 6 | ignore_fields | String, multivalue | Optional |
| 7 | precision | Double | Optional |
| 8 | hash_key | String | Optional |
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

The ArcGIS tools' default coordinate precision also differs from the CLI's. Left blank, the tool sets it from Original Feature Class's spatial reference: `1` for data in metres, or `0.00001` for data in degrees - both roughly 1m (0.00001° is about 1.1m of latitude, and 0.56-0.73m of longitude across BC). The CLI defaults to `0.01` (1cm) - adjusted to `0.0000001` (about 1cm) for data in degrees. So by default, a geometry change smaller than about 1m is reported by the CLI but UNCHANGED in ArcGIS - set Coordinate Precision explicitly to match the CLI.

The file geodatabase written by `changedetector_diff2gdb.py` stores 64-bit integer fields as Big Integer, rather than as floating point (Double), which cannot exactly represent every large value - eg a large id. Big Integer fields require ArcGIS Pro 3.2 or later.

## Tool metadata

Text for each tool's **Summary**, **Description**, **Usage** and **Syntax** (per-parameter help - each parameter's Dialog and Scripting Explanation), as shown in Edit Metadata.

Rather than pasting it in by hand, apply it with the script installed alongside the tools. Close the toolbox in ArcGIS Pro (or close Pro), then at a Windows command prompt:

    set PROPY="%PROGRAMFILES%\ArcGIS\Pro\bin\Python\Scripts\propy.bat"
    set METADATA=%VENV%\Lib\site-packages\fit_changedetector\arcgis\changedetector_metadata.py

    REM report what would be matched, without saving
    %PROPY% %METADATA% <path to toolbox .atbx> --dry-run

    REM apply
    %PROPY% %METADATA% <path to toolbox .atbx>

`propy.bat` runs the script with ArcGIS Pro's own Python (for `arcpy`). The tools must be named `diff2json` and `diff2gdb`; parameters are matched to the text below by their labels, and any parameter or text left unmatched is reported - rename the parameter's label (or edit the text below) to match. If a tool's metadata has never been edited, the script may find no parameters in it - open the tool's Edit Metadata view once and Save, then re-run.

The script reads the text below from this README, which is installed alongside it - so the text applied always matches the installed version of the tools.

### `changedetector_diff2json.py` (tool: diff2json)

**Summary:** Compares two feature classes and reports the differences as a JSON summary, with no spatial output.

**Description:** Compares an original and a new feature class - matched by primary key if one is given, otherwise by a generated hash key - and classifies every record as NEW, DELETED, UNCHANGED, MODIFIED_ATTR (attributes only), MODIFIED_GEOM (geometry only), or MODIFIED_BOTH. Writes a JSON file listing record counts per category, plus the primary key value(s) present in each category except UNCHANGED (a Duplicates category is added if duplicate primary keys are allowed). No spatial output is produced - use "Change Detector - Diff to GDB" instead if you need the actual changed features written out.

**Usage:** Wraps the `changedetector diff` command-line tool. Runs the CLI with the Python of the `fit_changedetector` environment it is installed in, rather than inside ArcGIS Pro's own Python (see the README alongside the tool scripts, in the fit_changedetector package's arcgis folder). Original and New Feature Class are matched by primary key if one is supplied; otherwise records are matched by a hash key generated from Fields to Include in Hash (required in that case - include the geometry field to match by geometry). There is no parameter for overriding the coordinate reference system used when hashing - geometries are hashed in their native CRS. Leave Output File Name blank to auto-generate a timestamped file name.

**Syntax:**
- **Original Feature Class** - The "before" dataset to compare.
- **New Feature Class** - The "after" dataset to compare against Original Feature Class.
- **Output Folder** - Folder where the JSON summary and the run's log file are written.
- **Primary Key** - A single column, common to both datasets, that uniquely identifies each record. If left blank, records are matched by a generated hash key instead - **Fields to Include in Hash** is then required (use this to match on a composite of multiple fields). Hidden once **Fields to Include in Hash** has a selection - clear that to supply a primary key instead.
- **Fields to Include in Hash** - The complete list of fields to fold into the generated hash key. Required when no primary key is supplied; cleared and hidden when one is. Include the geometry field (Shape) in this list to match records by geometry - omit it to hash on attributes only.
- **Fields to Compare** - Fields to compare for attribute changes; do not include the primary key. If left blank, all fields common to both datasets are compared.
- **Fields to Ignore** - Fields to exclude from the attribute comparison.
- **Coordinate Precision** - Coordinate precision used when hashing and comparing geometries, in the data's units. If left blank, set from Original Feature Class's spatial reference: `1` (metres) or `0.00001` (degrees) - both roughly 1m.
- **Hash Key** - Name of the column used to hold the generated hash key, when no primary key is supplied. Default: `fcd_hash_id`. Hidden when a primary key is supplied.
- **Suffix - Original** - Suffix appended to column names from Original Feature Class when reporting attribute differences. Default: `original`.
- **Suffix - New** - Suffix appended to column names from New Feature Class when reporting attribute differences. Default: `new`.
- **Drop Null Geometry** - Drop records with null geometry before comparing. Only valid when the geometry field is included in **Fields to Include in Hash**. Left unchecked, records with null geometry are kept and matched on their other hash fields alone - an error if the geometry field is the only hash field. Cleared and hidden when a primary key is supplied.
- **Allow Duplicate Primary Keys** - Do not fail on a duplicated primary key - instead, keep the first occurrence of each duplicated key (per source) and report the dropped records under a Duplicates category. Not applied when matching by geometry alone (no primary key or hash fields) - a duplicate there always fails, since geometry alone can't reliably pair records when more than one shares a location.
- **Output File Name** - Optional. Names the output JSON file and its log file. Leave blank to auto-generate a timestamped name instead.
- **Debug Logging** - Enable verbose (DEBUG level) logging.
- **Output File** *(Derived)* - Path of the JSON summary file written by this run.

### `changedetector_diff2gdb.py` (tool: diff2gdb)

**Summary:** Compares two feature classes and writes the differences as layers in a new file geodatabase.

**Description:** Compares an original and a new feature class - matched by primary key if one is given, otherwise by a generated hash key - and writes the results to a new file geodatabase, one layer per category of change: NEW, DELETED, MODIFIED_ATTR (attributes only), MODIFIED_GEOM (geometry only), MODIFIED_BOTH, and DUPLICATES (if duplicate primary keys are allowed). Optionally also writes copies of the two input layers, with the hash key added, for reference. Use "Change Detector - Diff (JSON Summary)" instead if you just need a quick count/summary without spatial output.

**Usage:** Wraps the `changedetector diff2gdb` command-line tool. Runs the CLI with the Python of the `fit_changedetector` environment it is installed in, rather than inside ArcGIS Pro's own Python (see the README alongside the tool scripts, in the fit_changedetector package's arcgis folder). Original and New Feature Class are matched by primary key if one is supplied; otherwise records are matched by a hash key generated from Fields to Include in Hash (required in that case - include the geometry field to match by geometry). Writes results as separate layers - NEW, DELETED, MODIFIED_ATTR, MODIFIED_GEOM, MODIFIED_BOTH, and DUPLICATES if duplicates are allowed - in a new file geodatabase. There is no parameter for overriding the coordinate reference system used when hashing - geometries are hashed in their native CRS. Leave Output File Name blank to auto-generate a timestamped name.

**Syntax:** same as diff2json for the parameters below, plus Dump Input Layers:
- **Original Feature Class**, **New Feature Class**, **Output Folder**, **Fields to Include in Hash**, **Fields to Compare**, **Fields to Ignore**, **Coordinate Precision**, **Hash Key**, **Suffix - Original**, **Suffix - New**, **Drop Null Geometry** - as in diff2json above.
- **Primary Key** - A single column, common to both datasets, that uniquely identifies each record. If left blank, records are matched by a generated hash key instead - **Fields to Include in Hash** is then required (use this to match on a composite of multiple fields). Leaving this blank forces **Dump Input Layers** on regardless of that parameter's own setting - see below. Hidden once **Fields to Include in Hash** has a selection - clear that to supply a primary key instead.
- **Allow Duplicate Primary Keys** - as in diff2json above.
- **Dump Input Layers** - Also write copies of the two input layers, with the generated hash key column added, into the output geodatabase for reference. Forced on automatically whenever a hash key had to be generated (Primary Key left blank) - the generated key only exists in that hashed copy, so dumping the inputs is how you can see which geometry/attribute values produced which hash. In that case, this happens regardless of how this parameter is set.
- **Output File Name** - Optional. Names the output `.gdb` and its log file. Leave blank to auto-generate a timestamped name instead.
- **Debug Logging** - Enable verbose (DEBUG level) logging.
- **Output File** *(Derived)* - Path of the file geodatabase written by this run.
