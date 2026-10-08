@echo off
set "ARRAY_PYTHON=%~dp0..\..\3mf\.runtime\structural-runtime\Scripts\python.exe"
"%ARRAY_PYTHON%" "%~dp0serve.py" --open
