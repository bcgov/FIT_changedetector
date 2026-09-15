# Upgrading an existing ArcGIS Pro deployment

Most releases are a drop-in swap: download the new `fit_changedetector-arcgis-tools-<version>.zip`,
overwrite `changedetector_common.py`, `changedetector_diff2json.py`, `changedetector_diff2gdb.py`
in place, and restart ArcGIS Pro (it caches the imported `changedetector_common.py` for the life
of a session).

Some releases also require changes to the tool's **parameters** or **Validation** code, which
must be manually updated. This file lists those extra steps, newest release first.

## Unreleased (next release after v0.1.0a2)

**Breaking: Primary Key is now a single field, not a list.** `primary_key` no longer accepts
multiple/composite columns - a composite key now goes through **Fields to Include in Hash**
instead. See [#123](https://github.com/bcgov/FIT_changedetector/issues/123).

To upgrade an existing deployment:

1. Replace `changedetector_common.py`, `changedetector_diff2json.py`, `changedetector_diff2gdb.py`
   with the new versions (as usual).
2. In each tool's parameter list, retype parameter 3 (**Primary Key**) from **String, multivalue**
   to plain **String**. If it was previously set to accept more than one value, that setting must
   be changed by hand - ArcGIS Pro does not do this for you, and a tool left as multivalue will
   silently pass the wrong shape of data to the CLI and fail at run time.
3. Re-paste the updated `changedetector_toolvalidator.py` into each tool's **Validation** tab.
4. Restart ArcGIS Pro before the next run.
5. If any saved models, scripts, or scheduled tasks pass a comma-separated Primary Key value,
   update them to pass a single field name and move the other fields to **Fields to Include in
   Hash**.
