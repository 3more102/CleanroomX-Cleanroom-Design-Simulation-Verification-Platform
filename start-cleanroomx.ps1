[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CleanroomXArgs
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$pythonPrefix = @()
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $python = $venvPython
} else {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $python = $py.Source
        $pythonPrefix = @("-3")
    } else {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if (-not $pythonCommand) {
            throw "Python 3.11+ was not found. Install Python, or create .venv in the repository."
        }
        $python = $pythonCommand.Source
        $pythonPrefix = @()
    }
}

& $python @pythonPrefix -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "CleanroomX requires Python 3.11 or newer. The selected interpreter does not satisfy this requirement."
}

& $python @pythonPrefix -c "import tkinter"
if ($LASTEXITCODE -ne 0) {
    throw "CleanroomX GUI requires Tkinter. Install a Python 3.11+ distribution with Tcl/Tk support, or recreate .venv with one."
}

$src = Join-Path $repoRoot "src"
if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
    $env:PYTHONPATH = $src
} else {
    $env:PYTHONPATH = "$src;$env:PYTHONPATH"
}

if (-not $CleanroomXArgs -or $CleanroomXArgs.Count -eq 0) {
    $CleanroomXArgs = @("--demo")
}

if ($pythonPrefix) {
    & $python @pythonPrefix -m cleanroomx.gui @CleanroomXArgs
} else {
    & $python -m cleanroomx.gui @CleanroomXArgs
}
exit $LASTEXITCODE
