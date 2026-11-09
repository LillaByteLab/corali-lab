"""Preparazione locale dei pasti. Il tracciato deriva dal modello scelto dall'operatore."""

import calendar
import codecs
import csv
import hashlib
import io
import json
import re
import zipfile
import sqlite3
from contextlib import closing
from collections import defaultdict
from datetime import date
from pathlib import Path

import mensa_corsi
from csv_tools import CsvSession, digest
from workspace_tools import write_xlsx

MONTHS = "gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre".split()
ALIASES = {
    "role": ("tipo utente", "ruolo"),
    "school": ("plesso mecc", "plesso", "codice plesso", "codice scuola"),
    "cf": ("codice fiscale", "cf", "c f"),
    "month": ("mese", "periodo"),
    "last": ("cognome",),
    "first": ("nome",),
    "class": ("classe",),
    "total": ("totale presenze in mensa", "totale pasti", "totale mensa"),
}
CF = re.compile(
    r"[A-Z]{6}[0-9LMNPQRSTUV]{2}[ABCDEHLMPRST][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]"
)
MAX_CELLS = 1000000


def valid_cf(value):
    if not CF.fullmatch(value):
        return False
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    odd = (
        1,
        0,
        5,
        7,
        9,
        13,
        15,
        17,
        19,
        21,
        2,
        4,
        18,
        20,
        11,
        3,
        6,
        8,
        12,
        14,
        16,
        10,
        22,
        25,
        24,
        23,
    )
    check = 0
    for i, char in enumerate(value[:-1]):
        index = int(char) if char.isdigit() else alphabet.index(char)
        check += odd[index] if i % 2 == 0 else index
    return value[-1] == alphabet[check % 26]


def norm(value):
    return " ".join(re.findall(r"[^\W_]+", str(value).casefold()))


def display(value, fmt):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if (
        isinstance(value, (float, int))
        and not isinstance(value, bool)
        and int(value) == value
    ):
        if re.fullmatch("0+", fmt):
            return str(int(value)).zfill(len(fmt))
        if fmt.lower() in ("general", "@"):
            return str(int(value))
    raise ValueError(
        "Formato numerico inatteso. Verifica la cella o prepara una copia come testo."
    )


def workbooks(path):
    """Read inert cell values, preserving formatted identifiers and refusing formulas in OOXML."""
    if path.stat().st_size > 30 * 1024**2:
        raise ValueError("Usa un prospetto fino a 30 MB.")
    if path.suffix.lower() == ".xls":
        with path.open("rb") as stream:
            signature = stream.read(256).lstrip(b"\xef\xbb\xbf \t\r\n").lower()
        if signature.startswith((b"<!doctype html", b"<html", b"<table")):
            yield "Stampa mensile", mensa_corsi.read_html(path.read_bytes())
            return
        import xlrd

        book = xlrd.open_workbook(path, formatting_info=True, on_demand=True)
        try:
            for sh in book.sheets():
                if sh.nrows * sh.ncols > MAX_CELLS:
                    raise ValueError("Foglio troppo grande.")
                rows = []
                for i in range(sh.nrows):
                    row = []
                    for j, c in enumerate(sh.row(i)):
                        fmt = (
                            book.format_map[
                                book.xf_list[c.xf_index].format_key
                            ].format_str
                            if c.xf_index is not None
                            else "General"
                        )
                        if c.ctype == xlrd.XL_CELL_DATE:
                            value = xlrd.xldate_as_datetime(c.value, book.datemode)
                        elif c.ctype in (xlrd.XL_CELL_ERROR, xlrd.XL_CELL_BOOLEAN):
                            raise ValueError(
                                f"{sh.name}, riga {i + 1}, colonna {j + 1}: valore non utilizzabile."
                            )
                        else:
                            value = c.value
                        try:
                            row.append(display(value, fmt))
                        except ValueError as exc:
                            raise ValueError(
                                f"{sh.name}, riga {i + 1}, colonna {j + 1}: {exc}"
                            ) from exc
                    rows.append(row)
                if any(any(row) for row in rows):
                    yield sh.name, rows
        finally:
            book.release_resources()
    elif path.suffix.lower() == ".xlsx":
        import openpyxl

        with zipfile.ZipFile(path) as archive:
            if sum(x.file_size for x in archive.infolist()) > 120 * 1024**2:
                raise ValueError("Cartella Excel troppo grande.")
        book = openpyxl.load_workbook(path, read_only=True, keep_links=False)
        try:
            for sh in book:
                if (sh.max_row or 0) * (sh.max_column or 0) > MAX_CELLS:
                    raise ValueError("Foglio troppo grande.")
                rows = []
                count = 0
                for i, cells in enumerate(sh.rows, 1):
                    count += len(cells)
                    if count > MAX_CELLS:
                        raise ValueError("Foglio troppo grande.")
                    row = []
                    for j, c in enumerate(cells, 1):
                        try:
                            if c.data_type in ("e", "f"):
                                raise ValueError(
                                    "Formula o errore. Serve una copia con valori verificati."
                                )
                            row.append(display(c.value, c.number_format or "General"))
                        except ValueError as exc:
                            raise ValueError(
                                f"{sh.title}, riga {i}, colonna {j}: {exc}"
                            ) from exc
                    rows.append(row)
                if any(any(r) for r in rows):
                    yield sh.title, rows
        finally:
            book.close()
    else:
        raise ValueError("Seleziona un file .xls o .xlsx.")


def fields(header):
    result = {}
    for i, value in enumerate(header):
        for key, names in ALIASES.items():
            if norm(value) in names:
                if key in result:
                    raise ValueError(f"Intestazione ripetuta: {value}.")
                result[key] = i
    return result


def period_matches(value, year, month):
    value = norm(value)
    accepted = (MONTHS[month - 1], str(month), f"{month:02}")
    return any(value in (m, f"{m} {year}", f"{year} {m}") for m in accepted)


def day_columns(header, year, month):
    days = {}
    for i, value in enumerate(header):
        m = re.fullmatch(
            r"(?:giorno\s+)?(\d{1,2})(?:/(\d{1,2})/(\d{4}))?", value.strip(), re.I
        )
        if not m:
            continue
        day = int(m[1])
        if m[2] and (int(m[2]), int(m[3])) != (month, year):
            raise ValueError(f"Colonna {i + 1}: data di un altro mese.")
        if day in days or not 1 <= day <= calendar.monthrange(year, month)[1]:
            raise ValueError(f"Colonna {i + 1}: giorno duplicato o fuori mese.")
        days[day] = i
    return days


def person(row, cols):
    return {key: (row[i].strip() if i < len(row) else "") for key, i in cols.items()}


def identity(p):
    return tuple(norm(p.get(k, "")) for k in ("last", "first", "school", "class"))


def school_rows(paths, year, month, issues):
    students = []
    seen = {}
    hashes = set()
    staff = repeats = staff_meals = 0
    notes = []
    for path in paths:
        fp = digest(path)
        if fp in hashes:
            issues.append(f"{path.name}: stesso file caricato due volte.")
            continue
        hashes.add(fp)
        for sheet, rows in workbooks(path):
            prefix = f"{path.name} / {sheet}"
            head = next(
                (
                    i
                    for i, r in enumerate(rows[:20])
                    if any(norm(x) in ALIASES["role"] for x in r)
                ),
                None,
            )
            if head is None:
                issues.append(prefix + ": intestazione scolastica non riconosciuta.")
                continue
            header = rows[head]
            cols = fields(header)
            if (
                not {"role", "month", "school", "class", "first", "last", "total"}
                <= cols.keys()
            ):
                issues.append(
                    prefix + ": mancano colonne per anagrafica, periodo o totale."
                )
                continue
            days = day_columns(header, year, month)
            extra = sum(
                1
                for row in rows[head + 1 :]
                if any(
                    v
                    for j, v in enumerate(row)
                    if j >= len(header) or not header[j].strip()
                )
            )
            if extra:
                notes.append(
                    f"{prefix}: {extra} righe contengono valori in colonne senza intestazione, da verificare."
                )
            for i, row in enumerate(rows[head + 1 :], head + 2):
                if not any(row):
                    continue
                p = person(row, cols)
                loc = f"{prefix}, riga {i}"
                role = norm(p["role"])
                if not period_matches(p["month"], year, month):
                    issues.append(loc + ": mese diverso o non leggibile.")
                    continue
                if (
                    not re.fullmatch(r"\d{1,2}", p["total"])
                    or int(p["total"]) > calendar.monthrange(year, month)[1]
                ):
                    issues.append(loc + ": totale pasti non valido.")
                    continue
                total = int(p["total"])
                if role in ("docente", "insegnante"):
                    staff += 1
                    staff_meals += total
                    continue
                if role not in ("alunno", "alunna", "studente", "studentessa"):
                    issues.append(loc + ": tipo utente non riconosciuto.")
                    continue
                cf = p.get("cf", "").upper()
                p["cf"] = cf
                if cf and not valid_cf(cf):
                    issues.append(
                        loc
                        + ": codice fiscale con formato o carattere di controllo non valido."
                    )
                if not all(identity(p)):
                    issues.append(loc + ": anagrafica, plesso o classe incompleti.")
                present = []
                if days and extra:
                    problem = (
                        prefix
                        + ": verificare le colonne senza intestazione prima del CSV."
                    )
                    if problem not in issues:
                        issues.append(problem)
                for day, j in days.items():
                    mark = row[j].strip().upper() if j < len(row) else ""
                    if mark in ("X", "1"):
                        present.append(day)
                    elif mark not in ("", "0"):
                        issues.append(f"{loc}, giorno {day}: simbolo inatteso.")
                if days and total != len(present):
                    issues.append(
                        loc + ": totale mensile diverso dalle presenze giornaliere."
                    )
                key = cf or identity(p)
                signature = (
                    identity(p),
                    total,
                    tuple(sorted(present)),
                    tuple(sorted(days)),
                )
                if key in seen:
                    old_path, old_sheet, old_sig = seen[key]
                    if (
                        cf
                        and path == old_path
                        and old_sheet != sheet
                        and signature == old_sig
                    ):
                        repeats += 1
                    else:
                        issues.append(
                            loc
                            + ": alunno duplicato o dati discordanti. Controllare le righe."
                        )
                    continue
                seen[key] = path, sheet, signature
                students.append(
                    dict(
                        p,
                        total=total,
                        days=present if days else None,
                        loc=loc,
                        match="",
                    )
                )
    return students, staff, staff_meals, repeats, notes


def match_template(path, students, year, month, issues, identity_issues, notes):
    sheets = list(workbooks(path))
    if len(sheets) != 1:
        raise ValueError("Usa un modello con un solo foglio compilato.")
    _, rows = sheets[0]
    if len(rows) < 3:
        raise ValueError("Modello privo di intestazione o alunni.")
    header = rows[1]
    official = norm(header[0]) == "corso alunno"
    period_text = next((x.strip() for x in rows[0] if x.strip()), "")
    title = re.fullmatch(r"mese\s*:?\s*(.*)", period_text, re.I)
    period_value = re.sub(r"(?<=[A-Za-z])(?=\d{4}$)", " ", title[1]) if title else ""
    if not period_matches(period_value, year, month):
        raise ValueError(
            "Il mese o l’anno del modello non corrisponde al periodo selezionato."
        )
    while (
        header
        and header[-1] == ""
        and all(len(r) < len(header) or r[len(header) - 1] == "" for r in rows[2:])
    ):
        header.pop()
    width = len(header)
    if any(any(row[width:]) for row in rows[2:]):
        raise ValueError(
            "Modello con dati oltre l’ultima intestazione. Verifica le colonne."
        )
    grid = [header] + [(r + [""] * width)[:width] for r in rows[2:]]
    while not official and len(grid) > 1 and not any(grid[-1]):
        grid.pop()
    cols, days = fields(header), day_columns(header, year, month)
    if official:
        output, courses = mensa_corsi.reconcile(
            grid, students, year, month, days, issues, identity_issues, notes, norm, valid_cf
        )
        return grid, output, courses
    if not days or (
        "cf" not in cols and not {"last", "first", "class", "school"} <= cols.keys()
    ):
        raise ValueError(
            "Intestazioni del modello non riconosciute: verificare identificativi e colonne giornaliere."
        )
    by_cf, by_name = defaultdict(list), defaultdict(list)
    for i, row in enumerate(grid[1:], 1):
        p = person(row, cols)
        cf = p.get("cf", "").upper()
        if cf:
            by_cf[cf].append(i)
            if not valid_cf(cf):
                issues.append(
                    f"Modello riga {i + 2}: codice fiscale con formato o carattere di controllo non valido."
                )
        key = identity(p)
        if all(key):
            by_name[key].append(i)
        if any(row[j].strip() for j in days.values()):
            issues.append(f"Modello riga {i + 2}: giorni già compilati.")
    for matches in by_cf.values():
        if len(matches) > 1:
            issues.append(
                "Codice fiscale duplicato nel modello alle righe "
                + ", ".join(str(i + 2) for i in matches)
                + "."
            )
    used = set()
    output = [r.copy() for r in grid]
    for p in students:
        matches = by_cf.get(p["cf"], []) if p["cf"] else []
        method = "codice fiscale"
        if not matches and all(identity(p)):
            matches = by_name.get(identity(p), [])
            method = "nome, cognome, plesso e classe"
        if len(matches) != 1:
            p["match"] = "Ambiguo" if matches else "Non riconosciuto"
            issues.append(p["loc"] + ": " + p["match"] + ".")
            continue
        i = matches[0]
        q = person(grid[i], cols)
        if (
            i in used
            or (p["cf"] and q.get("cf") and p["cf"] != q["cf"].upper())
            or any(
                q.get(k) and norm(q[k]) != norm(p[k])
                for k in ("last", "first", "school", "class")
            )
        ):
            p["match"] = "Dati discordanti"
            issues.append(
                f"{p['loc']}: abbinamento discordante con la riga modello {i + 2}."
            )
            continue
        p["match"] = f"Riga {i + 2} · {method}"
        if not q.get("cf"):
            p["match"] += " (codice fiscale assente nel modello)"
        used.add(i)
        p["model_index"] = i
        for day in p["days"] or []:
            if day not in days:
                issues.append(f"{p['loc']}: giorno {day} assente dal modello.")
            else:
                output[i][days[day]] = "X"
    for i in range(1, len(grid)):
        if i not in used:
            issues.append(
                f"Modello riga {i + 2}: nessuna presenza scolastica abbinata."
            )
    return grid, output, []


def class_groups(reference):
    """Derive class labels only from a complete roll and disjoint detail sheets."""
    if not reference:
        return {}
    sheets = {}
    for name, rows in workbooks(reference):
        header = next(
            (
                i
                for i, r in enumerate(rows[:20])
                if any(norm(x) in ALIASES["role"] for x in r)
            ),
            None,
        )
        if header is None:
            continue
        cols = fields(rows[header])
        if not {"cf", "role", "class", "school"} <= cols.keys():
            continue
        pupils = {}
        for row in rows[header + 1 :]:
            p = person(row, cols)
            if norm(p["role"]) not in ("alunno", "alunna", "studente", "studentessa"):
                continue
            key = p["cf"].upper()
            if not valid_cf(key) or key in pupils or not p["school"] or not p["class"]:
                raise ValueError(
                    f"Classi di riferimento: anagrafica incompleta o ripetuta nel foglio {name}."
                )
            pupils[key] = (norm(p["school"]), norm(p["class"]))
        if pupils:
            sheets[name] = pupils
    full = [
        name
        for name, roll in sheets.items()
        if all(set(other.items()) <= set(roll.items()) for other in sheets.values())
    ]
    if len(full) != 1 or len(sheets) < 3:
        raise ValueError(
            "Per riprendere i gruppi scegli un esempio con elenco completo e almeno due fogli di dettaglio."
        )
    master = sheets.pop(full[0])
    classes = defaultdict(set)
    members = set()
    for name, pupils in sheets.items():
        if members.intersection(pupils):
            raise ValueError("L’esempio assegna lo stesso alunno a più gruppi.")
        members.update(pupils)
        for key in pupils.values():
            classes[key].add(name)
    if members != set(master):
        raise ValueError(
            "I fogli di dettaglio dell’esempio non coprono l’elenco completo."
        )
    return {k: next(iter(names)) for k, names in classes.items() if len(names) == 1}


def prepare(paths, model, reference, period, groups_file=None, from_totals=False):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period) or not 1 <= len(paths) <= 30:
        raise ValueError("Seleziona mese, anno e da uno a trenta prospetti.")
    year, month = map(int, period.split("-"))
    issues = []
    students, staff, staff_meals, repeats, notes = school_rows(
        paths, year, month, issues
    )
    monthly = sum(p["days"] is None for p in students)
    if not students:
        issues.append("Nessun alunno utilizzabile.")
    raw = None
    courses = []
    identity_issues = []
    grid_preview = []
    symbols = 0
    if model:
        grid, output, courses = match_template(
            model, students, year, month, issues, identity_issues, notes
        )
        enrolled = (
            [p for p in students if p["match"].startswith("Riga ")]
            if courses
            else students
        )
        if reference:
            ref = CsvSession(reference)
            delimiter, encoding, newline = ref.delimiter, ref.encoding, ref.newline
            if ref.rows != grid:
                issues.append(
                    "La copia CSV deve corrispondere al modello con la sola riga del mese rimossa."
                )
            else:
                notes.append(
                    f"Formato CSV confrontato: {encoding}, separatore {repr(delimiter)}."
                )
        else:
            delimiter, encoding, newline = ";", "cp1252", "\r\n"
            notes.append(
                "Formato proposto per la prova nel gestionale: punto e virgola, Windows-1252."
            )
        if from_totals:
            notes.append(
                "Per i soli totali mensili le X occupano le prime colonne giornaliere in ordine cronologico. La posizione è convenzionale. Le date documentate restano quelle della scuola."
            )
        elif any(p["days"] is None for p in enrolled):
            issues.append(
                "Sono disponibili solo totali mensili. Scegli «Converti i totali mensili in X» per preparare il conteggio."
            )
        day_cols = day_columns(grid[0], year, month)
        sorted_cols = [day_cols[day] for day in sorted(day_cols)]
        for pupil in enrolled:
            idx = pupil.get("model_index")
            if idx is None:
                continue
            row = output[idx]
            if pupil["days"] is None:
                if not from_totals:
                    continue
                if pupil["total"] > len(sorted_cols):
                    issues.append(
                        pupil["loc"]
                        + ": colonne giornaliere insufficienti per il totale."
                    )
                    continue
                for j in sorted_cols[: pupil["total"]]:
                    row[j] = "X"
            count = sum(row[j] == "X" for j in sorted_cols)
            symbols += count
            if count != pupil["total"]:
                issues.append(
                    pupil["loc"] + ": il numero di X differisce dal totale scolastico."
                )
        grid_preview = output
        if not issues:
            buf = io.StringIO(newline="")
            csv.writer(buf, delimiter=delimiter, lineterminator=newline).writerows(
                output
            )
            try:
                if (
                    encoding == "utf-16"
                    and reference
                    and reference.read_bytes().startswith(codecs.BOM_UTF16_BE)
                ):
                    raw = codecs.BOM_UTF16_BE + buf.getvalue().encode("utf-16-be")
                else:
                    raw = buf.getvalue().encode(encoding)
            except UnicodeEncodeError:
                issues.append(
                    "Il formato CSV scelto non rappresenta alcuni caratteri. Usa un CSV di riferimento in UTF-8."
                )
            if (
                raw is not None
                and list(
                    csv.reader(
                        io.StringIO(raw.decode(encoding), newline=""),
                        delimiter=delimiter,
                    )
                )
                != output
            ):
                raise ValueError("Controllo del CSV generato fallito.")
    else:
        issues.append("Seleziona il modello Excel esportato dal gestionale.")
        if monthly:
            issues.append(f"{monthly} alunni hanno solo il totale mensile.")
    draft_ready = bool(
        from_totals
        and courses
        and identity_issues
        and not issues
        and raw is not None
        and any("model_index" in pupil for pupil in students)
    )
    issues.extend(identity_issues)
    groups = class_groups(groups_file)
    if repeats and not groups_file:
        detected = defaultdict(set)
        for path in paths:
            try:
                mapping = class_groups(path)
            except ValueError:
                continue
            for key, name in mapping.items():
                detected[key].add(name)
        groups = {k: next(iter(v)) for k, v in detected.items() if len(v) == 1}
    summary = dict(
        students=len(students),
        meals=sum(p["total"] for p in students),
        teachers=staff,
        teacherMeals=staff_meals,
        duplicates=repeats,
        monthly=monthly,
        matched=sum(p["match"].startswith("Riga ") for p in students),
        missingCF=sum(not p["cf"] for p in students),
    )
    review = [
        [
            "Cognome",
            "Nome",
            "Codice fiscale",
            "Plesso",
            "Classe",
            "Pasti",
            "Giorni documentati",
            "Abbinamento",
            "Origine",
            "Gruppo scuola",
        ]
    ]
    for p in students:
        review.append(
            [
                p["last"],
                p["first"],
                p["cf"],
                p["school"],
                p["class"],
                p["total"],
                "Solo totale" if p["days"] is None else ", ".join(map(str, p["days"])),
                p["match"] or "Modello assente",
                p["loc"],
                groups.get((norm(p["school"]), norm(p["class"])), ""),
            ]
        )
    buckets = defaultdict(list)
    for row in review[1:]:
        buckets[(row[3], row[4], row[9])].append(row)
    classes = [["Plesso", "Classe", "Gruppo scuola", "Alunni", "Pasti"]] + [
        [*k, len(v), sum(r[5] for r in v)] for k, v in sorted(buckets.items())
    ]
    snapshot = hashlib.sha256(
        json.dumps(
            [
                period,
                from_totals,
                summary,
                issues,
                notes,
                review,
                courses,
                classes,
                grid_preview,
            ],
            ensure_ascii=False,
        ).encode()
        + (raw or b"")
    ).hexdigest()
    return dict(
        summary=summary,
        issues=issues,
        notes=notes,
        review=review,
        courses=courses,
        classes=classes,
        grid=grid_preview,
        symbols=symbols,
        draftReady=draft_ready,
        token=snapshot,
        ready=not issues and raw is not None,
    ), raw


def run(app, p):
    from file_jobs import output_job

    paths = [app.resolve(i) for i in p.get("schools", [])]
    model = app.resolve(p["model"]) if p.get("model") else None
    ref = app.resolve(p["reference"]) if p.get("reference") else None
    period = p.get("period", "")
    groups_file = app.resolve(p["groupsFile"]) if p.get("groupsFile") else None
    result, raw = prepare(
        paths, model, ref, period, groups_file, p.get("fromTotals") is True
    )
    action = p.get("action", "preview")
    if action == "preview":
        return result
    if p.get("token") != result["token"]:
        raise ValueError("I dati sono cambiati: ripeti l’anteprima.")
    if action == "review":
        counts = result["summary"]
        summary = [
            ["Periodo", period],
            ["Simboli X nelle righe abbinate", result["symbols"]],
            ["Alunni", counts["students"]],
            ["Pasti alunni", counts["meals"]],
            ["Docenti esclusi", counts["teachers"]],
            ["Pasti docenti esclusi", counts["teacherMeals"]],
            ["Righe scolastiche ripetute", counts["duplicates"]],
            ["Alunni con solo totale", counts["monthly"]],
            ["Alunni abbinati", counts["matched"]],
            ["Alunni senza codice fiscale", counts["missingCF"]],
        ]
        detail = defaultdict(list)
        head, *rows = result["review"]
        for row in sorted(rows, key=lambda r: (r[3], r[4], norm(r[0]), norm(r[1]))):
            detail[row[9] or (row[3] + " " + row[4])].append(row)
        with output_job(app, app.cancel) as folder:
            dest = folder / f"Verifica mensa {period}.xlsx"
            write_xlsx(
                dest,
                [
                    ("Riepilogo", summary),
                    ("Alunni", result["review"]),
                    ("Classi", result["classes"]),
                    *(
                        [("Anteprima simboli", result["grid"])]
                        if result["grid"]
                        else []
                    ),
                    *(
                        [("Confronto modello", result["courses"])]
                        if result["courses"]
                        else []
                    ),
                    (
                        "Controlli",
                        [["Esito"]] + [[x] for x in result["issues"] + result["notes"]],
                    ),
                ]
                + [(name, [head] + members) for name, members in detail.items()],
            )
    elif action == "draft" and result["draftReady"]:
        with output_job(app, app.cancel) as folder:
            dest = folder / f"BOZZA PARZIALE - Pasti {period}.csv"
            dest.write_bytes(raw)
            if dest.read_bytes() != raw:
                raise ValueError("Verifica della bozza CSV fallita.")
        return {
            "files": [app.meta(dest)],
            "message": "Bozza parziale per controllo. Le anagrafiche da verificare sono indicate nel riepilogo.",
        }
    elif action == "csv" and result["ready"]:
        # Reserve before publishing. A crash leaves a visible pending reservation instead of a second export.
        keys = (
            set()
            if result["courses"]
            else {period + "/file/" + digest(path) for path in paths}
        )
        for row in result["review"][1:]:
            if result["courses"] and not row[7].startswith("Riga "):
                continue
            identity_key = row[2] or json.dumps([norm(row[i]) for i in (0, 1, 3, 4)])
            keys.add(
                period + "/alunno/" + hashlib.sha256(identity_key.encode()).hexdigest()
            )
        with closing(sqlite3.connect(app.root / "mensa-esportazioni.sqlite")) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS exports (key TEXT PRIMARY KEY, output TEXT)"
            )
            try:
                with db:
                    db.executemany(
                        "INSERT INTO exports VALUES (?, NULL)", [(k,) for k in keys]
                    )
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    "Prospetto o alunno già elaborato per questo mese. Controlla il CSV nei Risultati prima di ripetere il caricamento."
                ) from exc
            try:
                with output_job(app, app.cancel) as folder:
                    dest = folder / f"Pasti {period}.csv"
                    dest.write_bytes(raw)
                    if dest.read_bytes() != raw:
                        raise ValueError("Verifica della copia CSV fallita.")
            except BaseException:
                with db:
                    db.executemany(
                        "DELETE FROM exports WHERE key=? AND output IS NULL",
                        [(k,) for k in keys],
                    )
                raise
            with db:
                db.executemany(
                    "UPDATE exports SET output=? WHERE key=?",
                    [(app.meta(dest)["id"], k) for k in keys],
                )
    else:
        raise ValueError("CSV sospeso: controlla l’anteprima e le segnalazioni.")
    return {"files": [app.meta(dest)], "message": "Copia pronta nei Risultati."}
