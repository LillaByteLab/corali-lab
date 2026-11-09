"""A single Cedro invocation for a queue, with per-source verified outputs."""

import shutil
import zipfile
import xml.etree.ElementTree as ET


class EngineCommandError(ValueError):
    def __init__(self, message, stdout="", stderr="", code=1):
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr
        self.code = code


def transcribe(app, paths, params, folder):
    app.require_cedro()
    app.prepare_native_engine()
    app.engine_settings(cpu=bool(params.get("cpu")))
    precision = ["veloce", "buona", "massima"][
        max(0, min(2, int(params.get("model", 1))))
    ]
    records = []
    for number, path in enumerate(paths):
        sub = folder / ("trascrizione-" + str(number + 1))
        sub.mkdir()
        copy = sub / path.name
        shutil.copy2(path, copy)
        records.append(
            {"source": path, "copy": copy, "folder": sub, "ok": False, "error": ""}
        )

    def invoke(selected, cpu):
        args = [
            app.cedro,
            "trascrivi",
            *[r["copy"] for r in selected],
            "--precisione",
            precision,
        ]
        if cpu:
            args.append("--cpu")
        app.progress = {
            "label": f"Trascrizione di {len(selected)} file con Cedro",
            "percent": -1,
        }
        error = None
        try:
            app.command(args)
        except ValueError as failure:
            if app.cancel.is_set():
                raise
            error = failure
        for record in selected:
            generated = [
                p
                for p in record["folder"].rglob("*")
                if p.is_file()
                and p != record["copy"]
                and p.suffix.lower() in (".docx", ".txt")
            ]
            confirmed = error is None or any(
                line.startswith("OK " + str(record["copy"]) + " -> ")
                for line in getattr(error, "stdout", "").splitlines()
            )
            record["ok"] = bool(generated) and confirmed
            record["files"] = generated if record["ok"] else []
            record["error"] = (
                ""
                if record["ok"]
                else (
                    str(error)[-1000:]
                    if error
                    else "Il motore non ha prodotto una trascrizione."
                )
            )
        return error

    error = invoke(records, bool(params.get("cpu")))
    pending = [r for r in records if not r["ok"]]
    if (
        pending
        and error
        and not params.get("cpu")
        and any(
            word in str(error).lower()
            for word in ("chiuso", "vulkan", "gpu", "memoria")
        )
    ):
        # Clear only generated partials before retrying incomplete items on CPU.
        for record in pending:
            for p in record["folder"].rglob("*"):
                if p.is_file() and p != record["copy"]:
                    p.unlink()
        app.engine_settings(cpu=True)
        invoke(pending, True)
    outputs = []
    items = []
    for record in records:
        if app.cancel.is_set():
            raise ValueError(
                "Trascrizione annullata. Nessun risultato incompleto pubblicato."
            )
        try:
            if not record["ok"]:
                raise ValueError(record["error"])
            for file in list(record["files"]):
                if not file.stat().st_size:
                    raise ValueError("Trascrizione vuota.")
                if file.suffix.lower() == ".docx":
                    with zipfile.ZipFile(file) as z:
                        if z.testzip():
                            raise ValueError("Documento di trascrizione incompleto.")
                        tree = ET.fromstring(z.read("word/document.xml"))
                    lines = [
                        "".join(n.itertext())
                        for n in tree.iter(
                            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"
                        )
                    ]
                    txt = file.with_suffix(".txt")
                    txt.write_text("\n".join(lines), encoding="utf-8-sig")
                    if txt not in record["files"]:
                        record["files"].append(txt)
            record["copy"].unlink()
            outputs.extend(record["files"])
            items.append({"name": record["source"].name, "ok": True})
        except (
            ValueError,
            OSError,
            zipfile.BadZipFile,
            ET.ParseError,
            KeyError,
        ) as failure:
            shutil.rmtree(record["folder"], ignore_errors=True)
            items.append(
                {"name": record["source"].name, "ok": False, "error": str(failure)}
            )
    app.transcript_items = items
    if not outputs:
        raise ValueError(
            "Nessuna trascrizione completata. "
            + (items[0]["error"] if items else "Scegli almeno un file.")
        )
    return outputs
