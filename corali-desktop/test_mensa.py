"""All examples use invented identities. Exercise the same RPC actions as the desktop UI."""

import csv
import io
import tempfile
import unittest
from pathlib import Path
import openpyxl
import app
import mensa
from workspace_tools import write_xlsx

CF = "TSTFNT10A01A000P"
FIELDS = [
    "TIPO UTENTE",
    "PLESSO MECC",
    "CODICE FISCALE",
    "MESE",
    "COGNOME",
    "NOME",
    "CLASSE",
    "TOTALE PRESENZE IN MENSA",
]
PUPIL = ["studente", "001", CF, "Febbraio", "Fittizio", "Unità", "1A", 2]


class MealsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.a = app.Application(Path(self.tmp.name) / "data")
        self.addCleanup(self.a.advanced.ai.stop)
        self.dir = Path(self.tmp.name)

    def workbook(self, name, sheets):
        p = self.dir / name
        write_xlsx(p, sheets)
        return p

    def setup_case(self, monthly=False):
        days = [] if monthly else ["01", "28", "29"]
        values = [] if monthly else ["X", 0, 1]
        self.row = PUPIL + values
        rows = [FIELDS + days, self.row]
        teacher = list(self.row)
        teacher[0] = "docente"
        self.school = self.workbook(
            "scuola.xlsx", [("Classe", rows), ("Riepilogo", rows + [teacher])]
        )
        self.grid = [
            [
                "ID gestionale",
                "Codice fiscale",
                "29",
                "01",
                "28",
                "Nome",
                "Cognome",
                "Classe",
                "Plesso",
            ],
            ["00001", CF, "", "", "", "Unità", "Fittizio", "1A", "001"],
        ]
        self.model = self.workbook(
            "modello.xlsx", [("Alunni", [["Mese: Febbraio 2028"]] + self.grid)]
        )
        self.ref = self.dir / "modello.csv"
        with self.ref.open("w", encoding="cp1252", newline="") as f:
            csv.writer(f, delimiter=";").writerows(self.grid)

    def call(self):
        def adopt(p):
            return self.a.import_bytes(p.name, p.read_bytes())["id"]

        return dict(
            cmd="mensa",
            schools=[adopt(self.school)],
            model=adopt(self.model),
            reference=adopt(self.ref),
            period="2028-02",
        )

    def test_daily_export_preview_dates_exact_bytes_and_duplicate(self):
        self.setup_case()
        p = self.call()
        preview = self.a.dispatch(p)
        self.assertTrue(preview["ready"], preview["issues"])
        self.assertEqual(preview["summary"]["duplicates"], 1)
        self.assertEqual(preview["summary"]["teachers"], 1)
        self.assertEqual(preview["summary"]["meals"], 2)
        with self.assertRaisesRegex(ValueError, "anteprima"):
            self.a.dispatch(dict(p, action="csv", token="incorrect"))
        p.update(action="csv", token=preview["token"])
        result = self.a.dispatch(p)
        path = self.a.resolve(result["files"][0]["id"])
        expected = self.ref.read_bytes().replace(b";;;;", b";X;X;;")
        self.assertEqual(path.read_bytes(), expected)
        with self.assertRaisesRegex(ValueError, "già elaborato"):
            self.a.dispatch(p)

    def test_monthly_review_without_csv(self):
        self.setup_case(monthly=True)
        p = self.call()
        preview = self.a.dispatch(p)
        self.assertFalse(preview["ready"])
        self.assertEqual(preview["summary"]["monthly"], 1)
        with self.assertRaisesRegex(ValueError, "sospeso"):
            self.a.dispatch(dict(p, action="csv", token=preview["token"]))
        r = self.a.dispatch(dict(p, action="review", token=preview["token"]))
        b = openpyxl.load_workbook(self.a.resolve(r["files"][0]["id"]))
        self.assertEqual(b["Alunni"]["F2"].value, 2)
        self.assertEqual(b["Alunni"]["G2"].value, "Solo totale")
        b.close()

    def test_conflicts_unknowns_and_formats(self):
        self.setup_case()
        for case in (
            "cf",
            "ambiguo",
            "totale",
            "mancante",
            "prefill",
            "duplicato",
            "formato",
        ):
            with self.subTest(case=case):
                grid = [r.copy() for r in self.grid]
                row = self.row.copy()
                if case == "cf":
                    grid[1][1] = "TSTFNT10A01A001O"
                if case == "ambiguo":
                    grid.append(grid[1].copy())
                if case == "totale":
                    row[7] = 3
                if case == "mancante":
                    grid[1][5] = "Altra"
                if case == "prefill":
                    grid[1][2] = "X"
                if case == "formato":
                    grid[0][0] = "Altro ID"
                m = self.workbook("m.xlsx", [("Dati", [["Mese Febbraio"]] + grid)])
                s = self.workbook(
                    "s.xlsx", [("Dati", [FIELDS + ["01", "28", "29"], row])]
                )
                paths = [s, s] if case == "duplicato" else [s]
                r, _ = mensa.prepare(paths, m, self.ref, "2028-02")
                self.assertFalse(r["ready"], case)

    def test_fallback_and_period(self):
        self.setup_case()
        row = self.row.copy()
        row[2] = ""
        s = self.workbook("s.xlsx", [("Dati", [FIELDS + ["01", "28", "29"], row])])
        r, _ = mensa.prepare([s], self.model, self.ref, "2028-02")
        self.assertTrue(r["ready"], r["issues"])
        self.assertEqual(r["summary"]["missingCF"], 1)
        self.assertIn("plesso e classe", r["review"][1][7])
        with self.assertRaisesRegex(ValueError, "fuori mese"):
            mensa.prepare([s], self.model, self.ref, "2027-02")

    def test_course_model_html_calendar_layout_and_roundtrip(self):
        import calendar, html
        from datetime import date

        self.setup_case()
        days = list(range(1, 30))
        labels = "Lun Mar Mer Gio Ven Sab Dom".split()
        header = ["Corso/alunno", "c.f. alunno", *map(str, days), "Tot."]
        course = [
            "CORSO : Primaria modulo 1 sez. Unica",
            "",
            *[labels[date(2028, 2, d).weekday()] for d in days],
            "",
        ]
        pupil = ["Fittizio Unità", CF] + [""] * 30
        footer = ["Totale per giorno"] + [""] * 31
        empty = [""] * 32

        def model(rows):
            def table(rows):
                return (
                    "<table>"
                    + "".join(
                        "<tr>"
                        + "".join("<td>" + html.escape(c) + "</td>" for c in row)
                        + "</tr>"
                        for row in rows
                    )
                    + "</table>"
                )

            self.model = self.dir / "mensile.xls"
            self.model.write_bytes(
                (
                    table([["MESE:Febbraio2028", "01-03-2028 -", "09:45:12"]])
                    + table(rows)
                ).encode("cp1252")
            )

        model([header, course, pupil, footer, empty])
        request = self.call()
        request["reference"] = ""
        result = self.a.dispatch(request)
        self.assertTrue(result["ready"], result["issues"])
        self.assertEqual(result["courses"][1][-1], "Abbinato")
        saved = self.a.dispatch(dict(request, action="csv", token=result["token"]))
        with self.a.resolve(saved["files"][0]["id"]).open(
            encoding="cp1252", newline=""
        ) as f:
            written = list(csv.reader(f, delimiter=";"))
        expected = pupil.copy()
        expected[2] = expected[30] = "X"
        self.assertEqual(written, [header, course, expected, footer, empty])
        bad = pupil.copy()
        bad[0] = "Altro"
        model([header, course, bad, footer])
        result, _ = mensa.prepare([self.school], self.model, None, "2028-02")
        self.assertFalse(result["ready"])
        self.assertEqual(
            result["courses"][1][-1], "Stesso codice fiscale, nominativo diverso"
        )

    def test_single_school_sheet_and_class_groups(self):
        other = PUPIL.copy()
        other[2], other[6], other[7] = "TSTFNT10A01A001O", "2B", 5
        full = [FIELDS, PUPIL, other]
        single = self.workbook("origine.xlsx", [("Tutti", full)])
        example = self.workbook(
            "esempio.xlsx",
            [
                ("Tutti", full),
                ("Tempo Pieno", [FIELDS, PUPIL]),
                ("Modulo", [FIELDS, other]),
            ],
        )
        result, _ = mensa.prepare([single], None, None, "2028-02", example)
        self.assertEqual(
            [r[-1] for r in result["review"][1:]], ["Tempo Pieno", "Modulo"]
        )
        self.assertEqual(
            result["classes"][1:],
            [["001", "1A", "Tempo Pieno", 1, 2], ["001", "2B", "Modulo", 1, 5]],
        )
        automatic, _ = mensa.prepare([example], None, None, "2028-02")
        self.assertEqual(automatic["classes"], result["classes"])
        self.assertEqual(automatic["summary"]["duplicates"], 2)

    def test_monthly_symbols_count_calendar_order_and_capacity(self):
        self.setup_case(monthly=True)
        p = self.call()
        preview = self.a.dispatch(dict(p, fromTotals=True))
        self.assertTrue(preview["ready"], preview["issues"])
        # Header order is 29, 01, 28: monthly positions use 01 and 28.
        self.assertEqual(preview["grid"][1][2:5], ["", "X", "X"])
        self.assertEqual(preview["symbols"], 2)
        self.assertEqual(preview["review"][1][6], "Solo totale")
        saved = self.a.dispatch(
            dict(p, fromTotals=True, action="csv", token=preview["token"])
        )
        with self.a.resolve(saved["files"][0]["id"]).open(
            encoding="cp1252", newline=""
        ) as stream:
            self.assertEqual(list(csv.reader(stream, delimiter=";")), preview["grid"])
        for total, ready, marks in [(0, True, 0), (3, True, 3), (4, False, 0)]:
            row = PUPIL.copy()
            row[7] = total
            school = self.workbook("conteggio.xlsx", [("Dati", [FIELDS, row])])
            result, _ = mensa.prepare(
                [school], self.model, self.ref, "2028-02", from_totals=True
            )
            self.assertEqual((result["ready"], result["symbols"]), (ready, marks))
        self.setup_case()
        daily, _ = mensa.prepare(
            [self.school], self.model, self.ref, "2028-02", from_totals=True
        )
        self.assertEqual(daily["grid"][1][2:5], ["X", "X", ""])
