# Captures a genuine CleanroomX GUI window, not a fabricated rendering.
# Run on a Windows desktop with Python and CleanroomX installed.
param(
    [string] $PythonExe = "pythonw.exe",
    [string] $OutputDir = "reports/gui_reference_parity",
    [int] $Width = 1920,
    [int] $Height = 1080
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($Width -lt 640 -or $Height -lt 480) {
    throw "Capture window must be at least 640x480."
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class CleanroomXWindowCapture {
    [StructLayout(LayoutKind.Sequential)]
    public struct Rect {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }
    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr window, out Rect bounds);
    [DllImport("user32.dll")]
    public static extern bool SetWindowPos(
        IntPtr window, IntPtr insertAfter,
        int x, int y, int width, int height, uint flags
    );
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr window);
}
"@

$command = Get-Command $PythonExe -ErrorAction Stop
$virtualScreen = [System.Windows.Forms.SystemInformation]::VirtualScreen
if ($virtualScreen.Width -lt $Width -or $virtualScreen.Height -lt $Height) {
    throw "Desktop resolution is too small for a ${Width}x${Height} capture."
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$target = (Resolve-Path $OutputDir).Path
$process = Start-Process -FilePath $command.Source -ArgumentList @(
    "-m", "cleanroomx.gui", "--demo"
) -PassThru

try {
    $window = [IntPtr]::Zero
    for ($iteration = 0; $iteration -lt 60; $iteration++) {
        Start-Sleep -Milliseconds 250
        $process.Refresh()
        if ($process.HasExited) {
            throw "Demo process exited before a GUI window appeared."
        }
        $window = $process.MainWindowHandle
        if ($window -ne [IntPtr]::Zero) { break }
    }
    if ($window -eq [IntPtr]::Zero) {
        throw "No visible CleanroomX window was found."
    }

    # The measured dimensions include Windows window decorations.
    if (-not [CleanroomXWindowCapture]::SetWindowPos(
        $window, [IntPtr]::Zero, $virtualScreen.Left,
        $virtualScreen.Top, $Width, $Height, 0x0040
    )) {
        throw "Could not resize the CleanroomX window."
    }
    [void][CleanroomXWindowCapture]::SetForegroundWindow($window)
    Start-Sleep -Milliseconds 1000
    $rect = New-Object CleanroomXWindowCapture+Rect
    if (-not [CleanroomXWindowCapture]::GetWindowRect($window, [ref]$rect)) {
        throw "Could not read CleanroomX window geometry."
    }

    $captureWidth = $rect.Right - $rect.Left
    $captureHeight = $rect.Bottom - $rect.Top
    if ($captureWidth -le 0 -or $captureHeight -le 0) {
        throw "The CleanroomX window has invalid dimensions."
    }

    $bitmap = [System.Drawing.Bitmap]::new($captureWidth, $captureHeight)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen(
            $rect.Left, $rect.Top, 0, 0,
            [System.Drawing.Size]::new($captureWidth, $captureHeight)
        )
        $imagePath = Join-Path $target "design_studio_actual.png"
        $bitmap.Save($imagePath, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
    $sha = (Get-FileHash -Path $imagePath -Algorithm SHA256).Hash
    $gitHead = (& git rev-parse HEAD 2>$null)
    $receipt = @{
        kind = "genuine-windows-screen-capture"
        captured_at_utc = [DateTime]::UtcNow.ToString("o")
        command = "pythonw.exe -m cleanroomx.gui --demo"
        git_head = "$gitHead".Trim()
        screenshot = "design_studio_actual.png"
        screenshot_sha256 = $sha
        screenshot_width_px = $captureWidth
        screenshot_height_px = $captureHeight
        reference_parity_verified = $false
        solver_integration_verified = $false
    }
    $receipt | ConvertTo-Json -Depth 5 |
        Set-Content (Join-Path $target "capture_receipt.json") -Encoding UTF8
    Write-Host "Real screenshot: $imagePath"
    Write-Host "SHA-256: $sha"
}
finally {
    if (-not $process.HasExited) { $process.Kill() }
    $process.Dispose()
}
