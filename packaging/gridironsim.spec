# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

spec_dir = Path(SPECPATH)
project_root = spec_dir.parent
plays_src = project_root / "data" / "plays"
play_datas = []
for path in plays_src.rglob("*"):
    if path.is_file():
        relative = path.relative_to(project_root)
        target = Path("assets") / relative
        play_datas.append((str(path), str(target)))

pyqt6_datas = collect_data_files("PyQt6")
pyqt6_hiddenimports = collect_submodules("PyQt6")

analysis_datas = [
    (str(project_root / "gridiron.db"), "assets/gridiron.db"),
    *play_datas,
    *pyqt6_datas,
]

hidden_imports = [
    "sim.schedule",
    "sim.ruleset",
    "sim.engine",
    "sim.statbook",
    "domain.db",
    "domain.models",
    *pyqt6_hiddenimports,
]


a = Analysis(
    [str(project_root / "ui" / "windows_launcher.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=analysis_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GridironSim",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="GridironSim",
)
