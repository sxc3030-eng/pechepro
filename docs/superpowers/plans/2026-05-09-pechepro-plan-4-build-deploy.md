# Pechepro Plan 4 — Build & Deploy Implementation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package pechepro v0.1 into a Windows `.exe` + Inno Setup installer, automate the release via GitHub Actions on tag, and provide a 20-scenario smoke checklist for manual QA on a clean Windows VM.

**Architecture:** PyInstaller bundles the Python app + assets into a single `pechepro.exe`. Inno Setup wraps it in `pechepro-setup.exe` with Start Menu / Desktop shortcuts. GitHub Actions on `windows-latest` builds and publishes the artifact on every `v*` tag push. Code signing deferred to V0.2.

**Tech Stack:** PyInstaller 6.11.1 · Inno Setup 6 · GitHub Actions (windows-latest, Chocolatey) · Python 3.13 · PowerShell 7

**Worktree:** `D:\pechepro\.claude\worktrees\plan-4-build-deploy` on branch `plan/build-deploy`

---

## Spec coverage

| Spec section | Couvert par |
|---|---|
| §3.6 Build & distribution (PyInstaller .spec, Inno Setup .iss, sign script) | Tasks 1–10 |
| §11 Risks (SmartScreen, antivirus false-positives) | Tasks 4, 9, 11 |
| §13 Done criteria (smoke checklist 20 scenarios, ≤60 MB) | Tasks 5, 11, 16 |

## Prerequisites

Before this plan starts, the following must be true on `main` (verify with `git log` and a clean clone):

- [ ] Tag `phase-1-implementation` exists on `main`
- [ ] `app/shell.py`, `app/server.py`, `app/services/*`, `app/db/*`, `app/templates/*`, `app/static/*`, `app/locales/*` all present
- [ ] `data/curated/species.csv`, `regions.csv`, `water_types.csv`, `lures.csv`, `color_visibility.csv`, `tips.csv`, `solunar_rules.csv`, `baro_rules.csv` all populated
- [ ] `pyproject.toml` declares `[build]` extra with `pyinstaller==6.11.1`
- [ ] `pytest` passes ≥80% coverage on `app/`, `pytest -m smoke` passes
- [ ] Inno Setup 6 installed locally for dev (CI installs it via Chocolatey)

If any prereq is missing, STOP and resolve in plan-1/2/3 first.

## Worktree setup

```powershell
cd D:\pechepro
git fetch --tags
git checkout main
git pull --ff-only
git worktree add .claude\worktrees\plan-4-build-deploy -b plan/build-deploy phase-1-implementation
cd .claude\worktrees\plan-4-build-deploy
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev,build]"
```

---

## Task 1 : Create PyInstaller spec file

**Files:**
- Create: `D:\pechepro\deploy\windows\pechepro.spec`

- [ ] **Step 1: Write `deploy/windows/pechepro.spec`**

```python
# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for pechepro v0.1 — Windows one-file build.

Bundles:
  - app/db/schema.sql + app/db/migrations/*.sql
  - data/curated/*.csv (8 files: species, regions, water_types, lures,
    color_visibility, tips, solunar_rules, baro_rules)
  - app/templates/* (Jinja2)
  - app/static/* (CSS, JS, images)
  - app/locales/* (gettext .mo files for FR/EN)

Hidden imports declared explicitly because PyInstaller's static analysis
misses dynamic imports inside pywebview, astral, and winsdk.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Repository root = parent of deploy/windows/
REPO_ROOT = Path(SPECPATH).resolve().parent.parent

block_cipher = None

# Bundled data files: (source_on_disk, target_inside_exe)
datas = [
    (str(REPO_ROOT / "app" / "db" / "schema.sql"), "app/db"),
    (str(REPO_ROOT / "app" / "db" / "migrations"), "app/db/migrations"),
    (str(REPO_ROOT / "data" / "curated"), "data/curated"),
    (str(REPO_ROOT / "app" / "templates"), "app/templates"),
    (str(REPO_ROOT / "app" / "static"), "app/static"),
    (str(REPO_ROOT / "app" / "locales"), "app/locales"),
]

# Pull astral's geo database (timezone + city lookups)
datas += collect_data_files("astral")

# Hidden imports — modules pulled in dynamically that PyInstaller misses
hiddenimports = [
    "pkg_resources",
    "pkg_resources.extern",
    "astral.geocoder",
    "astral.location",
    "astral.sun",
    "astral.moon",
    "skyfield.api",
    "skyfield.almanac",
    "winsdk.windows.devices.geolocation",
    "winsdk.windows.foundation",
    "webview.platforms.edgechromium",
    "flask",
    "jinja2.ext",
]

# Collect all submodules of these packages so dynamic imports resolve
hiddenimports += collect_submodules("winsdk")
hiddenimports += collect_submodules("astral")

a = Analysis(
    [str(REPO_ROOT / "app" / "shell.py")],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Strip large unused stdlib modules to shrink the .exe
        "tkinter",
        "test",
        "unittest",
        "pydoc",
        "doctest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="pechepro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                  # UPX often triggers AV false-positives — disabled
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,              # GUI app — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(REPO_ROOT / "app" / "static" / "img" / "logo.ico"),
    version=str(REPO_ROOT / "deploy" / "windows" / "version_info.txt"),
)
```

- [ ] **Step 2: Create `deploy/windows/version_info.txt`** (Windows version resource)

```
# UTF-8
#
# For more details about fixed file info 'ffi' see:
# http://msdn.microsoft.com/en-us/library/ms646997.aspx
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(0, 1, 0, 0),
    prodvers=(0, 1, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
    ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'Master / sxc3030-eng'),
        StringStruct(u'FileDescription', u'Pechepro — Application Windows de pêche Amérique du Nord'),
        StringStruct(u'FileVersion', u'0.1.0.0'),
        StringStruct(u'InternalName', u'pechepro'),
        StringStruct(u'LegalCopyright', u'Copyright (c) 2026 Master / sxc3030-eng. All rights reserved.'),
        StringStruct(u'OriginalFilename', u'pechepro.exe'),
        StringStruct(u'ProductName', u'Pechepro'),
        StringStruct(u'ProductVersion', u'0.1.0')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
```

- [ ] **Step 3: Verify spec file is syntactically valid Python**

Run from repo root:
```powershell
python -c "exec(open('deploy/windows/pechepro.spec').read(), {'SPECPATH': 'deploy/windows', 'Analysis': lambda *a, **k: None, 'PYZ': lambda *a, **k: None, 'EXE': lambda *a, **k: None})"
```
Expected: no output, exit code 0 (purely a syntax check — won't actually build).

- [ ] **Step 4: Commit**

```powershell
git add deploy\windows\pechepro.spec deploy\windows\version_info.txt
git commit -m "build(plan-4): add PyInstaller spec + Windows version resource"
```

---

## Task 2 : Create build orchestration script

**Files:**
- Create: `D:\pechepro\deploy\windows\build.ps1`

- [ ] **Step 1: Write `deploy/windows/build.ps1`**

```powershell
<#
.SYNOPSIS
    Local + CI build orchestration for pechepro Windows installer.

.DESCRIPTION
    1. Cleans dist/ and build/ folders.
    2. Runs PyInstaller against deploy/windows/pechepro.spec → dist/pechepro.exe.
    3. Runs Inno Setup against deploy/windows/installer.iss → dist/pechepro-setup.exe.
    4. Verifies the resulting installer is < 60 MB.

.PARAMETER SkipInno
    If set, skips Inno Setup compilation (used for quick PyInstaller-only iteration).

.PARAMETER MaxSizeMB
    Maximum allowed installer size in MB. Default: 60.

.EXAMPLE
    pwsh deploy/windows/build.ps1
#>
[CmdletBinding()]
param(
    [switch] $SkipInno,
    [int]    $MaxSizeMB = 60
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Repo root = grandparent of this script
$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $RepoRoot

Write-Host "==> pechepro build pipeline" -ForegroundColor Cyan
Write-Host "    Repo root: $RepoRoot"
Write-Host "    PowerShell: $($PSVersionTable.PSVersion)"
Write-Host "    Python:     $(python --version)"

# ---- Step 1: Clean previous artifacts ----
Write-Host "==> [1/4] Cleaning dist/ and build/" -ForegroundColor Cyan
foreach ($dir in @("dist", "build")) {
    $path = Join-Path $RepoRoot $dir
    if (Test-Path $path) {
        Remove-Item -Recurse -Force $path
        Write-Host "    removed $dir/"
    }
}

# ---- Step 2: PyInstaller ----
Write-Host "==> [2/4] PyInstaller build" -ForegroundColor Cyan
$specPath = "deploy\windows\pechepro.spec"
& pyinstaller --noconfirm --clean --log-level=INFO $specPath
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$exePath = Join-Path $RepoRoot "dist\pechepro.exe"
if (-not (Test-Path $exePath)) {
    throw "Expected output not found: $exePath"
}
$exeSize = (Get-Item $exePath).Length / 1MB
Write-Host ("    pechepro.exe: {0:N2} MB" -f $exeSize)

# ---- Step 3: Inno Setup ----
if ($SkipInno) {
    Write-Host "==> [3/4] Inno Setup SKIPPED (--SkipInno)" -ForegroundColor Yellow
    return
}

Write-Host "==> [3/4] Inno Setup compile" -ForegroundColor Cyan

# Locate ISCC.exe — prefer x64 install, fall back to x86 and PATH
$isccCandidates = @(
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ }
$iscc = if ($isccCandidates) { $isccCandidates[0] } else { (Get-Command ISCC -ErrorAction SilentlyContinue).Source }
if (-not $iscc) {
    throw "Inno Setup 6 not found. Install via 'choco install innosetup -y' or download from jrsoftware.org."
}
Write-Host "    using: $iscc"

$issPath = Join-Path $RepoRoot "deploy\windows\installer.iss"
& $iscc $issPath
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed with exit code $LASTEXITCODE"
}

$setupPath = Join-Path $RepoRoot "dist\pechepro-setup.exe"
if (-not (Test-Path $setupPath)) {
    throw "Expected installer not found: $setupPath"
}

# ---- Step 4: Size check ----
Write-Host "==> [4/4] Size check (max $MaxSizeMB MB)" -ForegroundColor Cyan
$setupSize = (Get-Item $setupPath).Length / 1MB
Write-Host ("    pechepro-setup.exe: {0:N2} MB" -f $setupSize)

if ($setupSize -gt $MaxSizeMB) {
    throw "Installer too large: $([Math]::Round($setupSize, 2)) MB > $MaxSizeMB MB cap"
}

Write-Host ""
Write-Host "==> Build OK" -ForegroundColor Green
Write-Host "    $setupPath ($([Math]::Round($setupSize, 2)) MB)"
```

- [ ] **Step 2: Verify the script parses cleanly**

Run from repo root:
```powershell
powershell -NoProfile -Command "Get-Command -Syntax -Name '.\deploy\windows\build.ps1'"
```
Expected: prints the script's parameter syntax with no parse errors.

- [ ] **Step 3: Dry-run (PyInstaller-only, skip Inno)** — exercises the cleanup + spec compile path:

```powershell
pwsh deploy\windows\build.ps1 -SkipInno
```
Expected: ends with `[3/4] Inno Setup SKIPPED`. `dist\pechepro.exe` exists. (Will fail later if Phase 1 isn't merged — that's fine, just verify the orchestration logic.)

- [ ] **Step 4: Commit**

```powershell
git add deploy\windows\build.ps1
git commit -m "build(plan-4): add build.ps1 orchestrator (clean -> pyinstaller -> inno -> size check)"
```

---

## Task 3 : Create Inno Setup installer script

**Files:**
- Create: `D:\pechepro\deploy\windows\installer.iss`

- [ ] **Step 1: Generate a fresh GUID for AppId**

Run:
```powershell
[guid]::NewGuid().ToString().ToUpper()
```
Record the output (example: `7F4C2A89-3BD1-4E1F-9A65-2C8D7F1B0E03`). Use it in the next step in place of `<APP_ID_GUID>`.

- [ ] **Step 2: Write `deploy/windows/installer.iss`** (replace `<APP_ID_GUID>` with the GUID from Step 1)

```iss
; Inno Setup 6 script for Pechepro v0.1
; Builds dist\pechepro-setup.exe from dist\pechepro.exe
; No admin rights required — installs into %LOCALAPPDATA%\Programs\pechepro

#define MyAppName       "Pechepro"
#define MyAppVersion    "0.1.0"
#define MyAppPublisher  "Master / sxc3030-eng"
#define MyAppURL        "https://github.com/sxc3030-eng/pechepro"
#define MyAppExeName    "pechepro.exe"
#define MyAppId         "{<APP_ID_GUID>}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases

; userpf = %LOCALAPPDATA%\Programs — no admin required
DefaultDirName={userpf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

OutputDir=..\..\dist
OutputBaseFilename=pechepro-setup
SetupIconFile=..\..\app\static\img\logo.ico
LicenseFile=..\..\LICENSE

Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=auto

UninstallDisplayName={#MyAppName} {#MyAppVersion}
UninstallDisplayIcon={app}\{#MyAppExeName}

ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "english";  MessagesFile: "compiler:Default.isl"
Name: "french";   MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon";   Description: "{cm:CreateDesktopIcon}";   GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "startmenuicon"; Description: "Add Start Menu shortcut";  GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\dist\pechepro.exe"; DestDir: "{app}"; Flags: ignoreversion
; LICENSE + README are bundled inside the .exe by PyInstaller, but copy them
; alongside for transparency:
Source: "..\..\LICENSE";    DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\README.md";  DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}";       Filename: "{app}\{#MyAppExeName}"; Tasks: startmenuicon
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}";    Tasks: startmenuicon
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up __pycache__ and any temp PyInstaller extracts. Leave user data
; (%LOCALAPPDATA%\pechepro\pechepro.db) intact — see SMOKE_CHECKLIST scenario 19.
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
function InitializeSetup(): Boolean;
begin
  // Refuse to run on Windows < 10 — pywebview + Edge WebView2 require Win10+
  if not IsWindows10OrNewer() then
  begin
    MsgBox('Pechepro requires Windows 10 or newer.', mbError, MB_OK);
    Result := False;
    exit;
  end;
  Result := True;
end;

function IsWindows10OrNewer(): Boolean;
var
  Version: TWindowsVersion;
begin
  GetWindowsVersionEx(Version);
  Result := (Version.Major >= 10);
end;
```

- [ ] **Step 3: Verify Inno Setup is installed and the script compiles**

(Phase 1 must be merged for the .exe to exist; if not, this step is deferred to Task 5.)

```powershell
$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) { $iscc = "$env:ProgramFiles\Inno Setup 6\ISCC.exe" }
& $iscc /? | Select-Object -First 5
```
Expected: prints Inno Setup help banner. If not found, run `choco install innosetup -y` (admin) or download manually.

- [ ] **Step 4: Commit**

```powershell
git add deploy\windows\installer.iss
git commit -m "build(plan-4): add Inno Setup installer script (no-admin, userpf install)"
```

---

## Task 4 : Create code-signing placeholder

**Files:**
- Create: `D:\pechepro\deploy\windows\sign.ps1`

- [ ] **Step 1: Write `deploy/windows/sign.ps1`**

```powershell
<#
.SYNOPSIS
    Code-signing wrapper for pechepro v0.1+ installer.

.DESCRIPTION
    V0.1: STUB — prints "code signing pending" and exits 0.
    V0.2: Will use signtool.exe with a code-signing certificate
          (DigiCert / Sectigo / SSL.com EV cert pending budget approval).

    Once a certificate is available, replace the V0.2 block below with:
        signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 `
                      /a /n "Master / sxc3030-eng" $TargetPath

.PARAMETER TargetPath
    Path to the .exe to sign. Defaults to dist\pechepro-setup.exe.

.NOTES
    Mitigates SmartScreen "Unknown publisher" warning (spec §11). V0.1 ships
    unsigned — users see "Run anyway" prompt on first launch. Acceptable for
    closed beta; required to fix before public distribution at >100 users.
#>
[CmdletBinding()]
param(
    [string] $TargetPath = "dist\pechepro-setup.exe"
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
$resolved = Join-Path $RepoRoot $TargetPath

Write-Host "==> sign.ps1" -ForegroundColor Cyan
Write-Host "    Target: $resolved"

if (-not (Test-Path $resolved)) {
    Write-Host "    SKIP: target file not found (build first)" -ForegroundColor Yellow
    exit 0
}

# ---- V0.1 STUB ----
Write-Host "    V0.1: code signing pending — installer is unsigned" -ForegroundColor Yellow
Write-Host "    SmartScreen warning expected on first launch (spec §11)" -ForegroundColor Yellow
Write-Host "    See deploy/windows/sign.ps1 docstring for V0.2 unlock plan"
exit 0

# ---- V0.2 (uncomment once cert is acquired) ----
# $signtool = "${env:ProgramFiles(x86)}\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe"
# if (-not (Test-Path $signtool)) {
#     throw "signtool.exe not found — install Windows 10 SDK"
# }
# & $signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a /n "Master / sxc3030-eng" $resolved
# if ($LASTEXITCODE -ne 0) { throw "signtool failed: $LASTEXITCODE" }
# Write-Host "    Signed: OK" -ForegroundColor Green
```

- [ ] **Step 2: Verify the stub runs without error**

```powershell
pwsh deploy\windows\sign.ps1
```
Expected:
```
==> sign.ps1
    Target: D:\pechepro\dist\pechepro-setup.exe
    SKIP: target file not found (build first)
```

- [ ] **Step 3: Commit**

```powershell
git add deploy\windows\sign.ps1
git commit -m "build(plan-4): add sign.ps1 V0.1 stub (V0.2 signtool path documented)"
```

---

## Task 5 : Local end-to-end build smoke

**Files:** none new — exercises Tasks 1–4 against the already-merged Phase 1 code.

- [ ] **Step 1: Verify .venv has the build extra**

```powershell
.venv\Scripts\activate
pip show pyinstaller | Select-String "^Version"
```
Expected: `Version: 6.11.1`. If missing: `pip install -e ".[dev,build]"`.

- [ ] **Step 2: Run full build pipeline**

From repo root:
```powershell
pwsh deploy\windows\build.ps1
```
Expected (last lines):
```
==> [4/4] Size check (max 60 MB)
    pechepro-setup.exe: XX.XX MB
==> Build OK
    D:\pechepro\dist\pechepro-setup.exe (XX.XX MB)
```

- [ ] **Step 3: Verify size and signature placeholder**

```powershell
$setup = "dist\pechepro-setup.exe"
$size = (Get-Item $setup).Length / 1MB
"Size: {0:N2} MB" -f $size
pwsh deploy\windows\sign.ps1
```
Expected: size < 60 MB; sign.ps1 exits 0 with "code signing pending".

- [ ] **Step 4: Smoke launch the .exe (manual)**

Double-click `dist\pechepro.exe` (the inner exe, not the installer). Expected:
- PyWebView window opens within ~3 seconds (one-file mode is slower on first launch — that's the documented trade-off)
- Home screen renders with 15 species in dropdown
- Close window — process exits cleanly (verify with Task Manager)

If launch fails, capture logs:
```powershell
$env:PYINSTALLER_DEBUG = "1"
.\dist\pechepro.exe 2>&1 | Tee-Object -FilePath build-smoke.log
```

- [ ] **Step 5: Commit any spec adjustments needed (hidden imports, datas)**

If Step 4 surfaced missing imports, edit `deploy/windows/pechepro.spec` and rebuild. Commit the fix:
```powershell
git add deploy\windows\pechepro.spec
git commit -m "build(plan-4): fix hidden imports surfaced by smoke launch"
```

---

## Task 6 : Verify installer install/uninstall lifecycle

**Files:** none new — manual QA against `dist/pechepro-setup.exe`.

- [ ] **Step 1: Install the package** (on the dev machine — this is a sanity check; the full Windows 11 VM smoke is Task 11)

Double-click `dist\pechepro-setup.exe`. Expected:
- Installer launches without UAC prompt (PrivilegesRequired=lowest)
- License page shows the LICENSE file content
- "Create desktop icon" checkbox visible and checked by default
- Installs to `%LOCALAPPDATA%\Programs\pechepro\` (verify after install)
- "Launch Pechepro" checkbox at end shown

- [ ] **Step 2: Verify install artifacts**

```powershell
$installDir = "$env:LOCALAPPDATA\Programs\pechepro"
ls $installDir
```
Expected files present:
- `pechepro.exe`
- `LICENSE`
- `README.md`
- `CHANGELOG.md`
- `unins000.exe` (Inno Setup uninstaller)
- `unins000.dat`

```powershell
Test-Path "$env:USERPROFILE\Desktop\Pechepro.lnk"
Test-Path "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Pechepro\Pechepro.lnk"
```
Expected: both `True`.

- [ ] **Step 3: Verify Apps & Features registration**

```powershell
Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' |
    Where-Object DisplayName -Like 'Pechepro*' |
    Select DisplayName, DisplayVersion, Publisher, UninstallString
```
Expected: one row matching "Pechepro 0.1.0", publisher "Master / sxc3030-eng".

- [ ] **Step 4: Uninstall via Apps & Features**

Open Settings → Apps → Installed apps → Pechepro → Uninstall. Expected:
- Uninstaller runs without errors
- `%LOCALAPPDATA%\Programs\pechepro\` is gone
- Desktop + Start Menu shortcuts removed
- Registry entry removed
- `%LOCALAPPDATA%\pechepro\pechepro.db` is **preserved** (per [UninstallDelete] decision — documented in SMOKE_CHECKLIST #19)

- [ ] **Step 5: Document any deviations**

If anything in Steps 1–4 surprised you, append a note to `deploy/windows/installer.iss` (in a `; NOTE:` comment) or open a follow-up ticket. Commit:
```powershell
git add deploy\windows\installer.iss
git commit -m "build(plan-4): document install/uninstall lifecycle observations"
```

---

## Task 7 : Create LICENSE file

**Files:**
- Create: `D:\pechepro\LICENSE`

- [ ] **Step 1: Write `LICENSE`** (proprietary, all rights reserved)

```
PECHEPRO PROPRIETARY LICENSE
Version 0.1 — 2026-05-09

Copyright (c) 2026 Master / sxc3030-eng. All rights reserved.

PERMITTED USE
-------------
This software ("Pechepro") is licensed, not sold. By installing or using
Pechepro, you agree to the following terms:

1. Personal, non-commercial use of the software is permitted free of charge.
2. You may install Pechepro on any number of personal devices you own or
   control.
3. You may NOT redistribute, sublicense, sell, rent, lease, or otherwise
   transfer the software to third parties without prior written consent
   from the copyright holder.
4. You may NOT decompile, reverse engineer, disassemble, or attempt to
   derive the source code of the software, except to the extent that such
   activity is expressly permitted by applicable law notwithstanding this
   restriction.
5. You may NOT remove, alter, or obscure any copyright, trademark, or other
   proprietary notices contained in the software.

DATA AND PRIVACY
----------------
Pechepro stores user preferences and a cache of weather data locally on
your device under %LOCALAPPDATA%\pechepro\. No personal data is
transmitted to the publisher. The application contacts third-party APIs
(Open-Meteo, USGS Water Services, ECCC, GitHub raw) directly from your
device. See README.md for the full list.

THIRD-PARTY ASSETS
------------------
Pechepro embeds an Expedia Affiliate Banners widget (camref 1101l5IQud)
in accordance with the Expedia Group Creator program terms. Clicking the
widget routes traffic through Expedia's affiliate tracking; no Pechepro
user identifier is sent to Expedia.

DISCLAIMER OF WARRANTY
----------------------
PECHEPRO IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE, AND NONINFRINGEMENT.

LIMITATION OF LIABILITY
-----------------------
IN NO EVENT SHALL THE COPYRIGHT HOLDER BE LIABLE FOR ANY CLAIM, DAMAGES,
OR OTHER LIABILITY ARISING FROM, OUT OF, OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

GOVERNING LAW
-------------
This license is governed by the laws of the Province of Quebec, Canada.

CONTACT
-------
For licensing inquiries: https://github.com/sxc3030-eng/pechepro/issues
```

- [ ] **Step 2: Verify Inno Setup can read it**

The installer.iss already references `..\..\LICENSE` — re-run build.ps1 after creating this file to confirm the license page renders.

- [ ] **Step 3: Commit**

```powershell
git add LICENSE
git commit -m "docs(plan-4): add proprietary LICENSE for pechepro v0.1"
```

---

## Task 8 : Create CHANGELOG.md

**Files:**
- Create: `D:\pechepro\CHANGELOG.md`

- [ ] **Step 1: Write `CHANGELOG.md`**

```markdown
# Changelog

All notable changes to pechepro are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-05-09

First public release.

### Added
- Standalone Windows desktop app (PyWebView shell + local Flask).
- 15 North American species supported (FR + EN).
- 65+ regions across CA / US.
- 5 water types (lake, river, pond, reservoir, marsh).
- Solunar major/minor period calculation (local, no network).
- Sun + moon ephemeris via `astral` (local, no network).
- Open-Meteo integration (weather, barometric trend) with 1 h SQLite cache.
- USGS Water Services + ECCC water-temperature lookup.
- Recommender engine with fallback hierarchy (species + region + conditions).
- ~300+ curated tips with source URLs (In-Fisherman, Bassmaster, Sépaq,
  Quebec Pêche, INFOpêche, Pêches et Océans Canada).
- ~120 color/visibility entries (turbidity × light × color matrix).
- GitHub raw data sync at launch (24 h cache).
- Expedia Affiliate Banners widget (camref `1101l5IQud`,
  pubref `pechepro-tips`).
- Localization FR + EN via `gettext`.
- Inno Setup installer (no admin required, installs to
  `%LOCALAPPDATA%\Programs\pechepro\`).
- GitHub Actions release workflow on tag `v*`.

### Known limitations
- Installer is **unsigned** — first launch shows SmartScreen "Unknown
  publisher" warning. Click "More info" → "Run anyway" to proceed.
  Code-signing certificate planned for V0.2.
- One-file PyInstaller build: first launch unpacks to `%TEMP%`, takes
  ~3–5 s before window appears.
- Mexican (MX) regions not yet curated. Planned for V0.2.
- USGS only covers US waters; ECCC has limited Canadian station coverage.
  Manual water-temperature entry available as fallback.

### Security
- No user data leaves the device except direct calls to Open-Meteo, USGS,
  ECCC, GitHub raw, and the Expedia widget script (loaded by PyWebView).
- Local DB stored at `%LOCALAPPDATA%\pechepro\pechepro.db` — survives
  app updates and uninstalls.

[0.1.0]: https://github.com/sxc3030-eng/pechepro/releases/tag/v0.1.0
```

- [ ] **Step 2: Commit**

```powershell
git add CHANGELOG.md
git commit -m "docs(plan-4): add CHANGELOG.md with v0.1.0 release notes"
```

---

## Task 9 : Create GitHub Actions release workflow

**Files:**
- Create: `D:\pechepro\.github\workflows\release.yml`

- [ ] **Step 1: Write `.github/workflows/release.yml`**

```yaml
name: Release

# Runs only on annotated version tags (v0.1.0, v0.1.1, v1.0.0, …).
# Does NOT run on every commit — that's handled by .github/workflows/test.yml.
on:
  push:
    tags:
      - 'v*'

permissions:
  contents: write     # required by softprops/action-gh-release@v2 to create the release

jobs:
  build-windows:
    name: Build Windows installer
    runs-on: windows-latest
    timeout-minutes: 30

    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0    # full history so version tags are resolvable

      - name: Set up Python 3.13
        uses: actions/setup-python@v5
        with:
          python-version: '3.13'
          cache: 'pip'
          cache-dependency-path: pyproject.toml

      - name: Install Python deps (dev + build)
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev,build]"

      - name: Run tests with coverage
        run: pytest --cov=app --cov-report=xml --cov-report=term -m "not smoke"

      - name: Install Inno Setup 6 via Chocolatey
        run: choco install innosetup --version=6.4.3 -y --no-progress
        shell: pwsh

      - name: Build installer (build.ps1)
        run: pwsh deploy/windows/build.ps1
        shell: pwsh

      - name: Run sign.ps1 (V0.1 stub)
        run: pwsh deploy/windows/sign.ps1
        shell: pwsh

      - name: Verify installer size (< 60 MB)
        shell: pwsh
        run: |
          $setup = "dist/pechepro-setup.exe"
          if (-not (Test-Path $setup)) { throw "Installer not found: $setup" }
          $sizeMB = (Get-Item $setup).Length / 1MB
          Write-Host ("Installer size: {0:N2} MB" -f $sizeMB)
          if ($sizeMB -gt 60) { throw "Installer too large: $sizeMB MB > 60 MB cap" }

      - name: Upload coverage report (artifact)
        uses: actions/upload-artifact@v4
        with:
          name: coverage-${{ github.ref_name }}
          path: coverage.xml
          retention-days: 30

      - name: Upload installer (artifact, fallback if release step fails)
        uses: actions/upload-artifact@v4
        with:
          name: pechepro-setup-${{ github.ref_name }}
          path: dist/pechepro-setup.exe
          retention-days: 90

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          name: Pechepro ${{ github.ref_name }}
          tag_name: ${{ github.ref_name }}
          body: |
            Pechepro release ${{ github.ref_name }}.

            See [CHANGELOG.md](https://github.com/sxc3030-eng/pechepro/blob/main/CHANGELOG.md)
            for the full list of changes.

            ## Install
            1. Download `pechepro-setup.exe` below.
            2. Run it (no admin required).
            3. SmartScreen warning expected on V0.1 (unsigned). Click
               "More info" → "Run anyway".
            4. Launch from Start Menu or Desktop shortcut.

            See README.md for full install instructions and the
            20-scenario [smoke checklist](https://github.com/sxc3030-eng/pechepro/blob/main/deploy/windows/SMOKE_CHECKLIST.md).
          files: |
            dist/pechepro-setup.exe
          draft: false
          prerelease: ${{ contains(github.ref_name, '-rc') || contains(github.ref_name, '-beta') }}
          fail_on_unmatched_files: true
```

- [ ] **Step 2: Lint the YAML locally**

```powershell
python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"
```
Expected: no output, exit 0.

Optionally with `actionlint` if installed:
```powershell
actionlint .github\workflows\release.yml
```

- [ ] **Step 3: Verify the workflow does NOT trigger on pushes to main**

Inspect the `on:` block — only `push.tags: ['v*']`. No `branches:` key, no `pull_request:`. Documented separation from `test.yml` (which runs on every push to main and PRs).

- [ ] **Step 4: Commit**

```powershell
git add .github\workflows\release.yml
git commit -m "ci(plan-4): add release workflow on tag v* (windows-latest, choco innosetup)"
```

---

## Task 10 : Update README.md with install + smoke section

**Files:**
- Edit: `D:\pechepro\README.md`

- [ ] **Step 1: Read existing README**

```powershell
Get-Content README.md
```
Note the current section structure so the install block fits the existing tone.

- [ ] **Step 2: Append (or insert near top) an Install + Quickstart section**

Insert between the project description and the Development section:

```markdown
## Install (Windows 10 / 11)

1. Download the latest `pechepro-setup.exe` from the
   [Releases page](https://github.com/sxc3030-eng/pechepro/releases/latest).
2. Double-click the installer.
   - **First-launch SmartScreen warning** is expected on V0.1
     (the installer is not yet code-signed). Click **More info** → **Run anyway**.
   - No administrator privileges required — Pechepro installs to
     `%LOCALAPPDATA%\Programs\pechepro\`.
3. Accept the license, choose whether to add a Desktop icon, and click **Install**.
4. The installer creates two shortcuts:
   - `Start Menu → Pechepro`
   - `Desktop → Pechepro` (if you opted in)
5. Launch Pechepro. The first launch takes ~3–5 seconds (one-file
   PyInstaller bootstrap unpacks to `%TEMP%`); subsequent launches are
   under 2 seconds.
6. On the Home screen, pick a species, water type, and either accept
   the Windows Location prompt or pick a region manually. Tips and
   conditions appear within ~3 seconds.

### Uninstall

Settings → Apps → Installed apps → Pechepro → Uninstall.
Your local database (`%LOCALAPPDATA%\pechepro\pechepro.db`) is
preserved by default so reinstalling restores your preferences and
weather cache. To wipe everything, also delete the
`%LOCALAPPDATA%\pechepro\` folder manually.

### Data updates

Pechepro fetches `data/curated/*.csv` from this repository at every
launch (with a 24-hour cache). New tips committed to `main` reach
existing users automatically — no app reinstall required.

## Quality assurance

Manual QA on a clean Windows 11 22H2 VM follows the
[20-scenario smoke checklist](deploy/windows/SMOKE_CHECKLIST.md).
Every release tagged `v*` must pass all 20 scenarios before the
GitHub Release is published.

## Build from source

```powershell
git clone https://github.com/sxc3030-eng/pechepro.git
cd pechepro
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev,build]"
pwsh deploy\windows\build.ps1
```

Output: `dist\pechepro-setup.exe`. The PowerShell script chains
PyInstaller → Inno Setup 6 (must be installed; `choco install innosetup -y`)
and asserts the installer is < 60 MB.
```

- [ ] **Step 3: Commit**

```powershell
git add README.md
git commit -m "docs(plan-4): add Install + Build-from-source sections to README"
```

---

## Task 11 : Write SMOKE_CHECKLIST.md (20 scenarios)

**Files:**
- Create: `D:\pechepro\deploy\windows\SMOKE_CHECKLIST.md`

- [ ] **Step 1: Write `deploy/windows/SMOKE_CHECKLIST.md`**

```markdown
# Pechepro v0.1 — Smoke Checklist (20 scenarios)

> **Target environment:** clean Windows 11 22H2 VM (recommended:
> Hyper-V or VirtualBox snapshot). User account is a **standard user**
> (not Administrator). No prior Pechepro install.

> **Test artifact:** `dist/pechepro-setup.exe` produced by `build.ps1`
> or downloaded from a GitHub release.

> **Pass criteria:** all 20 scenarios green. Any RED blocks the release.
> Mark each as `[x]` once verified, with date + tester initials.

---

## Pre-test setup

1. Take a VM snapshot named `clean-win11-pre-pechepro`.
2. Copy `pechepro-setup.exe` into the VM (e.g., shared folder or download
   from the GitHub release page inside the VM).
3. Optionally: install uBlock Origin in Edge/Chrome to test scenario 11
   (Expedia widget blocked).

After all scenarios are run, **revert the VM** to the snapshot.

---

## Scenarios

### 1. Fresh install — Windows 11 22H2 — no admin

- **Action:** Right-click `pechepro-setup.exe` → Open. Do **not**
  "Run as administrator".
- **Expected:** Installer launches without UAC prompt. Wizard advances
  past the License page after agreement. Final page shows "Launch
  Pechepro" checkbox.
- **Verify:** `%LOCALAPPDATA%\Programs\pechepro\pechepro.exe` exists.
- **Status:** [ ]

### 2. Launch from Start Menu shortcut

- **Action:** Press Win, type "Pechepro", press Enter.
- **Expected:** PyWebView window opens within 5 s on first launch
  (one-file unpack), under 2 s on subsequent launches. Window
  size 1100×750.
- **Verify:** Task Manager → "pechepro.exe" running. No console window.
- **Status:** [ ]

### 3. Launch from Desktop shortcut

- **Action:** Close the app (X button). Double-click the
  Desktop "Pechepro" icon.
- **Expected:** Same as scenario 2. Subsequent launch < 2 s.
- **Verify:** No second `pechepro.exe` process if previous still running.
- **Status:** [ ]

### 4. First-run DB initialization

- **Action:** Launch the app for the first time. After Home screen
  appears, exit the app.
- **Expected:** `%LOCALAPPDATA%\pechepro\pechepro.db` created.
- **Verify:** `Test-Path "$env:LOCALAPPDATA\pechepro\pechepro.db"` → True.
  File size > 50 KB (schema + seed).
- **Status:** [ ]

### 5. Home screen renders correctly

- **Action:** Launch the app, observe the Home screen.
- **Expected:** Species dropdown shows **15** entries (Achigan à grande
  bouche … Barbue de rivière). Region dropdown lists **65+** entries
  grouped by country (CA / US). Water-type dropdown shows **5** options
  (lac, rivière, étang, réservoir, marais).
- **Verify:** Each dropdown populated; no "loading…" stuck state.
- **Status:** [ ]

### 6. GPS auto-detection — accept

- **Action:** On Home, click "Détecter ma position". A Windows
  Location consent dialog appears. Click **Yes**.
- **Expected:** Lat/Lon fields populate within 5 s. Region dropdown
  auto-selects the matching region (e.g., Québec for Lévis).
- **Verify:** Lat/Lon are non-zero, displayed with 4 decimals.
- **Status:** [ ]

### 7. GPS denied — manual region selection

- **Action:** Settings → Privacy & Security → Location → toggle
  Location services **OFF**. Restart Pechepro. Click "Détecter ma
  position".
- **Expected:** App shows a polite "Localisation non disponible —
  veuillez choisir manuellement" message. Manual region dropdown is
  enabled and selecting "Québec" populates a default lat/lon for the
  region centroid.
- **Verify:** No crash. App proceeds normally with manually chosen
  region. Re-enable Location after the test.
- **Status:** [ ]

### 8. End-to-end recommendation: Walleye / Lévis QC / lac / midday

- **Action:** Pick **Doré jaune (Walleye)**, region **Québec**, water
  **lac**, clock = local midday. Click "Voir les conditions".
- **Expected:** Conditions screen renders in **< 3 s**. Shows: weather
  block (temp + wind + baro trend), sun-rise/set times, current moon
  phase, solunar major + minor periods, and at least 5 ranked tips.
- **Verify:** Page contains the words "Doré" or "Walleye".
- **Status:** [ ]

### 9. Tips screen — sources cited

- **Action:** Click "Astuces" tab from the Conditions screen.
- **Expected:** ≥ 5 tip cards visible, ranked by confidence.
  Each tip displays the **source URL** as a clickable link
  (Sépaq / Quebec Pêche / In-Fisherman / Bassmaster / etc.).
- **Verify:** At least 3 distinct source domains shown across the
  visible tips. Click one link → opens in default browser.
- **Status:** [ ]

### 10. Expedia widget loads (online)

- **Action:** With network connectivity, observe the footer of the
  Tips screen (allow ~3 s for async load).
- **Expected:** Expedia leaderboard banner (728×90) renders with
  destination imagery and "Find your hotel" CTA.
- **Verify:** Browser DevTools (if PyWebView dev mode enabled) shows
  request to `creator.expediagroup.com` with `data-camref="1101l5IQud"`
  and `data-pubref="pechepro-tips"`.
- **Status:** [ ]

### 11. Expedia widget gracefully absent (uBlock or offline)

- **Action:** Either (a) install uBlock Origin and enable a banner
  blocklist, or (b) disconnect network. Reload the Tips screen.
- **Expected:** Tips render normally. The banner slot is empty — **no**
  error message, **no** placeholder, **no** layout collapse beyond
  the banner's reserved 90 px height.
- **Verify:** Page rendering proceeds; tips remain visible and
  legible.
- **Status:** [ ]

### 12. Offline mode — local tips still served

- **Action:** Close Pechepro. Disconnect WiFi / Ethernet. Relaunch
  Pechepro. Pick Doré + Québec + lac → Conditions.
- **Expected:** Sun/moon times displayed (local calc). Solunar
  windows displayed. Tips list rendered from local SQLite.
  Weather block shows "Météo indisponible — astuces basées sur
  les conditions de référence" banner.
- **Verify:** No crash. App reaches Tips screen within 3 s. At
  least 5 tips visible.
- **Status:** [ ]

### 13. "Météo indisponible" banner when offline + cache expired

- **Action:** While offline (from scenario 12), edit
  `%LOCALAPPDATA%\pechepro\pechepro.db` `weather_cache` table to
  set `expires_at` to a date in 2020 (e.g., via DB Browser for
  SQLite). Reload Conditions.
- **Expected:** Yellow banner "Météo indisponible — astuces basées
  sur les conditions de référence" replaces the weather block.
  Tips remain available.
- **Verify:** Banner text matches exactly. No silent failures.
- **Status:** [ ]

### 14. Language switch FR ↔ EN

- **Action:** Toggle the language switcher in the header from FR to EN.
- **Expected:** All visible UI strings switch instantly (or after a
  page reload — both behaviors acceptable). Tips switch from
  `tip_text_fr` to `tip_text_en`. Species names switch
  (Doré → Walleye, etc.).
- **Verify:** No mixed-language strings on the same screen.
  Toggling back to FR restores French text.
- **Status:** [ ]

### 15. Sun + moon times correct for Lévis QC today

- **Action:** Note today's sunrise / sunset / moonrise / moonset
  shown in the Conditions screen for Lévis, QC (lat 46.81, lon -71.21).
- **Expected:** Match (within ±2 minutes) the values published by
  [suncalc.org](https://www.suncalc.org/) for the same date and
  coordinates.
- **Verify:** All four times within tolerance. Solar noon also
  consistent.
- **Status:** [ ]

### 16. Solunar major + minor periods visualized

- **Action:** On Conditions, locate the "Périodes solunaires" section.
- **Expected:** Two **major** periods (~2 h each) and two **minor**
  periods (~1 h each) displayed for the day, with times in 24h format.
  Quality score (1–10) shown for each.
- **Verify:** No overlap in times. Times fit within 00:00–23:59.
- **Status:** [ ]

### 17. Baro trend rising/falling indicator

- **Action:** Open `pechepro.db`, edit `weather_cache.payload_json`
  for your current cache_key to fake a 6-hour pressure drop
  (e.g., 1020 → 1010 hPa). Reload Conditions.
- **Expected:** Baro trend indicator switches to "↘ falling".
  Activity-score banner for the selected species reflects the
  baro_rules table (e.g., walleye + falling = high activity).
- **Verify:** Indicator and score change as expected. Repeat with
  a rising trend (1010 → 1020) to confirm both directions.
- **Status:** [ ]

### 18. Curated data sync from GitHub raw

- **Action:** On the test VM, ensure `data_sync_meta.last_synced_at`
  for `tips` is older than 24 h (or zero). On a separate dev
  machine, edit `data/curated/tips.csv` on `main`, push, and verify
  the file is reachable at
  `https://raw.githubusercontent.com/sxc3030-eng/pechepro/main/data/curated/tips.csv`.
  Then close + relaunch Pechepro on the VM (with network).
- **Expected:** At launch, the new tip row appears in the SQLite
  `tips` table after sync. Tips screen shows the new tip in the
  ranking when conditions match.
- **Verify:** SQL query on `pechepro.db` finds the new tip's
  `id` / `tip_text_fr`. Revert the test edit on `main` after
  the test.
- **Status:** [ ]

### 19. Uninstall — app removed, user data preserved

- **Action:** Settings → Apps → Installed apps → Pechepro →
  Uninstall.
- **Expected:** `%LOCALAPPDATA%\Programs\pechepro\` removed. Desktop
  + Start Menu shortcuts removed. Apps & Features registration
  removed. **`%LOCALAPPDATA%\pechepro\pechepro.db` is preserved**
  (per design — see CHANGELOG; allows reinstall to restore prefs).
- **Verify:** All four conditions met. To wipe user data, the user
  must delete `%LOCALAPPDATA%\pechepro\` manually — documented in
  README.
- **Status:** [ ]

### 20. Reinstall after uninstall — clean state

- **Action:** Run `pechepro-setup.exe` again. Complete the wizard.
  Launch the app.
- **Expected:** Install succeeds. App launches. The preserved
  `pechepro.db` is detected and reused — last species + last region
  + language pref restored from `user_prefs`.
- **Verify:** No "first-run" wizard re-shown. No stale schema
  errors (verify by looking at recent logs in `%TEMP%\pechepro.log`
  if present).
- **Status:** [ ]

---

## Antivirus & SmartScreen sanity

Before sign-off, also verify the following on a Windows 11 VM with
Defender enabled (real-time protection ON):

- [ ] Defender does **not** flag `pechepro-setup.exe` as a threat at
      download or scan time.
- [ ] SmartScreen warning text is the standard "Windows protected your
      PC — Unknown publisher" — clicking "More info" → "Run anyway"
      proceeds the install. (V0.2 will eliminate this with a code-signing
      certificate.)
- [ ] `pechepro.exe` (the inner exe) does **not** trigger a Defender
      block when launched.
- [ ] Optionally: scan `pechepro-setup.exe` on
      [VirusTotal](https://www.virustotal.com/) — record the detection
      ratio in the release PR. Goal: < 5/70 engines flagging (acceptable
      noise from heuristics on PyInstaller binaries; see spec §11).

---

## Sign-off

| Field | Value |
|---|---|
| Build version | `_____________` |
| Tester | `_____________` |
| VM image | `_____________` |
| Date | `_____________` |
| Result | [ ] PASS / [ ] FAIL |
| Notes | `_____________` |

If FAIL: do **not** publish the GitHub release. Open an issue per
failed scenario and fix before re-tagging.
```

- [ ] **Step 2: Verify exactly 20 numbered scenarios**

```powershell
(Select-String -Path 'deploy\windows\SMOKE_CHECKLIST.md' -Pattern '^### \d+\.').Count
```
Expected: `20`.

- [ ] **Step 3: Commit**

```powershell
git add deploy\windows\SMOKE_CHECKLIST.md
git commit -m "docs(plan-4): add SMOKE_CHECKLIST.md with 20 QA scenarios"
```

---

## Task 12 : Test the release workflow with a release-candidate tag

**Files:** none new — exercises the workflow end-to-end against a `-rc1` tag.

- [ ] **Step 1: Push the branch + open PR (if not done)**

```powershell
git push -u origin plan/build-deploy
gh pr create --title "plan-4: build & deploy implementation" --body "Implements plan-4 build & deploy. See docs/superpowers/plans/2026-05-09-pechepro-plan-4-build-deploy.md"
```

- [ ] **Step 2: Merge to main**

After review approval:
```powershell
git checkout main
git pull --ff-only
git merge --no-ff plan/build-deploy -m "Merge plan-4: build & deploy"
git push origin main
```

- [ ] **Step 3: Tag a release candidate to test the workflow**

```powershell
git tag -a v0.1.0-rc1 -m "Pechepro v0.1.0-rc1 — release-candidate, exercises release.yml"
git push origin v0.1.0-rc1
```

- [ ] **Step 4: Watch the workflow**

```powershell
gh run watch --exit-status
```
Expected: green run within 15–25 minutes. Job "Build Windows installer" green. Coverage artifact + installer artifact uploaded.

- [ ] **Step 5: Verify the prerelease appears**

```powershell
gh release view v0.1.0-rc1
```
Expected: marked as **prerelease** (because the tag contains `-rc`). `pechepro-setup.exe` listed as an asset.

- [ ] **Step 6: Download + smoke the CI-built artifact**

```powershell
gh release download v0.1.0-rc1 -p pechepro-setup.exe -O dist\pechepro-setup-ci.exe
$ciSize = (Get-Item dist\pechepro-setup-ci.exe).Length / 1MB
"CI artifact size: {0:N2} MB" -f $ciSize
```
Expected: size < 60 MB and within ±5% of the local build size from Task 5.

- [ ] **Step 7: If RC artifact passes, no commit needed (artifact lives on GitHub).**

---

## Task 13 : Final QA — run the 20-scenario smoke on a clean VM

**Files:** none — fills out `SMOKE_CHECKLIST.md` against the v0.1.0-rc1 artifact.

- [ ] **Step 1: Provision a clean Windows 11 22H2 VM**

Hyper-V or VirtualBox. Take a snapshot named `clean-win11-pre-pechepro`.

- [ ] **Step 2: Transfer the rc1 installer**

Either (a) `gh release download v0.1.0-rc1` from inside the VM, or (b) shared folder copy.

- [ ] **Step 3: Run all 20 scenarios**

Walk through `deploy/windows/SMOKE_CHECKLIST.md`. Mark each `[x]` with date + initials.

- [ ] **Step 4: Record results**

If all 20 pass, commit a copy of the completed checklist to
`deploy/windows/SMOKE_CHECKLIST_v0.1.0-rc1.md` (preserve the blank
template at `SMOKE_CHECKLIST.md` for future releases):

```powershell
Copy-Item deploy\windows\SMOKE_CHECKLIST.md deploy\windows\SMOKE_CHECKLIST_v0.1.0-rc1.md
# Edit the copy with your results, then:
git add deploy\windows\SMOKE_CHECKLIST_v0.1.0-rc1.md
git commit -m "docs(plan-4): record smoke checklist results for v0.1.0-rc1 (20/20 PASS)"
```

- [ ] **Step 5: If any scenario FAILED, do NOT proceed to Task 14.**

Open a GitHub issue per failure, fix in a follow-up PR, retag rc2, restart from Task 12 step 3.

---

## Task 14 : Tag v0.1.0 and publish the GitHub Release

**Files:** none — final tag + release verification.

- [ ] **Step 1: Confirm `main` is at the rc1 commit**

```powershell
git log --oneline -3
git tag --list 'v0.1.0*'
```
Expected: most recent commit is the rc1 build. Tags include `v0.1.0-rc1`.

- [ ] **Step 2: Create the v0.1.0 tag**

```powershell
git tag -a v0.1.0 -m "Pechepro v0.1.0 — first public release. See CHANGELOG.md."
git push origin v0.1.0
```

- [ ] **Step 3: Watch the workflow**

```powershell
gh run watch --exit-status
```
Expected: green within 15–25 min.

- [ ] **Step 4: Verify the GitHub Release page**

```powershell
gh release view v0.1.0 --web
```
Expected:
- Title: `Pechepro v0.1.0`
- Marked as a **full release** (not prerelease — tag has no `-rc` / `-beta` suffix)
- Asset `pechepro-setup.exe` attached
- Body links to CHANGELOG.md and SMOKE_CHECKLIST.md

- [ ] **Step 5: Verify the asset is downloadable from a logged-out browser**

Open the release page in an incognito window. Click `pechepro-setup.exe` — download starts. Verify size matches.

- [ ] **Step 6: No commit needed.** v0.1.0 is shipped.

---

## Task 15 : Post-release housekeeping

**Files:** none — wraps up.

- [ ] **Step 1: Verify `dist/` is in `.gitignore`**

```powershell
Get-Content .gitignore | Select-String -Pattern '^dist'
Get-Content .gitignore | Select-String -Pattern '^build'
```
Expected: both `dist/` and `build/` ignored. If not, add them and commit:

```powershell
Add-Content .gitignore "`ndist/`nbuild/`n"
git add .gitignore
git commit -m "chore(plan-4): ignore dist/ and build/ artifacts"
```

- [ ] **Step 2: Confirm worktree is clean**

```powershell
git status
git worktree list
```
Expected: working tree clean. `plan-4-build-deploy` worktree present (will be removed by Master after final merge).

- [ ] **Step 3: Push final state**

```powershell
git push origin main
git push origin v0.1.0
```

- [ ] **Step 4: Update the master plan checkbox**

In `docs/superpowers/plans/2026-05-09-pechepro-master-plan.md`, mark Phase 2 done items:

```diff
**Phase 2** (plan 4) — done quand :
- - [ ] `dist\pechepro-setup.exe` build localement, taille <60 MB
- - [ ] GitHub Actions workflow green sur un push de tag `v0.1.0-rc1`
- - [ ] Smoke checklist 20 scénarios tous verts sur Windows clean
- - [ ] Tag `v0.1.0` créé, GitHub release publiée avec asset `pechepro-setup.exe`
+ - [x] `dist\pechepro-setup.exe` build localement, taille <60 MB
+ - [x] GitHub Actions workflow green sur un push de tag `v0.1.0-rc1`
+ - [x] Smoke checklist 20 scénarios tous verts sur Windows clean
+ - [x] Tag `v0.1.0` créé, GitHub release publiée avec asset `pechepro-setup.exe`
```

```powershell
git add docs\superpowers\plans\2026-05-09-pechepro-master-plan.md
git commit -m "docs(plan-4): mark Phase 2 complete in master plan"
git push
```

- [ ] **Step 5: Open a v0.2.0 tracking issue**

```powershell
gh issue create --title "v0.2.0 planning — code-signing cert + Mexican regions + Microsoft Store" --body "Per CHANGELOG.md known limitations and spec §11. Open after V0.1 user feedback collected."
```

---

## Self-review checklist

- [ ] **Spec coverage** — §3.6 Build & distribution (Tasks 1–4, 9), §11 Risks (Tasks 4 sign.ps1 + Task 11 SmartScreen / antivirus block), §13 Done criteria (Tasks 5 size cap, 11 smoke 20 scenarios, 14 GitHub release) all addressed.
- [ ] **`.exe` size constraint** — Task 5 step 3 + Task 9 size-check step + build.ps1 `MaxSizeMB=60` triple-enforces the < 60 MB cap.
- [ ] **Smoke checklist completeness** — exactly 20 scenarios, each with Action + Expected + Verify + Status box. Task 11 step 2 grep verifies the count.
- [ ] **Workflow runs on every tag, not on every commit** — Task 9 `on.push.tags: ['v*']` only. No `branches:` key. Test workflow (`test.yml`) handles every-commit testing per phase 0.
- [ ] **Local build (build.ps1) reproduces what CI does** — Task 9 release.yml calls `pwsh deploy/windows/build.ps1` directly; same script produces the same artifact whether run locally (Task 5) or in CI (Task 12).
- [ ] **No placeholders** — every code block is full and runnable: PyInstaller spec, Inno Setup script, GitHub Actions YAML, SMOKE_CHECKLIST scenarios, LICENSE, CHANGELOG, README, sign.ps1, build.ps1.
- [ ] **Exact versions pinned** — PyInstaller 6.11.1, Inno Setup 6.4.3 (via choco), softprops/action-gh-release@v2, actions/checkout@v4, actions/setup-python@v5, actions/upload-artifact@v4, Python 3.13.
- [ ] **Exact repo-relative paths** — `deploy/windows/pechepro.spec`, `deploy/windows/build.ps1`, `deploy/windows/installer.iss`, `deploy/windows/sign.ps1`, `deploy/windows/SMOKE_CHECKLIST.md`, `.github/workflows/release.yml`, `CHANGELOG.md`, `LICENSE`, `README.md`.
- [ ] **CI workflow runs on a clean GitHub Actions runner** — Task 9 installs Inno Setup via Chocolatey (no manual VM provisioning needed) and uses cached pip for speed.
