@echo off
setlocal
set "PREVIEW_PYTHON=%~dp0..\..\3mf\.runtime\structural-runtime\Scripts\python.exe"
if not exist "%PREVIEW_PYTHON%" (
  echo The local preview runtime was not found.
  pause
  exit /b 1
)
echo Open http://127.0.0.1:8866/ in your browser.
"%PREVIEW_PYTHON%" -B "%~dp0serve.py" --port 8866
