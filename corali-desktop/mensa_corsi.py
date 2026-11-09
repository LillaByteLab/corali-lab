"""Read the monthly HTML worksheet as local text, then reconcile its course sections."""

from collections import Counter, defaultdict
from datetime import date
from html.parser import HTMLParser
import calendar
import re


class TableReader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.in_table = False
        self.row = self.cell = None
        self.cells = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            if self.in_table:
                raise ValueError("Modello del gestionale con tabelle annidate.")
            self.in_table = True
        elif tag == "tr" and self.in_table:
            if self.row is not None:
                raise ValueError("Riga HTML incompleta nel modello.")
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            if self.cell is not None or any(
                k in ("rowspan", "colspan") and v != "1" for k, v in attrs
            ):
                raise ValueError("Modello con celle sovrapposte o unite da verificare.")
            self.cell = []
        elif tag == "br" and self.cell is not None:
            self.cell.append("\n")

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append("".join(self.cell).replace("\xa0", " ").strip())
            self.cell = None
            self.cells += 1
            if self.cells > 1000000:
                raise ValueError("Modello troppo grande.")
        elif tag == "tr" and self.row is not None:
            if self.cell is not None:
                raise ValueError("Cella HTML incompleta.")
            self.rows.append(self.row)
            self.row = None
        elif tag == "table":
            if self.row is not None:
                raise ValueError("Tabella HTML incompleta.")
            self.in_table = False


def read_html(raw):
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    reader = TableReader()
    reader.feed(text)
    reader.close()
    if reader.in_table or reader.row is not None or not reader.rows:
        raise ValueError("Modello HTML incompleto.")
    return reader.rows


def reconcile(
    grid, students, year, month, days, issues, identity_issues, notes, norm, valid_cf
):
    header = grid[0]
    if [norm(v) for v in header[:2]] != ["corso alunno", "c f alunno"] or norm(
        header[-1]
    ) != "tot":
        raise ValueError("Colonne Corso/alunno, c.f. alunno o Tot. non riconosciute.")
    if list(days) != list(range(1, calendar.monthrange(year, month)[1] + 1)) or list(
        days.values()
    ) != list(range(2, len(header) - 1)):
        raise ValueError(
            "Nel modello del gestionale mancano giorni o ci sono colonne fuori ordine."
        )
    index = {s["cf"]: s for s in students if s["cf"]}
    source_names = {
        norm(name)
        for s in students
        for name in (s["first"] + " " + s["last"], s["last"] + " " + s["first"])
    }
    courses = [
        [
            "Riga modello",
            "Corso nel modello",
            "Alunno nel modello",
            "CF nel modello",
            "Classe scuola",
            "Pasti scuola",
            "Esito",
        ]
    ]
    output = [r.copy() for r in grid]
    cf_counts = Counter(r[1].strip().upper() for r in grid[1:] if r[1].strip())
    weekdays = "lun mar mer gio ven sab dom".split()
    group = ""
    matched_classes = set()
    for rownum, r in enumerate(grid[1:], 3):
        label, cf = r[0].strip(), r[1].strip().upper()
        if not any(r):
            continue
        if not cf and re.match(r"^corso\s*:", label, re.I):
            group = label.split(":", 1)[1].strip()
            if (
                not group
                or r[-1]
                or any(
                    norm(r[j]) != weekdays[date(year, month, d).weekday()]
                    for d, j in days.items()
                )
            ):
                issues.append(
                    f"Modello riga {rownum}: intestazione del corso o giorni della settimana incoerenti."
                )
            continue
        if not cf and norm(label) == "totale per giorno":
            if any(r[2:]):
                issues.append(f"Modello riga {rownum}: totali già compilati.")
            group = ""
            continue
        if not group:
            issues.append(
                f"Modello riga {rownum}: riga fuori da un corso riconoscibile."
            )
        if any(r[2:]):
            issues.append(f"Modello riga {rownum}: giorni o totale già compilati.")
        pupil = index.get(cf)
        if not cf or not valid_cf(cf):
            status = "Codice fiscale mancante o non valido"
        elif cf_counts[cf] != 1:
            status = "Codice fiscale duplicato nel modello"
        elif pupil is None:
            status = (
                "Nominativo presente con altro codice fiscale"
                if norm(label) in source_names
                else "Codice fiscale assente nei prospetti scuola"
            )
        elif norm(label) not in (
            norm(pupil["last"] + " " + pupil["first"]),
            norm(pupil["first"] + " " + pupil["last"]),
        ):
            status = "Stesso codice fiscale, nominativo diverso"
        else:
            status = "Abbinato"
            level = re.search(r"\b(\d+)\s+sez\b", group, re.I)
            school_level = re.match(r"^\s*(\d+)", pupil["class"])
            if level and school_level and int(level[1]) != int(school_level[1]):
                status = "Classe della scuola diversa dal corso nel modello"
        if pupil:
            matched_classes.add((pupil["school"], pupil["class"]))
            pupil["match"] = (
                f"Riga {rownum} · codice fiscale e nominativo"
                if status == "Abbinato"
                else status
            )
        if status != "Abbinato":
            identity_issues.append(f"Modello riga {rownum}: {status}.")
        else:
            pupil["model_index"] = rownum - 2
            for day in pupil["days"] or []:
                output[rownum - 2][days[day]] = "X"
        courses.append(
            [
                rownum,
                group,
                label,
                cf,
                pupil["class"] if pupil else "",
                pupil["total"] if pupil else "",
                status,
            ]
        )
    if len(courses) == 1:
        issues.append("Il modello non contiene alunni.")
    for s in students:
        if not s["match"]:
            s["match"] = "Assente dal modello selezionato"
            if (s["school"], s["class"]) in matched_classes:
                notes.append(
                    s["loc"]
                    + ": assente dal modello, ma la classe compare tra gli abbinamenti. Verificare l’elenco."
                )
    return output, courses
