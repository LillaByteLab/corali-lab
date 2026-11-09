"""Prepare the Windows file-conversion CLI in a checkout of the pinned Cedro release."""
from pathlib import Path
import subprocess
import sys

source = Path(sys.argv[1]).resolve()
revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
if revision != "02d01d33cc3e051510047d5ef7dbef658717ddcf":
    raise SystemExit("Revisione Cedro inattesa")
src = source / "src"
(src / "main.rs").write_text("mod cli;\nfn main() { std::process::exit(cli::run()); }\n", encoding="utf-8")
lib = (src / "lib.rs").read_text(encoding="utf-8")
for module in ("ui", "wheelgfx", "credits", "webvideo", "youtube"):
    lib = lib.replace("pub mod " + module + ";\n", "")
(src / "lib.rs").write_text(lib, encoding="utf-8")
cli = (src / "cli.rs").read_text(encoding="utf-8")
cli = cli.replace('        "update" => return update(),\n', '')
cli = cli[:cli.index("fn update()")] + 'fn print_help() { eprintln!("Coralì Lab: convert, slices, trascrivi"); }\n\n' + cli[cli.index("fn transcribe("):]
(src / "cli.rs").write_text(cli, encoding="utf-8")
