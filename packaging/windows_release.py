"""Crea lo ZIP portatile dalla distribuzione CPython x64 usata per la build."""
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text().strip()


def build():
    if sys.platform != "win32" or platform.machine().lower() not in {"amd64","x86_64"} or sys.version_info[:2] != (3,12):
        raise SystemExit("Usa CPython 3.12 su Windows x64.")
    subprocess.run([sys.executable, str(ROOT / "build.py")], check=True)
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    archive = output / f"PDFHub-{VERSION}-Windows-x64.zip"
    with tempfile.TemporaryDirectory() as temp:
        app = Path(temp)/"PDFHub"
        runtime = app/"runtime"
        runtime.mkdir(parents=True)
        base = Path(sys.base_prefix)
        for name in ("python.exe","pythonw.exe","python3.dll","python312.dll","LICENSE.txt"):
            shutil.copy2(base/name, runtime/name)
        for dll in base.glob("vcruntime*.dll"):
            shutil.copy2(dll, runtime)
        shutil.copytree(base/"DLLs",runtime/"DLLs",ignore=shutil.ignore_patterns("*.pdb","*_test*.pyd"))
        shutil.copytree(base/"Lib",runtime/"Lib",ignore=shutil.ignore_patterns(
            "site-packages","__pycache__","test","tests","idlelib","ensurepip","tkinter","turtledemo"))
        site = runtime/"packages"
        for name in ("PyMuPDF","python-docx","typing_extensions","lxml"):
            package = metadata.distribution(name)
            for entry in package.files:
                if ".." in entry.parts or "__pycache__" in entry.parts or entry.name=="direct_url.json":
                    continue
                src = Path(package.locate_file(entry))
                if src.is_file():
                    target=site/entry
                    target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(src,target)
        (runtime/"python312._pth").write_text("Lib\nDLLs\npackages\n..\n",encoding="ascii")
        for name in ("PDFHub.exe","Installa icona desktop.cmd","PDFHub.pyw","desktop.py","engine.py",
                     "formats.py","openxml_io.py","worker.py","windows-tools.ps1","README.md","VERIFICHE.md",
                     "Launcher.cs","QuickEditor.cs","build.py","requirements.txt","VERSION"):
            shutil.copy2(ROOT/name,app/name)
        for folder in ("ui","docs"):
            shutil.copytree(ROOT/folder,app/folder)
        # Prova il runtime isolato prima di produrre l'archivio.
        subprocess.run([str(runtime/"python.exe"),"-B",str(ROOT/"tests/release_smoke.py"),str(app)],
                       cwd=app,check=True,env={**os.environ,"PYTHONPATH":"","PYTHONHOME":""})
        partial=archive.with_suffix(".tmp")
        with zipfile.ZipFile(partial,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as output_zip:
            for path in sorted(app.rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    output_zip.write(path,path.relative_to(app.parent))
        partial.replace(archive)
    print(archive)

if __name__=="__main__":
    build()
