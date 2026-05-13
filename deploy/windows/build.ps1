<#
.SYNOPSIS
    PyInstaller build orchestration for pechepro v0.1 Windows .exe.

.DESCRIPTION
    1. Verifies the test suite (pytest -m "not smoke") passes - release gate.
    2. Cleans previous dist/ and build/ folders.
    3. Runs PyInstaller against deploy/windows/pechepro.spec to produce
       dist/pechepro.exe.
    4. Verifies the .exe exists and is under the size cap (default 60 MB).
    5. Smoke-launches the .exe for ~5 s, then terminates the process to
       confirm bootstrap does not crash immediately.
    6. Prints a success line with the path and final size.

    Inno Setup wrapping into pechepro-setup.exe is handled by a separate
    script (deploy/windows/installer.iss + partner-agent build extension).

.PARAMETER SkipTests
    If set, skips the pytest gate (faster local iteration). NOT recommended
    for CI or release builds.

.PARAMETER SkipSmoke
    If set, skips the 5-second smoke-launch step. Useful on headless
    environments without a desktop session.

.PARAMETER MaxSizeMB
    Maximum allowed .exe size in MB. Default: 60. Per spec section 13.

.EXAMPLE
    pwsh deploy/windows/build.ps1
    pwsh deploy/windows/build.ps1 -SkipTests -SkipSmoke
    pwsh deploy/windows/build.ps1 -MaxSizeMB 80
#>
[CmdletBinding()]
param(
    [switch] $SkipTests,
    [switch] $SkipSmoke,
    [int]    $MaxSizeMB = 60
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Repo root = grandparent of this script (deploy/windows/build.ps1 -> ../..)
$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $RepoRoot

Write-Host "==> pechepro build pipeline" -ForegroundColor Cyan
Write-Host "    Repo root:  $RepoRoot"
Write-Host "    PowerShell: $($PSVersionTable.PSVersion)"

# Resolve the venv Python - prefer worktree-local venv, fallback to repo-root venv.
$pythonCandidates = @(
    (Join-Path $RepoRoot ".venv\Scripts\python.exe"),
    "D:\pechepro\.venv\Scripts\python.exe"
)
$pythonFound = @($pythonCandidates | Where-Object { Test-Path $_ })

if ($pythonFound.Count -eq 0) {
    throw "Cannot find a Python venv. Create one with 'python -m venv .venv' and 'pip install -e .[dev,build]'"
}
$python = $pythonFound[0]
Write-Host "    Python:     $python"
& $python --version

$buildStart = Get-Date

# ---- Step 1: pytest gate ----
if ($SkipTests) {
    Write-Host "==> [1/5] pytest gate SKIPPED (-SkipTests)" -ForegroundColor Yellow
} else {
    Write-Host "==> [1/5] pytest gate (-m 'not smoke')" -ForegroundColor Cyan
    & $python -m pytest -q -m "not smoke" --tb=no
    if ($LASTEXITCODE -ne 0) {
        throw "pytest failed with exit code $LASTEXITCODE - fix tests before building"
    }
}

# ---- Step 2: Clean previous artifacts ----
Write-Host "==> [2/5] Cleaning dist/ and build/" -ForegroundColor Cyan
foreach ($dir in @("dist", "build")) {
    $path = Join-Path $RepoRoot $dir
    if (Test-Path $path) {
        Remove-Item -Recurse -Force $path
        Write-Host "    removed $dir/"
    }
}

# ---- Step 3: PyInstaller ----
Write-Host "==> [3/5] PyInstaller build" -ForegroundColor Cyan
$specPath = "deploy\windows\pechepro.spec"
if (-not (Test-Path $specPath)) {
    throw "Spec file not found: $specPath"
}

& $python -m PyInstaller --noconfirm --clean --log-level=INFO $specPath
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$exePath = Join-Path $RepoRoot "dist\pechepro.exe"
if (-not (Test-Path $exePath)) {
    throw "Expected output not found: $exePath"
}

# ---- Step 4: Size check ----
Write-Host "==> [4/5] Size check (cap $MaxSizeMB MB)" -ForegroundColor Cyan
$exeSize = (Get-Item $exePath).Length / 1MB
Write-Host ("    pechepro.exe: {0:N2} MB" -f $exeSize)

if ($exeSize -gt $MaxSizeMB) {
    throw ("Executable too large: {0:N2} MB > {1} MB cap. Reduce hidden imports or excludes in pechepro.spec." -f $exeSize, $MaxSizeMB)
}

# ---- Step 5: Smoke launch ----
# Goal: prove the bootstrap (PyInstaller unpack + Python init + Flask thread)
# doesn't crash with a non-zero exit code. The PyWebView window can either
# stay open (interactive desktop session - process stays alive past 5 s) or
# return cleanly (non-interactive / headless / no Edge WebView2 attached -
# webview.start() returns without blocking). Both are acceptable; the only
# failure is a non-zero exit code, which signals a real bootstrap crash
# (missing DLL, ImportError, etc.).
if ($SkipSmoke) {
    Write-Host "==> [5/5] Smoke launch SKIPPED (-SkipSmoke)" -ForegroundColor Yellow
} else {
    Write-Host "==> [5/5] Smoke launch (up to 5 s)" -ForegroundColor Cyan
    $proc = Start-Process -FilePath $exePath -PassThru
    $waitedMs = 0
    while (-not $proc.HasExited -and $waitedMs -lt 5000) {
        Start-Sleep -Milliseconds 250
        $waitedMs += 250
    }

    if ($proc.HasExited) {
        $exit = $proc.ExitCode
        if ($exit -ne 0) {
            throw "Smoke launch failed: process exited with non-zero code $exit"
        }
        Write-Host ("    launch OK (clean exit code 0 within {0:N1} s; window did not block - non-interactive session)" -f ($waitedMs / 1000))
    } else {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        Write-Host "    launch OK (process alive after 5 s, terminated cleanly)"
    }
}

$buildEnd = Get-Date
$elapsed = ($buildEnd - $buildStart).TotalSeconds

Write-Host ""
Write-Host "==> Build OK" -ForegroundColor Green
Write-Host ("    {0} ({1:N2} MB)" -f $exePath, $exeSize)
Write-Host ("    elapsed: {0:N1} s" -f $elapsed)
