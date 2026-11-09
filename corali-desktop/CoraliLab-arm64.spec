from pathlib import Path
root=Path(SPECPATH)

import subprocess

engine = root / "engine" / "cedro.exe"
help_text = subprocess.check_output([str(engine), "--help"], stderr=subprocess.STDOUT, timeout=10)
if b"Coral" not in help_text or b"convert, slices, trascrivi" not in help_text:
    raise ValueError("Prepara la variante CLI locale di Cedro prima del confezionamento.")

datas=[(str(root/'assets'),'assets'),(str(root/'engine'),'engine')]
datas.append((str(root/'ai-manifest.json'),'.'))
a=Analysis([str(root/'app.py')],pathex=[str(root)],binaries=[],datas=datas,
           hiddenimports=[],
           excludes=['tkinter','webview','pythonnet','clr_loader','imageio_ffmpeg','onnxruntime','numpy','networkx','pymupdf4llm','pymupdf_layout'],
           noarchive=False,optimize=0)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='CoraliBackend',debug=False,strip=False,upx=False,console=False,icon=str(root/'corali.ico'))
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='CoraliLab')
