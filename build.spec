# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Exhibition CMS
# Run on Windows: pyinstaller build.spec

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[str(Path('.').resolve())],
    binaries=[],
    datas=[],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'apscheduler.schedulers.background',
        'apscheduler.triggers.cron',
        'bcrypt',
        'serial',
        'serial.tools.list_ports',
        'wakeonlan',
        'pythonosc',
        'pythonosc.udp_client',
        'pythonosc.osc_message_builder',
        'paramiko',
        'pyartnet',
    ],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ExhibitionCMS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # False = 창 없이 GUI만
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # 'assets/icon.ico' 경로로 교체 가능
    version=None,
)
