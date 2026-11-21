"""Allow `python -m fit_changedetector ...` as an alternative to the
`changedetector` console script - eg for callers that know the interpreter
path but not where its console scripts were installed."""

from fit_changedetector.cli import cli

if __name__ == "__main__":
    # without prog_name, click would show `python -m fit_changedetector`
    # (or `__main__.py`) in usage/help text instead of the command's name
    cli(prog_name="changedetector")
