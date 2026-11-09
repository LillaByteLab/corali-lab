"""Publish complete results; quarantine recoverable leftovers from dead processes."""

import contextlib
import ctypes
import json
import os
import shutil
import uuid
from pathlib import Path


def process_stamp(pid):
    """None means gone; unknown permissions conservatively mean alive."""
    if type(pid) is not int or pid <= 0:
        return None
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return "alive"
        except ProcessLookupError:
            return None
        except PermissionError:
            return "unknown"
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.c_void_p] * 4
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return None if ctypes.get_last_error() == 87 else "unknown"
    try:
        values = [ctypes.c_ulonglong() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(v) for v in values)):
            return "unknown"
        return str(values[0].value)
    finally:
        kernel.CloseHandle(handle)


def owner():
    return {"pid": os.getpid(), "stamp": process_stamp(os.getpid())}


def alive(record):
    if type(record) is not dict:
        return True
    current = process_stamp(record.get("pid"))
    return current is not None and (
        current in ("unknown", "alive") or current == record.get("stamp")
    )


def mark_pending(folder):
    (folder / ".corali-pending").write_text(json.dumps(owner()), encoding="utf8")


@contextlib.contextmanager
def output_job(app, cancelled=None):
    folder = app.folder()
    mark_pending(folder)
    try:
        yield folder
        if cancelled is not None and cancelled.is_set():
            raise ValueError(
                "Operazione annullata. Nessun risultato incompleto pubblicato."
            )
        with app.workspace_lock:
            (folder / ".corali-pending").unlink()
            if hasattr(app, "file_index"):
                app.file_index.update(folder)
    except BaseException:
        # Only this newly allocated output, never source files or other jobs.
        if (
            folder.parent == app.root / "outputs"
            and not folder.is_symlink()
            and not folder.is_junction()
        ):
            shutil.rmtree(folder, ignore_errors=True)
        raise


def recover_orphans(app):
    root = app.root
    recovery = root / "recovery"
    if recovery.is_symlink() or recovery.is_junction():
        return {"quarantined": 0, "unidentified": 0}
    legacy_dead = False
    try:
        previous = json.loads((root / "session.json").read_text("utf8"))
        legacy_dead = process_stamp(previous.get("pid")) is None
    except (OSError, ValueError, TypeError):
        pass
    moved = 0
    unknown = 0

    def quarantine(path):
        nonlocal moved, unknown
        try:
            recovery.mkdir(exist_ok=True)
            target = recovery / (uuid.uuid4().hex + "-" + path.name)
            path.rename(target)
            moved += 1
            return True
        except OSError:
            unknown += 1
            return False

    for part in (root / "cache").glob("*.part"):
        if part.is_symlink() or part.is_junction():
            continue
        metadata = part.with_suffix(".owner.json")
        try:
            record = json.loads(metadata.read_text("utf8"))
            dead = not alive(record)
        except (OSError, ValueError, TypeError):
            dead = legacy_dead
        if dead:
            moved_part = quarantine(part)
            if moved_part and metadata.is_file() and not metadata.is_symlink():
                quarantine(metadata)
        else:
            unknown += 1
    markers = [
        p
        for category in ("inputs", "outputs")
        for p in (root / category).glob("*/.corali-pending")
    ]
    for marker in markers:
        folder = marker.parent
        if folder.is_symlink() or folder.is_junction() or marker.is_symlink():
            continue
        try:
            dead = not alive(json.loads(marker.read_text("utf8")))
        except (OSError, ValueError, TypeError):
            dead = legacy_dead
        if dead:
            quarantine(folder)
        else:
            unknown += 1
    return {"quarantined": moved, "unidentified": unknown}


def recovery_files(app):
    root = app.root / "recovery"
    if root.is_symlink() or root.is_junction():
        return []
    entries = []
    for folder, dirs, names in os.walk(root, followlinks=False):
        directory = Path(folder)
        dirs[:] = [
            d
            for d in dirs
            if not (directory / d).is_symlink() and not (directory / d).is_junction()
        ]
        for name in names:
            p = directory / name
            if name.startswith(".") or name.endswith(".owner.json") or p.is_symlink():
                continue
            entries.append(
                {
                    "id": p.relative_to(root).as_posix(),
                    "name": name,
                    "bytes": p.stat().st_size,
                }
            )
    return entries
