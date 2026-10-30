"""Saved local AI preferences, resource checks and bounded idle lifetime."""

import ctypes
import json
import os
import threading
import time


def free_memory_mb():
    if os.name != "nt":
        return None

    class Memory(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong)
            for name in (
                "total",
                "available",
                "pageTotal",
                "pageAvailable",
                "virtualTotal",
                "virtualAvailable",
                "extended",
            )
        ]

    value = Memory()
    value.length = ctypes.sizeof(value)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
        return None
    return value.available // (1024 * 1024)


class AIControls:
    def init_controls(self):
        self.preferences_file = self.root / "preferences.json"
        self.preferences = {
            "enabled": True,
            "preload": False,
            "profile": "light",
            "idleMinutes": 5,
        }
        self.idle_timer = None
        self.last_used = time.monotonic()
        try:
            self.preferences.update(
                self.validate_preferences(
                    json.loads(self.preferences_file.read_text("utf8"))
                )
            )
        except (OSError, ValueError, TypeError):
            pass

    @staticmethod
    def validate_preferences(value):
        if type(value) is not dict:
            raise ValueError("Preferenze AI non valide.")
        if (
            type(value.get("enabled")) is not bool
            or type(value.get("preload")) is not bool
        ):
            raise ValueError("Scegli se abilitare e precaricare l’assistente.")
        if value.get("profile") not in ("light", "capable"):
            raise ValueError("Profilo AI non disponibile.")
        if type(value.get("idleMinutes")) is not int or value["idleMinutes"] not in (
            1,
            5,
            15,
            30,
        ):
            raise ValueError("Scegli un tempo di inattività valido.")
        return {k: value[k] for k in ("enabled", "preload", "profile", "idleMinutes")}

    def configure(self, value):
        selected = self.validate_preferences(value)
        if not self.lock.acquire(blocking=False):
            raise ValueError(
                "Attendi la fine della richiesta AI prima di cambiare profilo."
            )
        try:
            self.stop()
            self.root.mkdir(parents=True, exist_ok=True)
            temp = self.preferences_file.with_suffix(".tmp")
            temp.write_text(json.dumps(selected), encoding="utf8")
            temp.replace(self.preferences_file)
            self.preferences = selected
            return self.status()
        finally:
            self.lock.release()

    def model_spec(self, trained=False):
        if not trained and self.preferences["profile"] == "capable":
            info = self.manifest["models"]["capable"]
            return self.root / info["file"], info
        files = self.trained_files()
        if files:
            return files[0], self.manifest["trained"]["base"]
        return self.model, self.manifest["model"]

    def require_enabled(self):
        if not self.preferences["enabled"]:
            raise ValueError(
                "Assistente AI disattivato. Riattivalo nelle preferenze AI. Editor e calcoli manuali restano disponibili."
            )

    def check_resources(self, trained=False):
        available = free_memory_mb()
        minimum = (
            3072 if not trained and self.preferences["profile"] == "capable" else 768
        )
        if available is not None and available < minimum:
            raise ValueError(
                f"RAM libera insufficiente: {available} MB. Chiudi altre applicazioni o scegli il profilo leggero; occorrono almeno {minimum} MB liberi."
            )

    def mark_used(self):
        self.last_used = time.monotonic()
        if self.idle_timer:
            self.idle_timer.cancel()
        self.idle_timer = threading.Timer(
            self.preferences["idleMinutes"] * 60, self.release_idle
        )
        self.idle_timer.daemon = True
        self.idle_timer.start()

    def release_idle(self):
        if not self.lock.acquire(blocking=False):
            self.mark_used()
            return
        try:
            if (
                time.monotonic() - self.last_used
                >= self.preferences["idleMinutes"] * 60
            ):
                self.stop()
        finally:
            self.lock.release()

    def preload_requested(self):
        if (
            not self.preferences["enabled"]
            or not self.preferences["preload"]
            or not self.status()["ready"]
        ):
            return

        def load():
            with self.lock:
                try:
                    self.start(threading.Event())
                    self.mark_used()
                except Exception as error:
                    self.backend_note = "Caricamento iniziale non completato: " + str(
                        error
                    )

        threading.Thread(target=load, daemon=True).start()
