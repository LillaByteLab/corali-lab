"""Explicit, previewed cleanup of app copies. Originals are never candidates."""
import json
import hashlib
import os
import secrets
import time
from pathlib import Path


class WorkspaceCleanup:
    def __init__(self, app):
        self.app = app
        self.plans = {}
        self.purge_plans = {}

    @staticmethod
    def digest(path):
        with path.open('rb') as stream:
            return hashlib.file_digest(stream,'sha256').hexdigest()

    def candidates(self, days, results):
        cutoff = time.time() - days * 86400
        active = {str(v['path'].resolve()) for v in self.app.sessions.values() if 'path' in v}
        files = []
        for category in ('inputs', 'outputs') if results else ('inputs',):
            base = self.app.root / category
            if base.is_symlink() or base.is_junction():
                raise ValueError('Cartella collegata: pulizia non consentita.')
            for folder, dirs, names in os.walk(base, followlinks=False):
                directory = Path(folder)
                dirs[:] = [d for d in dirs if not (directory / d).is_symlink() and not (directory / d).is_junction()]
                if (directory / '.corali-pending').exists():
                    dirs[:] = []
                    continue
                for name in names:
                    path = directory / name
                    if path.is_symlink() or path.is_junction() or name.startswith('.') or str(path.resolve()) in active:
                        continue
                    stat = path.stat()
                    if stat.st_mtime > cutoff:
                        continue
                    files.append({'id': path.relative_to(self.app.root).as_posix(), 'bytes': stat.st_size, 'mtime': stat.st_mtime_ns, 'sha256': self.digest(path)})
        return files

    def preview(self, p):
        days = p.get('days', 30)
        if type(days) is not int or days not in (0, 7, 30, 90):
            raise ValueError('Scegli un periodo valido.')
        files = self.candidates(days, p.get('includeResults') is True)
        token = secrets.token_urlsafe(24)
        self.plans = {token: {'files': files, 'expires': time.monotonic() + 300}}
        return {'token': token, 'count': len(files), 'bytes': sum(f['bytes'] for f in files),
                'names': [f['id'] for f in files[:20]], 'originalsPreserved': True}

    def checked(self, entry, base):
        path = base / entry['id']
        if Path(entry['id']).is_absolute() or not path.resolve().is_relative_to(base.resolve()):
            raise ValueError('Percorso non valido.')
        if any(p.is_symlink() or p.is_junction() for p in (path, *path.parents) if p != base.parent):
            raise ValueError('Collegamenti non consentiti nella pulizia.')
        if not path.is_file():
            raise ValueError('Elenco cambiato: richiedi una nuova anteprima.')
        stat = path.stat()
        if stat.st_size != entry['bytes'] or stat.st_mtime_ns != entry['mtime']:
            raise ValueError('Un file è cambiato: richiedi una nuova anteprima.')
        if entry.get('sha256') and self.digest(path)!=entry['sha256']:
            raise ValueError('Il contenuto di un file è cambiato: richiedi una nuova anteprima.')
        return path

    def apply(self, token):
        plan = self.plans.pop(token, None)
        if not plan or plan['expires'] < time.monotonic():
            raise ValueError('Anteprima scaduta: prepara nuovamente la pulizia.')
        active = {str(v['path'].resolve()) for v in self.app.sessions.values() if 'path' in v}
        paths = [self.checked(e, self.app.root) for e in plan['files']]
        if any(str(p.resolve()) in active for p in paths):
            raise ValueError('Un documento è aperto: chiudilo e prepara una nuova anteprima.')
        trash = self.app.root / 'trash'
        if trash.is_symlink() or trash.is_junction():
            raise ValueError('Cestino collegato non consentito.')
        batch = secrets.token_hex(16)
        dest = trash / batch
        dest.mkdir(parents=True)
        (dest / 'manifest.json').write_text(json.dumps(plan['files']), encoding='utf8')
        moved = []
        try:
            for path, entry in zip(paths, plan['files']):
                target = dest / entry['id']
                target.parent.mkdir(parents=True, exist_ok=True)
                path.rename(target)
                moved.append((path, target))
        except Exception:
            for path, target in reversed(moved):
                target.rename(path)
            raise
        return {'batch': batch, 'count': len(moved), 'originalsPreserved': True}

    def batches(self):
        root = self.app.root / 'trash'
        if root.is_symlink() or root.is_junction():
            return []
        return [{'batch': p.parent.name, 'count': len(json.loads(p.read_text('utf8')))}
                for p in sorted(root.glob('*/manifest.json'))
                if not p.is_symlink() and not p.parent.is_symlink() and not p.parent.is_junction()]

    def restore(self, batch):
        import re
        if not isinstance(batch, str) or not re.fullmatch('[0-9a-f]{32}', batch):
            raise ValueError('Cestino non valido.')
        root = self.app.root / 'trash' / batch
        if any(p.is_symlink() or p.is_junction() for p in (root, root.parent)):
            raise ValueError('Cestino collegato non consentito.')
        entries = json.loads((root / 'manifest.json').read_text('utf8'))
        pairs = []
        for entry in entries:
            source = self.checked(entry, root)
            dest = self.app.root / entry['id']
            if not any(dest.resolve().is_relative_to(self.app.root / name) for name in ('inputs', 'outputs')) or dest.exists():
                raise ValueError('Ripristino interrotto: il percorso è occupato o non valido.')
            if any(p.is_symlink() or p.is_junction() for p in dest.parents):
                raise ValueError('Cartella collegata non consentita.')
            pairs.append((source, dest))
        moved = []
        try:
            for source, dest in pairs:
                dest.parent.mkdir(parents=True, exist_ok=True)
                source.rename(dest)
                moved.append((source, dest))
        except Exception:
            for source, dest in reversed(moved):
                dest.rename(source)
            raise
        (root / 'manifest.json').unlink()
        return {'restored': len(pairs)}

    def purge_preview(self):
        root = self.app.root / 'trash'
        files = []
        for batch in self.batches():
            folder = root / batch['batch']
            entries = json.loads((folder / 'manifest.json').read_text('utf8'))
            for entry in entries:
                source = self.checked(entry, folder)
                files.append({**entry, 'id': source.relative_to(root).as_posix()})
            stat = (folder / 'manifest.json').stat()
            files.append({'id': batch['batch'] + '/manifest.json', 'bytes': stat.st_size, 'mtime': stat.st_mtime_ns, 'sha256': self.digest(folder/'manifest.json')})
        token = secrets.token_urlsafe(24)
        self.purge_plans = {token: {'files': files, 'expires': time.monotonic() + 300}}
        return {'token': token, 'count': sum(not f['id'].endswith('/manifest.json') for f in files),
                'bytes': sum(f['bytes'] for f in files)}

    def purge(self, p):
        if p.get('confirmation') != 'ELIMINA':
            raise ValueError('Scrivi ELIMINA per confermare lo svuotamento definitivo del cestino.')
        plan = self.purge_plans.pop(p.get('token'), None)
        if not plan or plan['expires'] < time.monotonic():
            raise ValueError('Anteprima scaduta: controlla nuovamente il cestino.')
        root = self.app.root / 'trash'
        paths = [self.checked(entry, root) for entry in plan['files']]
        for path in paths:
            path.unlink()
        return {'deleted': sum(p.name != 'manifest.json' for p in paths)}

    def dispatch(self, p):
        if not self.app.busy.acquire(blocking=False):
            raise ValueError('Attendi la fine dell’elaborazione prima della pulizia.')
        try:
            with self.app.office_lock, self.app.workspace_lock:
                cmd = p['cmd']
                if cmd == 'cleanupPreview': return self.preview(p)
                if cmd == 'cleanupApply': return self.apply(p.get('token'))
                if cmd == 'cleanupRestore': return self.restore(p.get('batch'))
                if cmd == 'cleanupStatus': return {'batches': self.batches(), 'path': str(self.app.root / 'trash')}
                if cmd == 'cleanupPurgePreview': return self.purge_preview()
                if cmd == 'cleanupPurge': return self.purge(p)
        finally:
            self.app.busy.release()
