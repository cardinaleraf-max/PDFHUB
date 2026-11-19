"""Prova il worker distribuito, inclusi i nomi di file Unicode e i modelli DOCX."""
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf
from docx import Document


def main():
    app=Path(sys.argv[1]).resolve()
    if sys.platform=="win32":
        runtime=app/"runtime"
        assert Path(pymupdf.__file__).is_relative_to(runtime)
        assert Path(sys.executable).is_relative_to(runtime)
        command=[str(runtime/"python.exe"),"-B","-X","utf8",str(app/"worker.py")]
    else:
        command=[str(app/"Contents/Helpers/engine/engine")]
    with tempfile.TemporaryDirectory() as tmp:
        source=Path(tmp)/"Documento città.pdf"
        target=Path(tmp)/"output"
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((40,50),"PDFHub release")
            pdf.save(source)
        for op in ("text","wordout","pdfa"):
            job={"op":op,"files":[str(source)],"options":{},"output":str(target)}
            result=subprocess.run(command,input=json.dumps(job).encode(),capture_output=True,timeout=90,check=True)
            record=json.loads(result.stdout)
            assert "name" in record,record
            if op=="text":
                assert "PDFHub release" in target.read_text(encoding="utf-8-sig")
            elif op=="wordout":
                assert any("PDFHub release" in p.text for p in Document(io.BytesIO(target.read_bytes())).paragraphs)
            else:
                with pymupdf.open(target) as pdf:
                    assert len(pdf)==1 and "pdfaid:part" in pdf.get_xml_metadata()
    print("Worker distribuito verificato: TXT, DOCX, PDF/A.")

if __name__=="__main__":
    main()
