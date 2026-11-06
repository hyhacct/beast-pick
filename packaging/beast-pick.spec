# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import runpy
from PyInstaller.utils.win32.versioninfo import FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo

root = Path(SPECPATH).parent
version = runpy.run_path(str(root / 'beast_pick' / '__init__.py'))['__version__']
version_tuple = (*map(int, version.split('.')), 0)
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=version_tuple, prodvers=version_tuple,
                     mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
    kids=[StringFileInfo([StringTable('040904B0', [
        StringStruct('CompanyName', 'hyhacct'),
        StringStruct('FileDescription', 'BP · 困兽自动搜刮'),
        StringStruct('FileVersion', version),
        StringStruct('InternalName', 'BP'),
        StringStruct('LegalCopyright', 'Copyright (c) 2026 hyhacct'),
        StringStruct('OriginalFilename', 'BP.exe'),
        StringStruct('ProductName', 'Beast Pick'),
        StringStruct('ProductVersion', version),
    ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])],
)
a = Analysis(
    [str(root / 'run_tool.py')], pathex=[str(root)], binaries=[],
    datas=[(str(root / 'beast_pick' / 'agent.js'), 'beast_pick'),
           (str(root / 'beast_pick' / 'apply_update.ps1'), 'beast_pick'),
           (str(root / 'beast_pick' / 'filters.js'), 'beast_pick'),
           (str(root / 'beast_pick' / 'data'), 'beast_pick/data'),
           (str(root / 'beast_pick' / 'assets'), 'beast_pick/assets'),
           (str(root / 'beast_pick' / 'profiles'), 'beast_pick/profiles')],
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=[], noarchive=False, optimize=0,
)

# Qt 6.12 uses the unversioned Windows ICU API. A developer PATH can contain
# Poppler's incompatible ICU 78 (ucnv_open_78 instead of ucnv_open). Keep OS ICU
# out of the bundle so Windows resolves its own system implementation.
def is_icu(entry):
    name = Path(entry[0]).name.lower()
    return name.endswith('.dll') and name.startswith(('icuuc', 'icuin', 'icudt'))

removed = [entry[0] for entry in a.binaries if is_icu(entry)]
a.binaries = [entry for entry in a.binaries if not is_icu(entry)]
if removed:
    print('Excluded incompatible bundled ICU:', removed)

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='BP', version=version_info,
          icon=str(root / 'beast_pick' / 'assets' / 'beast-pick.ico'),
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          # Keep the one-file extraction outside the shared system TEMP tree.
          # Some antivirus / cleanup tools race PyInstaller while it loads
          # python312.dll from %TEMP%\_MEI..., which makes a self-update look
          # like a failed application start. LocalAppData is per-user and
          # remains writable for the same installs that can self-update.
          runtime_tmpdir=r'%LOCALAPPDATA%\BP\runtime', console=False,
          disable_windowed_traceback=False)
