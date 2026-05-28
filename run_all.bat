@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Change to the directory of this script
pushd "%~dp0"

rem Force UTF-8 for console and Python
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=UTF-8

rem Try to activate a local virtual environment if present
if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
) else if exist "venv\Scripts\activate.bat" (
  call "venv\Scripts\activate.bat"
) else (
  echo [i] No virtualenv found. Using system Python.
)

if not exist logs mkdir logs

for %%F in (cell_*.py) do (
  echo ==================================================================
  echo [%%~nxF] Starting at %DATE% %TIME%
  python -X utf8 "%%F" >> "logs\%%~nF.log" 2>&1
  if errorlevel 1 (
    echo [%%~nxF] FAILED. See logs\%%~nF.log
  ) else (
    echo [%%~nxF] OK
  )
)

popd
endlocal
