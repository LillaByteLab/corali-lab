import io
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

import app
from file_jobs import output_job, recover_orphans, recovery_files, owner
from transcription_queue import EngineCommandError


class ResourceJobs(unittest.TestCase):
    def test_locked_csv_keeps_edits_and_retries(self):
        f = self.a.import_bytes("locked.csv", b"Code,Value\n00123,4")
        sid = self.a.new_office(self.a.resolve(f["id"]))["session"]
        editor = self.a.sessions[sid]["csv"]
        self.a.csv(
            {"cmd": "apply", "changes": [{"row": 1, "column": 1, "value": "5"}]}, sid
        )
        with patch.object(editor, "save", side_effect=PermissionError("locked")):
            with self.assertRaisesRegex(ValueError, "file è in uso"):
                self.a.csv({"cmd": "save"}, sid)
        self.assertTrue(editor.dirty)
        self.assertFalse(any(x["output"] for x in self.a.scan()))
        saved = self.a.csv({"cmd": "save"}, sid)
        self.assertIn(b"00123,5", self.a.resolve(saved["file"]["id"]).read_bytes())
        self.assertEqual(self.a.resolve(f["id"]).read_bytes(), b"Code,Value\n00123,4")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.a = app.Application(Path(self.temp.name) / "data")
        self.ai = self.a.advanced.ai
        self.addCleanup(self.ai.stop)

    def test_import_stream_is_bounded_and_identical(self):
        raw = b"1234" * 800000

        class Bounded(io.BytesIO):
            def read(inner, n=-1):
                self.assertTrue(0 < n <= 1048576)
                return super(Bounded, inner).read(n)

        f = self.a.import_stream("large.bin", Bounded(raw), len(raw))
        self.assertEqual(self.a.resolve(f["id"]).read_bytes(), raw)

    def test_interrupted_import_is_not_published(self):
        with self.assertRaisesRegex(ValueError, "interrotta"):
            self.a.import_stream("broken.bin", io.BytesIO(b"abc"), 100)
        self.assertEqual(self.a.scan(), [])
        self.assertEqual(list((self.a.root / "inputs").iterdir()), [])

    def test_index_avoids_rescan_and_updates_imports(self):
        self.a.scan()
        f = self.a.import_bytes("new.txt", b"test")
        with patch.object(
            self.a, "scan_entries", side_effect=AssertionError("Unexpected scan")
        ):
            self.assertEqual(self.a.scan(refresh=False)[0]["id"], f["id"])

    def test_index_reconciles_external_files(self):
        self.a.scan()
        p = self.a.root / "inputs/external.txt"
        p.write_text("external")
        self.assertEqual(self.a.scan(refresh=False), [])
        self.assertEqual(
            len(self.a.dispatch({"cmd": "files", "refresh": True})["files"]), 1
        )
        p.unlink()
        self.a.file_index.last_scan -= 10
        self.assertEqual(self.a.scan(refresh=False), [])

    def test_output_hidden_until_complete(self):
        with output_job(self.a) as folder:
            (folder / "complete.txt").write_text("result")
            self.assertEqual(self.a.scan(), [])
        self.assertEqual(len(self.a.scan(refresh=False)), 1)

    def test_output_exception_and_cancel_preserve_original(self):
        original = self.a.import_bytes("original.txt", b"keep")
        for cancel in (False, True):
            event = threading.Event()
            with self.assertRaises(ValueError):
                with output_job(self.a, event) as folder:
                    (folder / "partial.txt").write_text("partial")
                    if cancel:
                        event.set()
                    else:
                        raise ValueError("failed")
            self.assertFalse(folder.exists())
        self.assertEqual(self.a.resolve(original["id"]).read_bytes(), b"keep")

    def test_recovery_quarantines_dead_keeps_live_and_unknown(self):
        cache = self.a.root / "cache"
        for name, record in [
            ("dead", {"pid": 99999999, "stamp": "gone"}),
            ("live", owner()),
            ("unknown", None),
        ]:
            (cache / (name + ".part")).write_bytes(name.encode())
            if record:
                (cache / (name + ".owner.json")).write_text(json.dumps(record))
        r = recover_orphans(self.a)
        self.assertFalse((cache / "dead.part").exists())
        self.assertTrue((cache / "live.part").exists())
        self.assertTrue((cache / "unknown.part").exists())
        self.assertEqual(r["unidentified"], 2)
        self.assertEqual(
            [f["name"].split("-", 1)[1] for f in recovery_files(self.a)], ["dead.part"]
        )

    def test_recovery_locked_file_does_not_block_startup(self):
        p = self.a.root / "cache/dead.part"
        p.write_bytes(b"partial")
        p.with_suffix(".owner.json").write_text(
            json.dumps({"pid": 99999999, "stamp": "gone"})
        )
        with patch.object(Path, "rename", side_effect=PermissionError("locked")):
            r = recover_orphans(self.a)
        self.assertEqual(r["quarantined"], 0)
        self.assertEqual(r["unidentified"], 1)
        self.assertTrue(p.exists())
        self.assertTrue(p.with_suffix(".owner.json").exists())

    def test_pending_job_dead_process_recovered_not_published(self):
        folder = self.a.folder()
        (folder / ".corali-pending").write_text(
            json.dumps({"pid": 99999999, "stamp": "gone"})
        )
        (folder / "result.txt").write_bytes(b"recover me")
        recover_orphans(self.a)
        self.assertEqual(self.a.scan(), [])
        self.assertEqual(len(recovery_files(self.a)), 1)

    def test_retention_default_off_then_opt_in_moves_only_imports(self):
        source = self.a.import_bytes("old.txt", b"original")
        p = self.a.resolve(source["id"])
        os.utime(p, (1, 1))
        with output_job(self.a) as folder:
            result = folder / "result.txt"
            result.write_text("result")
            os.utime(result, (1, 1))
        self.a.startup_maintenance()
        self.assertTrue(p.exists())
        self.a.advanced.save_preferences({"cleanupAutoDays": 7})
        self.a.startup_maintenance()
        self.assertFalse(p.exists())
        self.assertTrue(result.exists())
        batches = self.a.dispatch({"cmd": "cleanupStatus"})["batches"]
        self.a.dispatch({"cmd": "cleanupRestore", "batch": batches[0]["batch"]})
        self.assertEqual(p.read_bytes(), b"original")

    def test_retention_does_not_clean_another_live_instance(self):
        self.a.advanced.save_preferences({"cleanupAutoDays": 7})
        (self.a.root / "session.json").write_text(json.dumps({"pid": 1234}))
        with patch("app.process_stamp", return_value="alive"), patch.object(
            self.a.cleanup, "preview"
        ) as preview:
            self.a.startup_maintenance()
        preview.assert_not_called()

    def test_ai_preferences_persist_disable_and_validate(self):
        value = {
            "enabled": False,
            "preload": False,
            "profile": "capable",
            "idleMinutes": 1,
        }
        self.ai.configure(value)
        with self.assertRaisesRegex(ValueError, "disattivato"):
            self.ai.ask("ciao", "", "documenti", threading.Event())
        from local_ai import LocalAI

        other = LocalAI(
            self.a.root, app.ROOT / "ai-manifest.json", architecture="arm64"
        )
        self.assertEqual(other.preferences, value)
        with self.assertRaises(ValueError):
            self.ai.configure({**value, "idleMinutes": 0})

    def test_ai_resource_guard_and_model_adapter_separation(self):
        # The pre-existing trained pack must expose the metadata now used by status/setup.
        base = self.ai.root / "trained-v1"
        base.mkdir(parents=True)
        for key in ("base", "adapter"):
            (base / self.ai.manifest["trained"][key]["file"]).write_bytes(b"present")
        self.assertGreater(self.ai.status()["downloadBytes"], 0)
        self.ai.preferences["profile"] = "capable"
        self.assertIn("Qwen3", self.ai.model_spec()[1]["name"])
        self.assertNotEqual(
            self.ai.model_spec()[0], self.ai.model_spec(trained=True)[0]
        )
        with patch("ai_controls.free_memory_mb", return_value=2000):
            with self.assertRaisesRegex(ValueError, "RAM libera"):
                self.ai.check_resources()
            self.ai.check_resources(trained=True)

    def test_idle_does_not_stop_busy_request_then_releases(self):
        self.ai.preferences["idleMinutes"] = 1
        self.ai.last_used = time.monotonic() - 61
        with patch.object(self.ai, "stop") as stop:
            self.ai.release_idle()
            stop.assert_called_once()
        self.ai.lock.acquire()
        try:
            with patch.object(self.ai, "stop") as stop, patch.object(
                self.ai, "mark_used"
            ) as schedule:
                self.ai.release_idle()
                stop.assert_not_called()
                schedule.assert_called_once()
        finally:
            self.ai.lock.release()

    def test_catalog_cache_content_and_config_invalidation(self):
        engine = Path(self.temp.name) / "cedro.exe"
        engine.write_bytes(b"fake")
        self.a.cedro = engine
        f = self.a.import_bytes("a.txt", b"a")
        with patch.object(
            self.a, "command", return_value="docx\tWord\n"
        ) as command, patch.object(self.a, "conversion_options", return_value=[]):
            self.a.dispatch({"cmd": "catalog", "id": f["id"]})
            self.a.dispatch({"cmd": "catalog", "id": f["id"]})
            self.assertEqual(command.call_count, 3)
            self.a.resolve(f["id"]).write_bytes(b"b")
            self.a.dispatch({"cmd": "catalog", "id": f["id"]})
            self.assertEqual(command.call_count, 6)
            config = self.a.root / "engine-config/Cedro/config.txt"
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text("changed")
            self.a.dispatch({"cmd": "catalog", "id": f["id"]})
            self.assertEqual(command.call_count, 9)

    def test_transcription_one_invocation_preserves_success_on_partial_failure(self):
        paths = [
            self.a.resolve(self.a.import_bytes(n, b"audio")["id"])
            for n in ("good.wav", "bad.wav")
        ]

        def command(args):
            good = args[2]
            good.with_suffix(".txt").write_text("Trascrizione valida")
            raise EngineCommandError(
                "Formato non valido", stdout="OK " + str(good) + " -> output\n"
            )

        with patch.object(self.a, "require_cedro"), patch.object(
            self.a, "prepare_native_engine"
        ), patch.object(self.a, "engine_settings"), patch.object(
            self.a, "command", side_effect=command
        ) as invoked:
            with output_job(self.a) as folder:
                outputs = self.a.transcript(paths, {"cpu": True}, folder)
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(len(outputs), 1)
        self.assertEqual([r["ok"] for r in self.a.transcript_items], [True, False])
        self.assertTrue(all(p.read_bytes() == b"audio" for p in paths))

    def test_http_import_download_range_and_auth(self):
        server = app.make_server(self.a)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        raw = b"01234567" * 400000
        req = urllib.request.Request(
            self.a.origin + "/import",
            data=raw,
            headers={"X-Corali-Token": self.a.token, "X-Filename": "large.bin"},
        )
        with urllib.request.urlopen(req) as response:
            f = json.load(response)["data"]
        url = self.a.origin + "/local-file?id=" + f["id"]
        with patch.object(
            Path, "read_bytes", side_effect=AssertionError("Whole file read")
        ):
            req = urllib.request.Request(url, headers={"X-Corali-Token": self.a.token})
            with urllib.request.urlopen(req) as response:
                self.assertEqual(response.read(), raw)
            req.add_header("Range", "bytes=1048570-1048600")
            with urllib.request.urlopen(req) as response:
                self.assertEqual(response.status, 206)
                self.assertEqual(response.read(), raw[1048570:1048601])
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(url)


if __name__ == "__main__":
    unittest.main()
