# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = [
    ('apktool.jar', '.'),
    ('uber-apk-signer.jar', '.'),
    ('ad_patterns.json', '.'),
    ('icon.ico', '.'),
    ('icon.png', '.'),
    ('photo.jpg', '.'),
]
datas += collect_data_files('customtkinter')

# tkinterdnd2 拖拽支持（可选，导入失败时 GUI 自动降级）
try:
    datas += collect_data_files('tkinterdnd2')
    _dnd_hidden = ['tkinterdnd2']
except Exception:
    _dnd_hidden = []


a = Analysis(
    ['remove_ads_gui.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=_dnd_hidden + ['pattern_updater'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='remove_ads_gui',
    icon='icon.ico',
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
