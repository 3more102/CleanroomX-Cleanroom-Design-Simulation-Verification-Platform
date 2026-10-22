@echo off
setlocal
set "CLEANROOMX_LAUNCH_EXIT=2"
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
            goto :cleanroomx_launch_failed
        )
        set "CLEANROOMX_PY=python"
        set "CLEANROOMX_PY_ARGS="
    )
)

"%CLEANROOMX_PY%" %CLEANROOMX_PY_ARGS% -c "import sys; raise SystemExit(0 if (sys.version_info.major in range(4, 100) or (sys.version_info.major == 3 and sys.version_info.minor in range(11, 100))) else 1)" >nul 2>nul
if errorlevel 1 (
    echo CleanroomX requires Python 3.11 or newer. The selected interpreter does not satisfy this requirement. 1>&2
    goto :cleanroomx_launch_failed
)

"%CLEANROOMX_PY%" %CLEANROOMX_PY_ARGS% -c "import tkinter" >nul 2>nul
if errorlevel 1 (
    echo CleanroomX GUI requires Tkinter. Install a Python 3.11+ distribution with Tcl/Tk support, or recreate .venv with one. 1>&2
    goto :cleanroomx_launch_failed
)

if "%~1"=="" (
    "%CLEANROOMX_PY%" %CLEANROOMX_PY_ARGS% -m cleanroomx.gui --demo
) else (
    "%CLEANROOMX_PY%" %CLEANROOMX_PY_ARGS% -m cleanroomx.gui %*
)

set "CLEANROOMX_LAUNCH_EXIT=%ERRORLEVEL%"
if not "%CLEANROOMX_LAUNCH_EXIT%"=="0" goto :cleanroomx_launch_failed
exit /b 0

:cleanroomx_launch_failed
echo CleanroomX could not start. Review the error above. 1>&2
echo Startup tracebacks, when Python starts, are saved in %%LOCALAPPDATA%%\CleanroomX\Logs\cleanroomx-gui.log 1>&2
if "%~1"=="" if not "%CLEANROOMX_NO_PAUSE%"=="1" pause
exit /b %CLEANROOMX_LAUNCH_EXIT%
