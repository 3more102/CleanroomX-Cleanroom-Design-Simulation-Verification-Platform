@echo off
setlocal
cd /d "%~dp0"

set "PYTHONPATH=%CD%\src;%PYTHONPATH%"

if exist ".venv\Scripts\python.exe" (
    set "CLEANROOMX_PY=.venv\Scripts\python.exe"
    set "CLEANROOMX_PY_ARGS="
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        set "CLEANROOMX_PY=py"
        set "CLEANROOMX_PY_ARGS=-3"
    ) else (
        where python >nul 2>nul
        if errorlevel 1 (
            echo CleanroomX requires Python 3.11 or newer, but no Python interpreter was found. 1>&2
            exit /b 2
        )
        set "CLEANROOMX_PY=python"
        set "CLEANROOMX_PY_ARGS="
    )
)

"%CLEANROOMX_PY%" %CLEANROOMX_PY_ARGS% -c "import sys; raise SystemExit(0 if sys.version_info ^>= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 (
    echo CleanroomX requires Python 3.11 or newer. The selected interpreter does not satisfy this requirement. 1>&2
    exit /b 2
)

"%CLEANROOMX_PY%" %CLEANROOMX_PY_ARGS% -c "import tkinter" >nul 2>nul
if errorlevel 1 (
    echo CleanroomX GUI requires Tkinter. Install a Python 3.11+ distribution with Tcl/Tk support, or recreate .venv with one. 1>&2
    exit /b 2
)

if "%~1"=="" (
    "%CLEANROOMX_PY%" %CLEANROOMX_PY_ARGS% -m cleanroomx.gui --demo
) else (
    "%CLEANROOMX_PY%" %CLEANROOMX_PY_ARGS% -m cleanroomx.gui %*
)

exit /b %ERRORLEVEL%
