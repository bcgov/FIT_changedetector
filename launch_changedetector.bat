@echo off
call conda deactivate
call conda activate Q:\dss_workarea\_contractors\sinorris\conda_environments\changedetector_env
pythonw "%~dp0gui.py"