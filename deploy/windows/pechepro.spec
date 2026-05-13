# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for pechepro v0.1 — Windows one-file build.

Bundles:
  - app/db/schema.sql + app/db/migrations/*.sql
  - data/curated/*.csv (8 files: species, regions, water_types, lures,
    color_visibility, tips, solunar_rules, baro_rules)
  - app/templates/* (Jinja2)
  - app/static/* (CSS, JS, images)
  - app/locales/* (FR/EN JSON locale files)

Hidden imports declared explicitly because PyInstaller's static analysis
misses dynamic imports inside pywebview, astral, skyfield, and winsdk.
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

# Pull astral's bundled geo database (timezone + city lookups)
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

# Collect all submodules of these packages so dynamic imports resolve.
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
        # Strip large unused stdlib modules to shrink the .exe.
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
    upx=False,                  # UPX often triggers AV false-positives — disabled.
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,              # GUI app — no console window.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(REPO_ROOT / "app" / "static" / "img" / "logo.ico"),
    version=str(REPO_ROOT / "deploy" / "windows" / "version_info.txt"),
)
