import hashlib
import json
import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app import Application, VERSION
from local_ai import LocalAI
from safe_web import PublicYoutubeDL, PublicRedirectHandler, public_connection, validate_url


class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = Application(self.root / 'data')

    def test_version_from_backend(self):
        self.assertEqual(self.app.dispatch({'cmd': 'init'})['version'], VERSION)

    def test_ai_uses_package_architecture_on_arm_host(self):
        from advanced import Advanced
        import app
        with patch('local_ai.platform.machine', return_value='ARM64'), patch.dict(os.environ, {'PROCESSOR_ARCHITEW6432': 'ARM64'}):
            self.app.engine_info['architecture'] = 'x64'
            ai = Advanced(self.app, app.ROOT).ai
            self.assertEqual(ai.arch, 'x64')
            self.assertTrue(ai.runtime.name.endswith('-x64'))
            self.app.engine_info['architecture'] = 'arm64'
            self.assertEqual(Advanced(self.app, app.ROOT).ai.arch, 'arm64')

    def test_dns_resolved_once_numeric_address_used(self):
        address = (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443))
        sock = Mock()
        with patch('safe_web.socket.getaddrinfo', return_value=[address]) as dns, patch('safe_web.socket.socket', return_value=sock):
            self.assertIs(public_connection(('public.example', 443), 5), sock)
        dns.assert_called_once()
        sock.connect.assert_called_once_with(('8.8.8.8', 443))

    def test_private_mixed_dns_ipv6_and_rebinding_blocked(self):
        for ip in ('127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', '::ffff:127.0.0.1', '224.0.0.1'):
            answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443)),
                       (socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443))]
            with self.subTest(ip=ip), patch('safe_web.socket.getaddrinfo', return_value=answers), patch('safe_web.socket.socket') as sock:
                with self.assertRaises(ValueError): public_connection(('public.example', 443))
                sock.assert_not_called()

    def test_redirect_private_host_blocked_by_transport(self):
        import urllib.request
        redirect = PublicRedirectHandler().redirect_request(urllib.request.Request('https://public.example'), None, 302, '', {}, 'http://127.0.0.1/private')
        with PublicYoutubeDL({'quiet': True, 'proxy': ''}) as ydl:
            with self.assertRaises(Exception): ydl.urlopen(redirect)
            self.assertEqual(set(ydl._request_director.handlers), {'Public'})

    def test_urls_with_credentials_local_schemes_rejected(self):
        for url in ('file:///secret', 'ftp://example.com/x', 'https://user:pass@example.com', 'http://[fe80::1%25eth0]/'):
            with self.subTest(url=url), self.assertRaises(ValueError): validate_url(url)

    def test_external_downloader_protocols_and_live_rejected(self):
        with PublicYoutubeDL({'quiet': True}) as ydl:
            for protocol in ('rtmp', 'mms', 'http_dash_segments_generator'):
                with self.assertRaises(ValueError): ydl.dl('out', {'url': 'https://example.com/a', 'protocol': protocol})
            with self.assertRaises(ValueError): ydl.dl('out', {'url': 'https://example.com/a', 'protocol': 'https', 'is_live': True})

    def test_web_results_exclude_internal_pending_marker(self):
        folder=self.app.folder();(folder/'.corali-pending').touch();(folder/'audio.mp3').write_bytes(b'audio')
        with patch('safe_web.PublicYoutubeDL'), patch('media_runtime.ensure_ffmpeg',return_value=Path('ffmpeg.exe')):
            result=self.app.web_download({'url':'https://example.com/audio'},folder)
        self.assertEqual([p.name for p in result],['audio.mp3'])

    def test_runtime_same_size_tamper_and_extra_dll_rejected(self):
        folder = self.root / 'runtime';folder.mkdir()
        server = folder / 'llama-server.exe';server.write_bytes(b'good')
        info = {'files': {'llama-server.exe': hashlib.sha256(b'good').hexdigest()}}
        ai = self.app.advanced.ai
        ai.verify_runtime(folder, info)
        stat = server.stat();server.write_bytes(b'evil');os.utime(server, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, 'non integro'): ai.verify_runtime(folder, info)
        server.write_bytes(b'good');(folder / 'untrusted.dll').write_bytes(b'x')
        with self.assertRaises(ValueError): ai.verify_runtime(folder, info)

    def test_gpu_start_failure_falls_back_cpu(self):
        ai = self.app.advanced.ai;ai.root.mkdir();ai.backend = 'vulkan'
        with patch.object(ai, '_start', side_effect=[RuntimeError('no gpu'), None]) as start:
            ai.start(threading.Event())
        self.assertEqual(start.call_count, 2)
        self.assertEqual(ai.backend, 'cpu')
        self.assertIn('processore', ai.status()['backendNote'])

    def test_tampered_gpu_does_not_silently_fallback(self):
        ai = self.app.advanced.ai;ai.backend = 'vulkan'
        with patch.object(ai, '_start', side_effect=ValueError('integrity')) as start:
            with self.assertRaises(ValueError): ai.start(threading.Event())
        self.assertEqual(start.call_count, 1)

    def test_cleanup_restore_originals_and_unselected_results_preserved(self):
        original = self.root / 'original.txt';original.write_bytes(b'original')
        f = self.app.import_bytes(original.name, original.read_bytes())
        result = self.app.folder() / 'result.txt';result.write_bytes(b'result')
        preview = self.app.dispatch({'cmd':'cleanupPreview','days':0})
        self.assertEqual(preview['count'], 1)
        moved = self.app.dispatch({'cmd':'cleanupApply','token':preview['token']})
        self.assertFalse((self.app.root / f['id']).exists())
        self.assertEqual(original.read_bytes(), b'original');self.assertTrue(result.exists())
        self.app.dispatch({'cmd':'cleanupRestore','batch':moved['batch']})
        self.assertEqual(self.app.resolve(f['id']).read_bytes(), b'original')

    def test_cleanup_changed_preview_busy_and_active_documents(self):
        f = self.app.import_bytes('file.csv', b'a,b\n1,2')
        preview = self.app.dispatch({'cmd':'cleanupPreview','days':0})
        self.app.resolve(f['id']).write_bytes(b'changed')
        with self.assertRaises(ValueError): self.app.dispatch({'cmd':'cleanupApply','token':preview['token']})
        self.app.new_office(self.app.resolve(f['id']))
        self.assertEqual(self.app.dispatch({'cmd':'cleanupPreview','days':0})['count'], 0)
        with self.app.busy:
            with self.assertRaises(ValueError): self.app.dispatch({'cmd':'cleanupPreview','days':0})

    def test_cleanup_pending_outputs_and_paths_not_selected(self):
        folder = self.app.folder();(folder/'.corali-pending').touch();(folder/'pending.txt').write_bytes(b'pending')
        self.assertEqual(self.app.dispatch({'cmd':'cleanupPreview','days':0,'includeResults':True})['count'], 0)
        with self.assertRaises(ValueError): self.app.cleanup.restore('../inputs')
        with self.assertRaises(ValueError): self.app.cleanup.checked({'id':'../original','bytes':0,'mtime':0}, self.app.root)

    def test_purge_requires_confirmation_and_only_removes_trash(self):
        f = self.app.import_bytes('file.txt', b'copy')
        plan = self.app.dispatch({'cmd':'cleanupPreview','days':0})
        moved = self.app.dispatch({'cmd':'cleanupApply','token':plan['token']})
        other = self.app.import_bytes('keep.txt', b'keep')
        plan = self.app.dispatch({'cmd':'cleanupPurgePreview'})
        with self.assertRaises(ValueError): self.app.dispatch({'cmd':'cleanupPurge','token':plan['token']})
        self.assertEqual(self.app.dispatch({'cmd':'cleanupPurge','token':plan['token'],'confirmation':'ELIMINA'})['deleted'], 1)
        self.assertTrue(self.app.resolve(other['id']).exists())
        self.assertFalse((self.app.root/'trash'/moved['batch']/f['id']).exists())

    def test_worker_tampering_same_size_is_repaired_from_bundle(self):
        self.app.prepare_native_engine()
        worker = self.app.engine_info['workers'][0]
        target = self.app.engine_store()/'Cedro/trascrizione'/worker['name']
        with target.open('r+b') as stream: stream.write(b'BAD!')
        self.app.prepare_native_engine()
        with target.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
        self.assertEqual(digest, worker['sha256'])


if __name__ == '__main__': unittest.main()
