from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
root=Path(SPECPATH)
datas=[(str(root/'assets'),'assets'),(str(root/'engine-x64'),'engine'),(str(root/'media-manifest.json'),'.'),(str(root/'ai-manifest.json'),'.')]+collect_data_files('yt_dlp_ejs')
a=Analysis([str(root/'app.py')],pathex=[str(root)],binaries=[],datas=datas,hiddenimports=collect_submodules('yt_dlp'),excludes=['tkinter','webview','pythonnet','clr_loader','imageio_ffmpeg','onnxruntime','numpy','networkx','pymupdf4llm','pymupdf_layout'],noarchive=False,optimize=0)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='CoraliBackend',debug=False,strip=False,upx=False,console=False,icon=str(root/'corali.ico'))
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='CoraliLab')
