"""Synthetic registers only: independent expected daily codes and source totals."""

import tempfile, unittest
from pathlib import Path
import pymupdf
import workspace_tools as tools


def make_register(
    path, days=30, scale=1, missing=False, duplicate=False, mismatch=False, scan=False
):
    doc = pymupdf.open()
    p = doc.new_page(width=842 * scale, height=595 * scale)

    def text(x, y, s, size=7):
        p.insert_text((x * scale, y * scale), s, fontsize=size * scale)

    text(220, 60, "Registro mensile della classe 1A (TEST0001)", 11)
    text(
        220,
        80,
        "Situazione del mese di "
        + ("Febbraio" if days < 30 else "Settembre" if days == 30 else "Ottobre"),
        11,
    )
    for n in range(days):
        if missing and n == 7:
            continue
        text(180 + n * 16.8, 125, str(n if duplicate and n == 7 else n + 1).zfill(2))
    for n, k in enumerate("PARUM"):
        text(710 + n * 25, 110, k)
    expected = []
    for i in range(3):
        y = 150 + i * 60
        name = ["ALUNNO FITTIZIO UNO", "ALUNNA FITTIZIA DUE", "ALUNNO FITTIZIO TRE"][i]
        text(7, y, name, 9)
        text(7, y + 13, "(01-01-2020)", 9)
        codes = ["P", "A", "P"][i]
        text(181, y, codes)
        if i == 2:
            text(181, y + 9, "M")
        totals = [int(codes == "P"), int(codes == "A"), 0, 0, int(i == 2)]
        if mismatch and i == 0:
            totals[0] += 1
        for n, v in enumerate(totals):
            text(710 + n * 25, y + 3, str(v))
        expected.append(
            [name, "01-01-2020", "1A", "TEST0001"]
            + [codes + ("\nM" if i == 2 else "")]
            + [""] * 30
            + totals
        )
    if scan:
        pix = p.get_pixmap()
        doc.close()
        doc = pymupdf.open()
        p = doc.new_page(width=842, height=595)
        p.insert_image(p.rect, stream=pix.tobytes("png"))
    doc.save(path)
    doc.close()
    return expected


class RegisterCases(unittest.TestCase):
    def test_generated_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            for days in (28, 29, 30, 31):
                for scale in (0.75, 1, 1.5):
                    with self.subTest(days=days, scale=scale):
                        p = Path(tmp) / f"{days}-{scale}.pdf"
                        expected = make_register(p, days, scale)
                        sheets, warnings = tools.register(p)
                        self.assertEqual([r[:40] for r in sheets[0][1][1:]], expected)
                        self.assertEqual(warnings, [])

    def test_reject_broken_headers_and_scans(self):
        with tempfile.TemporaryDirectory() as tmp:
            for kw in ({"missing": True}, {"duplicate": True}, {"scan": True}):
                with self.subTest(kw=kw):
                    p = Path(tmp) / "bad.pdf"
                    make_register(p, **kw)
                    with self.assertRaises(ValueError):
                        tools.register(p)

    def test_totals_preserved_and_discrepancy_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "check.pdf"
            expected = make_register(p, mismatch=True)
            sheets, warnings = tools.register(p)
            self.assertEqual(sheets[0][1][1][35], 2)
            self.assertEqual(len(warnings), 1)


if __name__ == "__main__":
    unittest.main()
