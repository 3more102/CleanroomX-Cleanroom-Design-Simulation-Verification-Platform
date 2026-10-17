# Publish the genuine CleanroomX GUI screenshot appendix to GitHub.
# Usage from repository root:
# powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\publish_illustrated_manual.ps1 -PackageZip "$HOME\Downloads\CleanroomX_Illustrated_Manual_Package.zip"
# No changes are made to PHOTONX EDA PCB.

param(
    [string]$PackageZip = "$HOME\Downloads\CleanroomX_Illustrated_Manual_Package.zip"
)

$ErrorActionPreference = 'Stop'
$branch = 'docs/cleanroomx-illustrated-manual-20261017'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

if (!(Test-Path (Join-Path $repo 'src\cleanroomx\gui.py'))) {
    throw 'This script must be in the real CleanroomX repository.'
}

Push-Location $repo
try {
    $top = (& git rev-parse --show-toplevel).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Not a Git checkout.' }
    if ((Resolve-Path $top).Path -ne (Resolve-Path $repo).Path) {
        throw 'CleanroomX is nested inside another Git checkout; refusing to modify it.'
    }
    $remote = (& git remote get-url origin).Trim()
    if ($LASTEXITCODE -ne 0 -or $remote -notmatch '3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform(\.git)?$') {
        throw "Unexpected GitHub remote: $remote"
    }
    $current = (& git branch --show-current).Trim()
    if ($current -ne $branch) {
        throw "Switch to the documentation branch first: git fetch origin; git switch --track origin/$branch"
    }
    $dirty = & git status --porcelain
    if ($LASTEXITCODE -ne 0 -or $dirty) {
        throw 'Uncommitted changes detected. Commit or stash them before running.'
    }

    if (!(Test-Path -LiteralPath $PackageZip)) {
        throw "Download the complete ZIP package first: $PackageZip"
    }

    $tmp = Join-Path ([IO.Path]::GetTempPath()) ('cleanroomx_manual_' + [guid]::NewGuid().ToString('N'))
    try {
        Expand-Archive -LiteralPath $PackageZip -DestinationPath $tmp -Force
        $imagesFrom = Join-Path $tmp 'docs\images\cleanroomx_gui_real'
        $manifestFrom = Join-Path $tmp 'docs\GUI_Screenshot_Manifest.json'
        $appendixFrom = Join-Path $tmp 'docs\GUI_SCREENSHOTS_APPENDIX.md'
        $pdfFrom = Join-Path $tmp 'CleanroomX_Illustrated_Manual_2026-10-17.pdf'
        foreach ($file in @($manifestFrom, $appendixFrom, $pdfFrom)) {
            if (!(Test-Path -LiteralPath $file)) { throw "Missing package file: $file" }
        }

        $manifest = Get-Content -LiteralPath $manifestFrom -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($manifest.screenshot_count -ne 15 -or $manifest.screenshots.Count -ne 15) {
            throw 'Screenshot manifest must contain exactly 15 real captures.'
        }

        foreach ($entry in $manifest.screenshots) {
            if ($entry.file -notmatch '^[0-9]{2}_[a-z0-9_]+\.png$') {
                throw "Unsafe screenshot filename: $($entry.file)"
            }
            $file = Join-Path $imagesFrom $entry.file
            if (!(Test-Path -LiteralPath $file)) { throw "Missing screenshot: $file" }
            $actual = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($actual -ne $entry.sha256.ToLowerInvariant()) {
                throw "Screenshot SHA-256 mismatch: $($entry.file)"
            }
        }

        $destImages = Join-Path $repo 'docs\images\cleanroomx_gui_real'
        New-Item -ItemType Directory -Force -Path $destImages | Out-Null
        Copy-Item -Path (Join-Path $imagesFrom '*.png') -Destination $destImages -Force
        Copy-Item -LiteralPath $manifestFrom -Destination (Join-Path $repo 'docs\GUI_Screenshot_Manifest.json') -Force
        Copy-Item -LiteralPath $appendixFrom -Destination (Join-Path $repo 'docs\GUI_SCREENSHOTS_APPENDIX.md') -Force
        Copy-Item -LiteralPath $pdfFrom -Destination (Join-Path $repo 'docs\CleanroomX_Illustrated_Manual_2026-10-17.pdf') -Force

        $manualSource = Join-Path $repo 'docs\CleanroomX_Complete_Solution_Manual_2026-09-30.md'
        if (!(Test-Path -LiteralPath $manualSource)) { throw 'Controlled Markdown manual not found.' }
        $target = Join-Path $repo 'docs\CleanroomX_Complete_Solution_Manual_Illustrated.md'
        $base = (Get-Content -LiteralPath $manualSource -Raw -Encoding UTF8).TrimEnd()
        $appendix = Get-Content -LiteralPath $appendixFrom -Raw -Encoding UTF8
        [IO.File]::WriteAllText($target, $base + [Environment]::NewLine + [Environment]::NewLine + $appendix, [Text.UTF8Encoding]::new($false))

        $readmePath = Join-Path $repo 'README.md'
        $readme = Get-Content -LiteralPath $readmePath -Raw -Encoding UTF8
        if (!$readme.Contains('CleanroomX_Illustrated_Manual_2026-10-17.pdf')) {
            $section = @'

### Illustrated GUI manual (real screenshots)

- [Illustrated engineering manual, 17 October 2026 (PDF)](docs/CleanroomX_Illustrated_Manual_2026-10-17.pdf)
- [Illustrated manual source (Markdown)](docs/CleanroomX_Complete_Solution_Manual_Illustrated.md)
- [Actual desktop screenshots and limitations](docs/GUI_SCREENSHOTS_APPENDIX.md)

The screenshots show a development GUI demo; they do not establish physical CFD validation or ISO certification.

'@
            if ($readme.Contains('## Documentation')) {
                $readme = $readme.Replace('## Documentation', '## Documentation' + [Environment]::NewLine + $section)
            } else {
                $readme += [Environment]::NewLine + $section
            }
            [IO.File]::WriteAllText($readmePath, $readme, [Text.UTF8Encoding]::new($false))
        }

        & git add -- docs/images/cleanroomx_gui_real docs/GUI_Screenshot_Manifest.json docs/GUI_SCREENSHOTS_APPENDIX.md docs/CleanroomX_Illustrated_Manual_2026-10-17.pdf docs/CleanroomX_Complete_Solution_Manual_Illustrated.md README.md
        if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
        & git commit -m 'docs: publish illustrated engineering manual with 15 actual GUI screenshots'
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        & git push -u origin $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed; check GitHub authorization.' }
        Write-Host "SUCCESS: illustrated manual, PDF and 15 authentic screenshots pushed to $branch" -ForegroundColor Green
    }
    finally {
        if (Test-Path -LiteralPath $tmp) {
            Remove-Item -LiteralPath $tmp -Recurse -Force
        }
    }
}
finally {
    Pop-Location
}
