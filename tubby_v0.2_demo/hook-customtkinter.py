from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files('customtkinter', include_py_files=True, subdir='assets')
