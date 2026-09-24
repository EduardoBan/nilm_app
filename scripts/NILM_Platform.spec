# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the portable Windows NILM distribution."""
from pathlib import Path

ROOT = Path(SPEC).resolve().parents[1]
APP_NAME = "NILM_Energy_Platform"

# Keep data in the bundle for a self-contained build; build_windows.ps1 copies
# the same folders next to the executable so they remain user-writable.
datas = [
    (str(ROOT / "frontend"), "frontend"),
    (str(ROOT / "Data"), "Data"),
    (str(ROOT / "Informe_NILM_Inti.pdf"), "."),
    (str(ROOT / "backend" / "load_labels.json"), "backend"),
]

hiddenimports = [
    "scripts.generate_report",
    "hmmlearn.hmm",
    "sklearn.cluster._kmeans",
    "scipy.optimize._lsap",
]

analysis = Analysis(
    [str(ROOT / "start_server.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["nilmtk"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    name=APP_NAME,
)
