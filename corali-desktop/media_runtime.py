"""Fetch the media helper from its publisher only when a web-video task needs it."""
import hashlib,json,shutil,zipfile
from pathlib import Path

def ensure_ffmpeg(ai,manifest_path,progress,cancelled):
    info=json.loads(Path(manifest_path).read_text(encoding='utf8'))
    folder=ai.root.parent/'media-tools'/('ffmpeg-'+info['version'])
    executable=folder/'ffmpeg.exe'
    if executable.is_file():
        ai.verify(executable,{'sha256':info['exeSha256']});return executable
    folder.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(folder).free<400*1024*1024:raise ValueError('Servono 400 MB liberi per preparare lo strumento video.')
    archive=folder/'download.zip';part=folder/'ffmpeg.exe.part'
    try:
        ai.download(info,archive,progress,cancelled)
        if cancelled.is_set():raise ValueError('Scaricamento annullato.')
        with zipfile.ZipFile(archive) as z:
            member=z.getinfo(info['member'])
            if member.file_size>200*1024*1024:raise ValueError('Componente video troppo grande.')
            with z.open(member) as source,part.open('wb') as output:shutil.copyfileobj(source,output,1024*1024)
        ai.verify(part,{'sha256':info['exeSha256']})
        part.replace(executable);return executable
    finally:
        part.unlink(missing_ok=True);archive.unlink(missing_ok=True)
