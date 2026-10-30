import copy, hashlib, json, random, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
from app import Application
from local_ai import LocalAI
from local_operations import execute, parse_action, messages, NeedsReview


class OperationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = Application(self.root / "data")

    def tearDown(self):
        self.app.advanced.ai.stop()
        self.tmp.cleanup()

    def test_preview_is_readonly_and_counts_random_data(self):
        rng = random.Random(520)
        before = list(self.app.root.rglob("*"))
        for _ in range(500):
            cells = [
                rng.choice(["P", "A", "R", "U", "M", "", None])
                for _ in range(rng.randint(1, 366))
            ]
            data = {"cells": cells, "declared": rng.randint(0, 366)}
            original = copy.deepcopy(data)
            r = self.app.dispatch(
                {"cmd": "operationPreview", "action": "count", "data": data}
            )
            self.assertFalse(r["applied"])
            self.assertEqual(data, original)
            expected = []
            empty = 0
            for pos, value in enumerate(cells, 1):
                if value == "P":
                    expected.append(pos)
                elif value is None or value == "":
                    empty += 1
            self.assertEqual(r["result"]["posizioni_P"], expected)
            self.assertEqual(r["result"]["presenze_esplicite"], len(expected))
            self.assertEqual(r["result"]["celle_vuote"], empty)
        self.assertEqual(list(self.app.root.rglob("*")), before)

    def test_formulas_and_exact_rounding(self):
        self.assertEqual(
            execute("count_formula", {"range": "$B$2:$AF$2", "criterion": "P"})[
                "formula"
            ],
            '=COUNTIF($B$2:$AF$2,"P")',
        )
        self.assertEqual(
            execute("sum_formula", {"range": "C3:C9"})["formula"], "=SUM(C3:C9)"
        )
        self.assertEqual(
            execute("discount", {"amount": "10,05", "percent": "50"})["amount"], "5.03"
        )
        self.assertEqual(
            execute("discount", {"amount": "100"})["kind"], "clarification"
        )

    def test_bad_data_fails_closed(self):
        for action, data in [
            ("count", {"cells": ["?"]}),
            ("count", {"cells": ["P"], "declared": True}),
            ("count_formula", {"range": "A1:A2);EXEC(1)", "criterion": "P"}),
            ("sum_formula", {"range": "XFE1:XFE2"}),
            ("sum_formula", {"range": "B2:A1"}),
            ("discount", {"amount": "NaN", "percent": "20"}),
            ("discount", {"amount": "100", "percent": "101"}),
        ]:
            with self.subTest(action=action, data=data), self.assertRaises(ValueError):
                self.app.dispatch(
                    {"cmd": "operationPreview", "action": action, "data": data}
                )

    def test_model_cannot_supply_values_or_code(self):
        for text in [
            '{"action":"shell"}',
            '{"action":"count","total":999}',
            "null",
            '{"action":[]}',
            '{"action":null}',
        ]:
            with self.assertRaises(NeedsReview):
                parse_action(text)
        wire = json.dumps(
            messages(
                "Conta le presenze",
                {
                    "cells": ["P"],
                    "document_note": "SECRET DOCUMENT",
                    "amount": "123456",
                },
            )
        )
        self.assertNotIn("SECRET DOCUMENT", wire)
        self.assertNotIn("123456", wire)

    def test_missing_pack_does_not_use_original_base_with_adapter(self):
        engine = self.app.advanced.ai
        with patch.object(engine, "status", return_value={"ready": True}):
            with self.assertRaisesRegex(ValueError, "pacchetto AI"):
                engine.start(threading.Event(), trained=True)
        self.assertIsNone(engine.process)

    def test_pack_integrity_rechecked_after_change(self):
        file = self.root / "model"
        file.write_bytes(b"good")
        engine = self.app.advanced.ai
        info = {"sha256": hashlib.sha256(b"good").hexdigest()}
        engine.verify(file, info)
        file.write_bytes(b"corrupted")
        with self.assertRaisesRegex(ValueError, "non integro"):
            engine.verify(file, info)

    def test_suggestion_is_never_executed_and_releases_memory(self):
        import io

        engine = self.app.advanced.ai
        payload = {
            "choices": [
                {
                    "message": {"content": '{"action":"discount"}'},
                    "finish_reason": "stop",
                }
            ]
        }
        engine.origin = "http://127.0.0.1:1234"
        with patch.object(engine, "start") as start, patch.object(
            engine, "stop"
        ) as stop, patch.object(
            engine.http, "open", return_value=io.BytesIO(json.dumps(payload).encode())
        ):
            result = engine.suggest(
                "Calcola lo sconto",
                {"amount": "100", "percent": "20"},
                threading.Event(),
            )
            self.assertTrue(result["requiresConfirmation"])
            self.assertFalse(result["applied"])
            self.assertNotIn("result", result)
            start.assert_called_once()
            stop.assert_called_once()

    def test_incomplete_response_never_produces_proposal(self):
        import io

        engine = self.app.advanced.ai
        engine.origin = "http://127.0.0.1:1234"
        payload = {
            "choices": [
                {
                    "message": {"content": '{"action":"count"}'},
                    "finish_reason": "length",
                }
            ]
        }
        with patch.object(engine, "start"), patch.object(engine, "stop"), patch.object(
            engine.http, "open", return_value=io.BytesIO(json.dumps(payload).encode())
        ):
            with self.assertRaises(ValueError):
                engine.suggest("Conta", {"cells": ["P"]}, threading.Event())


if __name__ == "__main__":
    unittest.main()
