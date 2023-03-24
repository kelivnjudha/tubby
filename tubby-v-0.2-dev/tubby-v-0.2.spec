# tubby-v-0.2.spec

block_cipher = None

a = Analysis(['tubby-v-0.2.py'],
             pathex=['D:\Python\tubby-version-0.2'],
             binaries=[],
             datas=[],
             hookspath=['hooks'],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)

# Add the theme files and the assets folder to the list of data files
import os
import customtkinter

customtkinter_path = os.path.dirname(customtkinter.__file__)
theme_files_path = os.path.join(customtkinter_path, 'assets', 'themes')

for root, _, files in os.walk(theme_files_path):
    for file in files:
        if file.endswith('.json'):
            file_path = os.path.join(root, file)
            # Update the target path to match the modified theme_manager.py
            a.datas.append((file_path, os.path.join('customtkinter', 'assets', 'themes', file), 'DATA'))

pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
          name='tubby',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=True,
          icon=None)
