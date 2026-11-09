from pathlib import Path
root=Path(SPECPATH)
datas=[(str(root/'assets'),'assets'),(str(root/'engine'),'engine')]
datas.append((str(root/'ai-manifest.json'),'.'))
a=Analysis([str(root/'app.py')],pathex=[str(root)],binaries=[],datas=datas,
           hiddenimports=[],
           excludes=['tkinter','webview','pythonnet','clr_loader','imageio_ffmpeg','onnxruntime','numpy','networkx','pymupdf4llm','pymupdf_layout'],
           noarchive=False,optimize=0)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='CoraliBackend',debug=False,strip=False,upx=False,console=False,icon=str(root/'corali.ico'))
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='CoraliLab')
