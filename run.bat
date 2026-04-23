@echo off
setlocal

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "PYTHON_EXE=%ROOT%.venv\Scripts\python.exe"

if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" -m lmit.gui %*
    goto :done
)

echo [LMIT] .venv\Scripts\python.exe was not found.
echo [LMIT] Falling back to system Python. If this fails, create/install the venv first:
echo [LMIT]   python -m venv .venv
echo [LMIT]   .\.venv\Scripts\python -m pip install -e ".[dev]"
echo.

set "PYTHONPATH=%ROOT%src;%PYTHONPATH%"
py -m lmit.gui %*
if not errorlevel 9009 goto :done
python -m lmit.gui %*

:done
if errorlevel 1 (
    echo.
    echo [LMIT] GUI exited with error code %errorlevel%.
    pause
)

endlocal
