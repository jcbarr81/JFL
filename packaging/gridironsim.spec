# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_all

block_cipher = None

def _play_datas(root: Path) -> list[tuple[str, str]]:
    plays_root = root / "data" / "plays"
    datas: list[tuple[str, str]] = []
    for path in plays_root.rglob("*"):
        if path.is_file():
            relative = path.relative_to(plays_root)
            target_dir = Path("assets/data/plays") / relative.parent
            datas.append((str(path), str(target_dir)))
    return datas

spec_dir = Path(SPECPATH)
project_root = spec_dir.parent

play_datas = _play_datas(project_root)

pyqt6_datas, pyqt6_binaries, pyqt6_hiddenimports = collect_all("PyQt6")
pydantic_datas, pydantic_binaries, pydantic_hiddenimports = collect_all("pydantic")
pydantic_core_datas, pydantic_core_binaries, pydantic_core_hiddenimports = collect_all("pydantic_core")

analysis_datas = [
    (str(project_root / "gridiron.db"), "assets"),
    *play_datas,
    *pyqt6_datas,
    *pydantic_datas,
    *pydantic_core_datas,
]

all_binaries = list(pyqt6_binaries) + list(pydantic_binaries) + list(pydantic_core_binaries)

hidden_imports = [
    "sim.schedule",
    "sim.ruleset",
    "sim.engine",
    "sim.statbook",
    "domain.db",
    "domain.models",
    *pyqt6_hiddenimports,
    *pydantic_hiddenimports,
    *pydantic_core_hiddenimports,
]


a = Analysis(
    [str(project_root / "ui" / "windows_launcher.py")],
    pathex=[str(project_root)],
    binaries=all_binaries,
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
