# Opt-in Windows launcher for the actual Foundation v10 CFD engine inside WSL.
# This script neither installs OpenFOAM nor claims that a solver run converged.
[CmdletBinding()]
param(
    [ValidateSet("Probe", "Run")]
    [string]$Mode = "Probe",
    [string]$CaseDirectory,
    [string]$Distribution = "Ubuntu",
    [ValidateRange(60, 86400)]
    [int]$TimeoutSeconds = 3600
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw "wsl.exe was not found. Enable WSL, install Ubuntu and OpenFOAM Foundation v10, then retry."
}

$pythonPrefix = @()
$venvPython = Join-Path $repo ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    $python = $venvPython
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $python = (Get-Command py).Source
    $pythonPrefix = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $python = (Get-Command python).Source
} else {
    throw "Python 3.11+ was not found on Windows."
}

& $python @pythonPrefix -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "CleanroomX requires Windows Python 3.11 or newer."
}

# The Windows interpreter runs only the bridge; the Linux interpreter inside
# WSL runs the solver and owns the actual OpenFOAM runtime.
$src = Join-Path $repo "src"
if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
    $env:PYTHONPATH = $src
} else {
    $env:PYTHONPATH = "$src;$env:PYTHONPATH"
}
$bridgeArgs = @(
    "-m", "cleanroomx.cfd_wsl_bridge",
    "--mode", $Mode.ToLowerInvariant(),
    "--repository", $repo,
    "--distribution", $Distribution,
    "--timeout-seconds", [string]$TimeoutSeconds
)
if ($Mode -eq "Run") {
    if ([string]::IsNullOrWhiteSpace($CaseDirectory)) {
        throw "Run mode requires -CaseDirectory pointing to a generated connected case."
    }
    $bridgeArgs += @("--case-directory", $CaseDirectory)
} elseif (-not [string]::IsNullOrWhiteSpace($CaseDirectory)) {
    throw "-CaseDirectory may only be used with -Mode Run."
}
& $python @pythonPrefix @bridgeArgs
exit $LASTEXITCODE
