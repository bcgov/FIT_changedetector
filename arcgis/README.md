# ArcGIS Pro script tools

Two script tools wrap the `changedetector` CLI (see the [main README](../README.md) for what the CLI itself does):

- `changedetector_diff.py` - wraps `diff`, prints a JSON summary
- `changedetector_diff2gdb.py` - wraps `diff2gdb`, writes results to a .gdb

Both require `changedetector_common.py` (shared logic - subprocess invocation, logging, CLI arg building) alongside them, and both run the CLI via [`uv`](https://docs.astral.sh/uv/)'s `uvx`, which resolves and caches an isolated `fit_changedetector` environment on demand - no venv, no `pip install`, nothing else to set up.

## Prerequisite

[Install uv](https://docs.astral.sh/uv/getting-started/installation/) on the machine running ArcGIS Pro, so `uv`/`uvx` are available at the command prompt.

## Setup

1. Download `fit_changedetector-arcgis-tools-<version>.zip` from the [latest release](https://github.com/bcgov/FIT_changedetector/releases/latest) and extract `changedetector_common.py`, `changedetector_diff.py`, `changedetector_diff2gdb.py` (and this README) to a target folder - wherever you point the tool's Script File (ArcGIS Pro adds that script's own folder to `sys.path`). See [Releases & versioning](#releases--versioning) below for why this is the recommended source rather than copying the files straight out of the repo.
2. In ArcGIS Pro's Catalog pane, add a new **Script** tool to a toolbox, and set its **Script File** to the entry-point script (`changedetector_diff.py` or `changedetector_diff2gdb.py`).
3. Add the tool's parameters, in order, per the table below.
4. Paste `changedetector_toolvalidator.py`'s contents into the tool's **Validation** tab - the same code works unmodified for both tools (it only touches parameters 0-8, which are identical between them).
5. Repeat for the second tool, if you want both.

## Parameters

Parameters 0-12 are identical for both tools. Each tool then adds its own tail, ending in a **Derived** output parameter that publishes the path of the file it wrote.

| # | Name | Suggested type | Required |
|---|------|-----------------|----------|
| 0 | original_fc | Feature Layer | Required |
| 1 | new_fc | Feature Layer | Required |
| 2 | out_folder | Folder | Required |
| 3 | primary_key | String, multivalue | Optional |
| 4 | fields | String, multivalue | Optional |
| 5 | ignore_fields | String, multivalue | Optional |
| 6 | hash_key | String | Optional |
| 7 | hash_fields | String, multivalue | Optional |
| 8 | precision | Double | Optional |
| 9 | suffix_a | String | Optional |
| 10 | suffix_b | String | Optional |
| 11 | drop_null_geometry | Boolean | Optional |
| 12 | allow_duplicates | Boolean | Optional |

`changedetector_diff.py` (`diff`):

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

## Releases & versioning

Each script tool shells out to a specific, pinned `fit_changedetector` version - `changedetector_common.py`'s `FIT_CHANGEDETECTOR_SPEC` - rather than "whatever's newest," so a tool's behavior can't shift between runs without someone explicitly changing that pin.

Note that the scripts in `arcgis/` committed in this repository are not guaranteed to match any real release. Instead, every tagged release (`vX.Y.Z`) automatically builds a correctly-pinned copy and attaches it to the matching [GitHub Release](https://github.com/bcgov/FIT_changedetector/releases) as `fit_changedetector-arcgis-tools-vX.Y.Z.zip` - this is what is deployed to ArcGIS systems as above. That archive's `FIT_CHANGEDETECTOR_SPEC` is generated fresh from the tag at release time, so it's always version-matched to the `fit_changedetector` release published to PyPI in the same run - it does not have to be kept in sync by hand.

### Testing against unreleased fit_changedetector changes

To test changes that are not on PyPI yet, temporarily point `FIT_CHANGEDETECTOR_SPEC` at a git ref or a local wheel/checkout path instead of a released version (`uvx --from` accepts either), then revert before merging:

    FIT_CHANGEDETECTOR_SPEC = "git+https://github.com/bcgov/FIT_changedetector.git@main"
