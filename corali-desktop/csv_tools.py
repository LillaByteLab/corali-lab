"""CSV editing without automatic conversion of dates, identifiers or formulas."""

import codecs
import csv
import hashlib
import io
from pathlib import Path


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class CsvSession:
    def __init__(self, path, delimiter=None):
        self.path = Path(path)
        raw = self.path.read_bytes()
        if len(raw) > 50 * 1024 * 1024:
            raise ValueError("Questa versione apre CSV fino a 50 MB.")
        self.original_hash = hashlib.sha256(raw).hexdigest()
        self.encoding = (
            "utf-16"
            if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE))
            else "utf-8-sig" if raw.startswith(codecs.BOM_UTF8) else "utf-8"
        )
        try:
            text = raw.decode(self.encoding)
        except UnicodeDecodeError:
            self.encoding = "cp1252"
            text = raw.decode("cp1252")
        self.newline = "\r\n" if "\r\n" in text else "\n"
        if delimiter is None:
            try:
                delimiter = (
                    csv.Sniffer().sniff(text[:65536], delimiters=",;\t|").delimiter
                )
            except csv.Error:
                delimiter = (
                    ";"
                    if text.partition("\n")[0].count(";")
                    > text.partition("\n")[0].count(",")
                    else ","
                )
        if delimiter not in (",", ";", "\t", "|"):
            raise ValueError("Separatore CSV non valido.")
        self.delimiter = delimiter
        self.rows = list(
            csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
        )
        self.columns = max((len(row) for row in self.rows), default=1)
        if len(self.rows) > 100000 or self.columns > 500:
            raise ValueError("CSV troppo grande: limite 100.000 righe e 500 colonne.")
        self.dirty = False

    def view(self, start=0):
        start = max(0, min(int(start), max(0, len(self.rows) - 1)))
        return {
            "name": self.path.name,
            "delimiter": self.delimiter,
            "encoding": self.encoding,
            "count": len(self.rows),
            "columns": self.columns,
            "start": start,
            "rows": self.rows[start : start + 50],
            "dirty": self.dirty,
        }

    def apply(self, changes):
        pending = []
        for change in changes:
            row, column = change.get("row"), change.get("column")
            value = change.get("value")
            if (
                type(row) != int
                or type(column) != int
                or not 0 <= row < len(self.rows)
                or not 0 <= column < self.columns
                or not isinstance(value, str)
                or len(value) > 65536
            ):
                raise ValueError("Modifica CSV non valida.")
            pending.append((row, column, value))
        for row, column, value in pending:
            self.rows[row].extend([""] * max(0, column + 1 - len(self.rows[row])))
            self.rows[row][column] = value
        self.dirty |= bool(pending)

    def add(self, what):
        if what == "row" and len(self.rows) < 100000:
            self.rows.append([""] * self.columns)
        elif what == "column" and self.columns < 500:
            for row in self.rows:
                row.extend([""] * max(0, self.columns + 1 - len(row)))
            self.columns += 1
        else:
            raise ValueError("È stato raggiunto il limite del CSV.")
        self.dirty = True

    def save(self, destination, encoding=None):
        if digest(self.path) != self.original_hash:
            raise ValueError("La sorgente è cambiata: apri nuovamente il CSV.")
        encoding = encoding or self.encoding
        if encoding not in ("utf-8", "utf-8-sig", "cp1252", "utf-16"):
            raise ValueError("Codifica non supportata.")
        buffer = io.StringIO(newline="")
        writer = csv.writer(
            buffer, delimiter=self.delimiter, lineterminator=self.newline
        )
        writer.writerows(self.rows)
        try:
            raw = buffer.getvalue().encode(encoding)
        except UnicodeEncodeError:
            raise ValueError(
                "Alcuni caratteri richiedono UTF-8. Cambia la codifica di salvataggio."
            )
        check = list(
            csv.reader(
                io.StringIO(raw.decode(encoding), newline=""),
                delimiter=self.delimiter,
                strict=True,
            )
        )
        if check != self.rows:
            raise ValueError("Il controllo della copia CSV non è riuscito.")
        Path(destination).write_bytes(raw)
        self.dirty = False
