import hashlib,json,tempfile,threading,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from local_ai import LocalAI
from media_runtime import ensure_ffmpeg

class MediaRuntimeTests(unittest.TestCase):
    def test_pinned_download_then_cached_offline_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);ai=LocalAI(root,Path(__file__).parent/'ai-manifest.json');manifest=root/'media.json';raw=b'test executable'
            info={'version':'test','member':'release/bin/ffmpeg.exe','exeSha256':hashlib.sha256(raw).hexdigest()};manifest.write_text(json.dumps(info))
            def download(_info,dest,_progress,_cancel):
                with zipfile.ZipFile(dest,'w') as z:z.writestr(info['member'],raw);z.writestr('../outside',b'ignore')
            with patch.object(ai,'download',side_effect=download) as call:
                first=ensure_ffmpeg(ai,manifest,lambda _:None,threading.Event());second=ensure_ffmpeg(ai,manifest,lambda _:None,threading.Event())
                self.assertEqual(first,second);self.assertEqual(first.read_bytes(),raw);self.assertEqual(call.call_count,1)
                self.assertFalse((root/'outside').exists());self.assertFalse(first.with_name('download.zip').exists())
            first.write_bytes(b'changed')
            with self.assertRaises(ValueError):ensure_ffmpeg(ai,manifest,lambda _:None,threading.Event())
    def test_invalid_payload_is_not_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);ai=LocalAI(root,Path(__file__).parent/'ai-manifest.json');manifest=root/'media.json'
            manifest.write_text(json.dumps({'version':'test','member':'ffmpeg.exe','exeSha256':'0'*64}))
            def download(_info,dest,_progress,_cancel):
                with zipfile.ZipFile(dest,'w') as z:z.writestr('ffmpeg.exe',b'bad')
            with patch.object(ai,'download',side_effect=download),self.assertRaises(ValueError):ensure_ffmpeg(ai,manifest,lambda _:None,threading.Event())
            self.assertFalse((root/'media-tools/ffmpeg-test/ffmpeg.exe').exists())
            self.assertFalse(list(root.rglob('*.part')))

if __name__=='__main__':unittest.main()
