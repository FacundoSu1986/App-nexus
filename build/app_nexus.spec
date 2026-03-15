# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for App-nexus.

Build a one-file Windows .exe:
    cd <repo-root>
    pyinstaller build/app_nexus.spec

The output executable is placed in the ``dist/`` folder.
"""

import os

block_cipher = None

repo_root = os.path.abspath(os.path.join(os.path.dirname(SPECFILE), '..'))

a = Analysis(
    [os.path.join(repo_root, "main.py")],
    pathex=[repo_root],
    binaries=[],
    datas=[],
    hiddenimports=[
        "src.gui.main_window",
        "src.gui.mod_detail_frame",
        "src.nexus.api",
        "src.mo2.reader",
        "src.database.manager",
        "src.analyzer.compatibility",
        "requests",
        "sv_ttk",
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
    name="AppNexus",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # No console window — pure GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
