from pathlib import Path

from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.hooks import collect_submodules


project = Path(SPECPATH)
datas = [(str(project / "alembic.ini"), ".")]
migration_tree = Tree(
    str(project / "migrations"),
    prefix="migrations",
    excludes=["__pycache__", "*.pyc"],
)
asset_tree = Tree(
    str(project / "src" / "emss" / "assets"),
    prefix="emss/assets",
    excludes=["__pycache__", "*.pyc"],
)
template_tree = Tree(
    str(project / "templates"),
    prefix="templates",
    excludes=[
        "__pycache__",
        "*.pyc",
        "ddi_import_template.xlsx.inspect.ndjson",
    ],
)
seed_tree = Tree(
    str(project / "seed"),
    prefix="seed",
    excludes=["__pycache__", "*.pyc"],
)
hiddenimports = collect_submodules(
    "alembic", filter=lambda name: not name.startswith("alembic.testing")
) + collect_submodules("sqlalchemy.dialects.sqlite") + ["logging.config"]

a = Analysis(
    [str(project / "src" / "emss" / "__main__.py")],
    pathex=[str(project / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "unittest"],
    noarchive=False,
    optimize=1,
)
# Qt6Core requires Windows ICU exports. A foreign ICU on the build PATH
# (e.g. Poppler ICU78) has version-suffixed exports and breaks QtCore import.
a.binaries = [
    entry for entry in a.binaries
    if not (Path(entry[0]).name.lower() == "icuuc.dll"
            or (Path(entry[0]).name.lower().startswith("icudt")
                and Path(entry[0]).suffix.lower() == ".dll"))
]
a.datas += migration_tree + asset_tree + template_tree + seed_tree
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="E-MAS Farmasi",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(project / "src" / "emss" / "assets" / "emss.ico"),
    contents_directory=".",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="E-MAS Farmasi",
)
# Compatibility entry point for existing shortcuts and scheduled startup commands.
# It is the exact new binary, not an old runtime left alongside the upgrade.
import shutil
shutil.copyfile(Path(DISTPATH) / 'E-MAS Farmasi' / 'E-MAS Farmasi.exe',
                Path(DISTPATH) / 'E-MAS Farmasi' / 'e-MSS Farmasi RS.exe')
