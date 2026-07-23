# -*- mode: python ; coding: utf-8 -*-

import os
import sys

from tubby import __version__


APP_ICON = 'public/logo/tubby_logo.png'
MACOS_ENTITLEMENTS = 'packaging/macos/entitlements.plist'
codesign_identity = os.environ.get('TUBBY_CODESIGN_IDENTITY') or None

a = Analysis(
    ['tubby/gui.py'],
    pathex=[],
    binaries=[],
    datas=[(APP_ICON, 'public/logo')],
    hiddenimports=[
        'yt_dlp',
        'faster_whisper',
        'ctranslate2',
        'av',
        'reportlab.pdfbase._fontdata',
        'uharfbuzz',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['kivy', 'moviepy', 'pytube'],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

if sys.platform == 'darwin':
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='Tubby',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=codesign_identity,
        entitlements_file=MACOS_ENTITLEMENTS,
    )
    collected = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        name='Tubby',
    )
    app = BUNDLE(
        collected,
        name='Tubby.app',
        icon=APP_ICON,
        bundle_identifier='com.kelivnjudha.tubby',
        info_plist={
            'CFBundleDisplayName': 'Tubby',
            'CFBundleName': 'Tubby',
            'CFBundleShortVersionString': __version__,
            'CFBundleVersion': __version__,
            'LSMinimumSystemVersion': '14.0',
            'NSHighResolutionCapable': True,
        },
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name='Tubby',
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
        icon=APP_ICON,
    )
