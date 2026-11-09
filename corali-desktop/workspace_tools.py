"""Local document workflows. Values are copied; only explicit arithmetic is calculated."""

from pathlib import Path
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from xml.etree import ElementTree as ET
import calendar, json, re, zipfile
from statistics import median
from xml.sax.saxutils import escape
import pymupdf


class Formula:
    def __init__(self, expression, value):
        if not re.fullmatch(r"[A-Z0-9+*/()., -]+", expression) or any(
            name != "ROUND" for name in re.findall(r"([A-Z]+)\(", expression)
        ):
            raise ValueError("Formula non consentita.")
        self.expression = expression
        self.value = value


def text(path):
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        with pymupdf.open(path) as doc:
            return "\n".join(p.get_text() for p in doc)[:40000]
    if path.suffix.lower() in (".docx", ".xlsx", ".odt", ".ods"):
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if sum(e.file_size for e in entries) > 200 * 1024 * 1024:
                raise ValueError("Documento troppo grande.")
            parts = []
            for e in entries:
                if e.filename in (
                    "word/document.xml",
                    "content.xml",
                    "xl/sharedStrings.xml",
                ) or re.fullmatch(r"xl/worksheets/sheet\d+\.xml", e.filename):
                    raw = archive.read(e)
                    if b"<!DOCTYPE" in raw.upper():
                        raise ValueError("XML non supportato.")
                    parts.append(" ".join(ET.fromstring(raw).itertext()))
            return "\n".join(parts)[:40000]
    if path.suffix.lower() in (".txt", ".csv", ".md"):
        raw = path.read_bytes()
        try:
            return raw.decode("utf-8-sig")[:40000]
        except UnicodeDecodeError:
            return raw.decode("cp1252", errors="replace")[:40000]
    raise ValueError(
        "Scegli PDF, DOCX, XLSX, ODT, ODS, CSV o TXT per leggere il contesto."
    )


def write_docx(path, content):
    paragraphs = "".join(
        '<w:p><w:r><w:t xml:space="preserve">' + escape(line) + "</w:t></w:r></w:p>"
        for line in content.split("\n")
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        )
        z.writestr(
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        )
        z.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
            + paragraphs
            + "</w:body></w:document>",
        )


def letters(index):
    result = ""
    while index:
        index, n = divmod(index - 1, 26)
        result = chr(65 + n) + result
    return result


def write_xlsx(path, sheets):
    """Small OOXML writer: text is never interpreted as a formula or link."""
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    relation = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    names = set()
    normalized = []
    for name, rows in sheets:
        name = re.sub(r"[\[\]:*?/\\]", "_", name).strip(" '")[:28] or "Dati"
        base = name
        n = 1
        while name.lower() in names:
            n += 1
            name = base[:26] + " " + str(n)
        names.add(name.lower())
        normalized.append((name, rows))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + "".join(
                '<Override PartName="/xl/worksheets/sheet'
                + str(i)
                + '.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for i in range(1, len(sheets) + 1)
            )
            + "</Types>",
        )
        z.writestr(
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="'
            + relation
            + '/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        )
        workbook = ET.Element("workbook", {"xmlns": ns, "xmlns:r": relation})
        container = ET.SubElement(workbook, "sheets")
        for i, (name, rows) in enumerate(normalized, 1):
            ET.SubElement(
                container,
                "sheet",
                {"name": name, "sheetId": str(i), "r:id": "rId" + str(i)},
            )
        ET.SubElement(workbook, "calcPr", {"fullCalcOnLoad": "1", "forceFullCalc": "1"})
        z.writestr(
            "xl/workbook.xml",
            ET.tostring(workbook, encoding="utf-8", xml_declaration=True),
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                '<Relationship Id="rId'
                + str(i)
                + '" Type="'
                + relation
                + '/worksheet" Target="worksheets/sheet'
                + str(i)
                + '.xml"/>'
                for i in range(1, len(sheets) + 1)
            )
            + "</Relationships>",
        )
        for i, (name, rows) in enumerate(normalized, 1):
            sheet = ET.Element("worksheet", {"xmlns": ns})
            views = ET.SubElement(sheet, "sheetViews")
            view = ET.SubElement(views, "sheetView", {"workbookViewId": "0"})
            ET.SubElement(
                view,
                "pane",
                {
                    "ySplit": "1",
                    "topLeftCell": "A2",
                    "activePane": "bottomLeft",
                    "state": "frozen",
                },
            )
            cols = ET.SubElement(sheet, "cols")
            width = max((len(r) for r in rows), default=1)
            ET.SubElement(
                cols, "col", {"min": "1", "max": "1", "width": "30", "customWidth": "1"}
            )
            if width > 1:
                ET.SubElement(
                    cols,
                    "col",
                    {"min": "2", "max": str(width), "width": "13", "customWidth": "1"},
                )
            data = ET.SubElement(sheet, "sheetData")
            for r, row in enumerate(rows, 1):
                node = ET.SubElement(data, "row", {"r": str(r)})
                for c, value in enumerate(row, 1):
                    cell = ET.SubElement(node, "c", {"r": letters(c) + str(r)})
                    if isinstance(value, Formula):
                        ET.SubElement(cell, "f").text = value.expression
                        ET.SubElement(cell, "v").text = str(value.value)
                    elif isinstance(value, (int, Decimal)) and not isinstance(
                        value, bool
                    ):
                        ET.SubElement(cell, "v").text = str(value)
                    else:
                        cell.set("t", "inlineStr")
                        inline = ET.SubElement(cell, "is")
                        ET.SubElement(
                            inline,
                            "t",
                            {"{http://www.w3.org/XML/1998/namespace}space": "preserve"},
                        ).text = re.sub(
                            r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value or "")
                        )[:32767]
            if rows:
                ET.SubElement(
                    sheet,
                    "autoFilter",
                    {"ref": "A1:" + letters(width) + str(len(rows))},
                )
            z.writestr(
                "xl/worksheets/sheet" + str(i) + ".xml",
                ET.tostring(sheet, encoding="utf-8", xml_declaration=True),
            )


def register(path):
    """Recognize monthly native-text registers. Fail closed on unexpected geometry."""
    records = []
    current = None
    warnings = []
    with pymupdf.open(path) as doc:
        if len(doc) > 200:
            raise ValueError("Usa un registro fino a 200 pagine.")
        for pageNo, page in enumerate(doc, 1):
            words = page.get_text("words")
            if not words:
                raise ValueError(
                    f"Pagina {pageNo}: nessun testo leggibile. Controlla se occorre OCR."
                )
            match = re.search(
                r"Registro mensile della classe\s+(\S+)\s+\(([^)]+)\)", page.get_text()
            )
            if match:
                month = re.search(
                    r"Situazione del mese di\s+(\w+)(?:[ \t]+(\d{4})\b)?",
                    page.get_text(),
                )
                current = {
                    "class": match[1],
                    "school": match[2],
                    "month": month[1] if month else "Registro",
                }
                lines = defaultdict(list)
                for w in words:
                    if re.fullmatch(r"\d{1,2}", w[4]) and 1 <= int(w[4]) <= 31:
                        lines[round(w[1])].append(w)
                dayline = sorted(
                    max(lines.values(), key=len, default=[]), key=lambda w: w[0]
                )
                daynumbers = [int(w[4]) for w in dayline]
                monthlength = {
                    "gennaio": 31,
                    "febbraio": calendar.monthrange(int(month[2]), 2)[1]
                    if month and month[2]
                    else None,
                    "marzo": 31,
                    "aprile": 30,
                    "maggio": 31,
                    "giugno": 30,
                    "luglio": 31,
                    "agosto": 31,
                    "settembre": 30,
                    "ottobre": 31,
                    "novembre": 30,
                    "dicembre": 31,
                }.get(current["month"].lower())
                if (
                    not 28 <= len(dayline) <= 31
                    or daynumbers != list(range(1, len(dayline) + 1))
                    or (monthlength is not None and len(dayline) != monthlength)
                    or (current["month"].lower() == "febbraio" and len(dayline) > 29)
                ):
                    raise ValueError(
                        "Intestazione incompleta o giorni duplicati a pagina "
                        + str(pageNo)
                        + ". Verifica il PDF: nessuna tabella esportata."
                    )
                centers = [((w[0] + w[2]) / 2, w[4].zfill(2)) for w in dayline]
                step = median(b[0] - a[0] for a, b in zip(centers, centers[1:]))
                labels = sorted(
                    [
                        w
                        for w in words
                        if w[4] in ("P", "A", "R", "U", "M")
                        and w[0] > centers[-1][0] + 10
                        and w[1] < dayline[0][1]
                    ],
                    key=lambda w: w[0],
                )
                if sorted(w[4] for w in labels) != sorted("PARUM"):
                    raise ValueError(
                        f"Pagina {pageNo}, intestazione: controlla le cinque colonne dei totali."
                    )
                totals = [((w[0] + w[2]) / 2, w[4]) for w in labels]
                minimum = dayline[0][3] + 2
                page_width = page.rect.width
            elif not current:
                raise ValueError(
                    "Questo PDF non corrisponde al profilo Registri presenze. Prova Tabelle generiche o OCR."
                )
            else:
                if abs(page_width - page.rect.width) > 1:
                    raise ValueError(
                        f"Pagina {pageNo}: larghezza diversa senza una nuova intestazione dei giorni."
                    )
                minimum = 0
            maximum = min(
                (w[1] - 3 for w in words if w[4] == "Legenda:"),
                default=page.rect.height,
            )
            lines = []
            identity = [
                w
                for w in words
                if w[0] < centers[0][0] - 12 and minimum <= w[1] < maximum
            ]
            for w in sorted(identity, key=lambda w: (w[1], w[0])):
                if not lines or abs(lines[-1][0] - w[1]) > 2:
                    lines.append([w[1], []])
                lines[-1][1].append(w)
            anchors = []
            # A new line of printed totals distinguishes adjacent pupils if a birth date is missing.
            total_baselines = [
                w[1]
                for w in words
                if w[4].isdigit()
                and abs((w[0] + w[2]) / 2 - totals[0][0]) < step / 2
                and minimum <= w[1] < maximum
            ]
            for y, group in lines:
                value = " ".join(w[4] for w in sorted(group, key=lambda w: w[0]))
                date = re.fullmatch(r"\((\d{2}-\d{2}-\d{4})\)", value)
                if date:
                    if not records or records[-1]["birth"] or (match and not anchors):
                        raise ValueError(
                            f"Pagina {pageNo}, riga {len(anchors) or 1}: data di nascita senza anagrafica univoca."
                        )
                    records[-1]["birth"] = date[1]
                    records[-1]["pages"] = sorted(set(records[-1]["pages"] + [pageNo]))
                elif re.search("[A-Za-zÀ-ÿ]", value):
                    if (
                        records
                        and not records[-1]["birth"]
                        and records[-1]["startPage"] == pageNo
                        and not any(
                            anchors[-1][0] <= ty < y - 2 for ty in total_baselines
                        )
                    ):
                        records[-1]["name"] += " " + value
                        continue
                    row = {
                        **current,
                        "name": value,
                        "birth": "",
                        "startPage": pageNo,
                        "pages": [pageNo],
                        "days": {},
                        "totals": {},
                        "issues": [],
                        "pageRow": len(anchors) + 1,
                    }
                    records.append(row)
                    anchors.append((y, row))
            for w in words:
                if w[0] < centers[0][0] - 12 or not minimum <= w[1] < maximum:
                    continue
                candidates = [r for y, r in anchors if y <= w[1] + 2]
                row = (
                    candidates[-1]
                    if candidates
                    else next(
                        (
                            r
                            for r in reversed(records)
                            if not match and r["startPage"] < pageNo
                        ),
                        None,
                    )
                )
                if row is None:
                    raise ValueError(
                        f"Pagina {pageNo}, riga prima della prima anagrafica: dati senza destinatario."
                    )
                x = (w[0] + w[2]) / 2
                row["pages"] = sorted(set(row["pages"] + [pageNo]))
                if x < (centers[-1][0] + totals[0][0]) / 2:
                    cx, day = min(centers, key=lambda c: abs(c[0] - x))
                    location = f"pagina {pageNo}, riga iniziata a pagina {row['startPage']} n. {row['pageRow']}, giorno {day}"
                    if w[0] < cx - step / 2 or w[2] > cx + step / 2:
                        raise ValueError(
                            f"{location}: testo a cavallo di due colonne. Verifica il PDF."
                        )
                    if not re.fullmatch(r"[PARUM]+", w[4]):
                        row["issues"].append(f"{location}: sigla da verificare nel PDF")
                    row["days"].setdefault(day, []).append(w[4])
                else:
                    cx, key = min(totals, key=lambda c: abs(c[0] - x))
                    if abs(cx - x) > 12 or not w[4].isdigit() or key in row["totals"]:
                        raise ValueError(
                            f"Pagina {pageNo}, riga {row['pageRow']}, totale {key} ambiguo."
                        )
                    row["totals"][key] = int(w[4])
    if not records:
        raise ValueError("Nessuna riga riconosciuta.")
    sheets = {}
    header = (
        ["Alunno", "Data nascita", "Classe", "Codice scuola"]
        + [str(i).zfill(2) for i in range(1, 32)]
        + ["Totale " + k for k in ("P", "A", "R", "U", "M")]
        + ["Controllo", "Pagina PDF"]
    )
    for n, row in enumerate(records, 1):
        missing = ([] if row["birth"] else ["data di nascita"]) + [
            "totale " + k for k in "PARUM" if k not in row["totals"]
        ]
        if missing:
            row["issues"].append(
                f"Pagina {row['startPage']}, riga {row['pageRow']}: manca "
                + ", ".join(missing)
            )
        counts = Counter(
            code
            for cell in row["days"].values()
            for token in cell
            if re.fullmatch(r"[PARUM]+", token)
            for code in token
        )
        mismatch = [
            f"totale {k} (PDF {v}, sigle {counts[k]})"
            for k, v in row["totals"].items()
            if counts[k] != v
        ]
        issues = row["issues"] + mismatch
        check = "Da verificare: " + ", ".join(issues) if issues else "Conteggi coerenti"
        if issues:
            warnings.append({"row": n, "pages": row["pages"], "message": check})
        sheets.setdefault(row["month"], [header]).append(
            [row["name"], row["birth"], row["class"], row["school"]]
            + ["\n".join(row["days"].get(str(i).zfill(2), [])) for i in range(1, 32)]
            + [row["totals"].get(k, "") for k in ("P", "A", "R", "U", "M")]
            + [check, ", ".join(map(str, row["pages"]))]
        )
    return list(sheets.items()), warnings


def tables(path, profile):
    if profile == "register":
        return register(path)
    sheets = []
    with pymupdf.open(path) as doc:
        if len(doc) > 200:
            raise ValueError("Usa un PDF fino a 200 pagine.")
        for n, page in enumerate(doc, 1):
            for j, t in enumerate(page.find_tables().tables, 1):
                sheets.append(("Pagina " + str(n) + " tabella " + str(j), t.extract()))
    if not sheets:
        raise ValueError(
            "Non riconosco una tabella affidabile. Per registri mensili scegli Registri presenze; per scansioni usa prima OCR. Nessun dato inventato."
        )
    return sheets, []


def tariff(base, rate):
    try:
        base = Decimal(str(base).replace(",", "."))
        rate = Decimal(str(rate).replace(",", "."))
        if (
            not base.is_finite()
            or not rate.is_finite()
            or base < 0
            or not 0 <= rate <= 100
        ):
            raise ValueError()
        if base > Decimal("1000000000"):
            raise ValueError()
        final = (base * (Decimal(1) - rate / 100)).quantize(
            Decimal(".01"), rounding=ROUND_HALF_UP
        )
        return {
            "base": str(base),
            "rate": str(rate),
            "amount": str(final),
            "rounding": "Al centesimo, metà verso l’alto",
            "rule": "importo base × (1 − riduzione / 100)",
        }
    except (InvalidOperation, ValueError):
        raise ValueError(
            "Inserisci una base non negativa e una percentuale da 0 a 100, senza separatori delle migliaia."
        )


def repetition_warnings(content):
    words = re.findall(r"\w+", content.lower())
    counts = Counter(tuple(words[i : i + 8]) for i in range(max(0, len(words) - 7)))
    return [" ".join(phrase) for phrase, count in counts.most_common(12) if count >= 4]
