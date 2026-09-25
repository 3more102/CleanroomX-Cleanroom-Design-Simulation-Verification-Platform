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
        set "CLEANROOMX_PY=python"
        set "CLEANROOMX_PY_ARGS="
    )
)

if "%~1"=="" (
    "%CLEANROOMX_PY%" %CLEANROOMX_PY_ARGS% -m cleanroomx.gui --demo
) else (
    "%CLEANROOMX_PY%" %CLEANROOMX_PY_ARGS% -m cleanroomx.gui %*
)

exit /b %ERRORLEVEL%
