@echo off
setlocal
cd /d "%~dp0"

set "PYTHONPATH=%CD%\src;%PYTHONPATH%"

if "%~1"=="" (
    set "CLEANROOMX_ARGS=--demo"
) else (
    set "CLEANROOMX_ARGS=%*"
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m cleanroomx.gui %CLEANROOMX_ARGS%
    exit /b %ERRORLEVEL%
)

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    py -3 -m cleanroomx.gui %CLEANROOMX_ARGS%
    exit /b %ERRORLEVEL%
)

python -m cleanroomx.gui %CLEANROOMX_ARGS%
exit /b %ERRORLEVEL%
