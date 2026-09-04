# ArcGIS Pro script tools

Two script tools wrap the `changedetector` CLI (see the [main README](../README.md) for what the CLI itself does):

- `changedetector_diff.py` - wraps `diff`, prints a JSON summary
- `changedetector_diff2gdb.py` - wraps `diff2gdb`, writes results to a .gdb

Both require `changedetector_common.py` (shared logic - subprocess invocation, logging, CLI arg building) alongside them, and both run the CLI via [`uv`](https://docs.astral.sh/uv/)'s `uvx`, which resolves and caches an isolated `fit_changedetector` environment on demand - no venv, no `pip install`, nothing else to set up.

## Prerequisite

[Install uv](https://docs.astral.sh/uv/getting-started/installation/) on the machine running ArcGIS Pro, so `uv`/`uvx` are available at the command prompt.

## Setup

1. Copy scripts `changedetector_common.py`, `changedetector_diff.py`, `changedetector_diff2gdb.py` to target folder - wherever you point the tool's Script File (ArcGIS Pro adds that script's own folder to `sys.path`).
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

## Testing against unreleased FIT_changedetector changes

`changedetector_common.py`'s `FIT_CHANGEDETECTOR_SPEC` pins the exact `fit_changedetector` version each run installs via `uvx`. To test changes that are not on PyPI yet, temporarily point it at a git ref or a local wheel/checkout path instead (`uvx --from` accepts either), then revert before merging:

    FIT_CHANGEDETECTOR_SPEC = "git+https://github.com/bcgov/FIT_changedetector.git@main"
