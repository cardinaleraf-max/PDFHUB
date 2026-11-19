"""Prove di conversione su documenti generati localmente, anche tramite interfaccia."""
import argparse
import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from contextlib import contextmanager
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import pymupdf as pdf
from docx import Document
from pypdf import PdfReader
from desktop import Handler,ThreadingHTTPServer
from engine import TOOLS,convert
from formats import spreadsheet
from openxml_io import presentation


def cases():
    doc=pdf.open()
    for n in (1,2,3):
        page=doc.new_page(width=360,height=450)
        page.insert_text((24,45),f"Pagina {n} Prova PDFHub",fontsize=18)
        page.insert_text((24,75),"Riservato. Documento di esempio.")
    page=doc[0]
    for x in (30,130,230):
        page.draw_line((x,130),(x,210))
    for y in (130,170,210):
        page.draw_line((30,y),(230,y))
    for x,y,t in [(38,150,"Nome"),(140,150,"Valore"),(38,190,"Alfa"),(140,190,"42")]:
        page.insert_text((x,y),t)
    field=pdf.Widget()
    field.field_type=pdf.PDF_WIDGET_TYPE_TEXT
    field.field_name="Cliente"
    field.rect=pdf.Rect(50,300,200,330)
    page.add_widget(field)
    image=page.get_pixmap().tobytes("png")
    doc[2].insert_image(pdf.Rect(20,100,200,325),stream=image)
    data=doc.tobytes()
    normal=[("Test qualità.pdf",data)]
    locked=[("Protetto.pdf",doc.tobytes(encryption=pdf.PDF_ENCRYPT_AES_256,owner_pw="owner",user_pw="chiave"))]
    scan=pdf.open()
    scan.new_page(width=360,height=450).insert_image(page.rect,stream=image)
    word=Document();word.add_paragraph("Contenuto Word")
    stream=io.BytesIO();word.save(stream)
    alt=pdf.open();alt.new_page().insert_text((40,40),"Versione diversa")
    inputs={
        "merge":normal*2,"compare":normal+[("Versione.pdf",alt.tobytes())],
        "fromimg":[("Foto uno.png",image),("Foto due.jpg",page.get_pixmap().tobytes("jpeg"))],
        "wordin":[("Test.docx",stream.getvalue())],"excelin":[("Test.xlsx",spreadsheet(doc))],
        "pptin":[("Test.pptx",presentation(doc))],"html":[("Pagina.html",b"<h1>HTML locale</h1>")],
        "txtin":[("Test.txt","Testo UTF-8 città".encode())],"unlock":locked,
        "ocr":[("Scansione.pdf",scan.tobytes())],"scan":[]}
    options={"split":{"mode":"all"},"extract":{"pages":"2,1"},"order":{"pages":"3,1,2"},
             "remove":{"pages":"2"},"rotate":{"angle":"90"},"toimg":{"format":"jpg"},
             "compress":{"level":"normal"},"numbers":{"start":"17"},"watermark":{"caption":"Bozza"},
             "crop":{"margin":"3"},"edit":{"caption":"Nota","page":"2","x":"15","y":"40"},
             "sign":{"signature":"Ada Rossi","page":"3","x":"12","y":"80"},
             "forms":{"field":"Cliente","value":"Ada"},"newfield":{"field":"Nuovo","page":"1","x":"12","y":"80"},
             "protect":{"password":"segreta"},"unlock":{"source_password":"chiave"},"redact":{"needle":"Riservato"},
             "summary":{"method":"extractive"},"translate":{"language":"Italiano","model":"pdfhub-qa-missing"}}
    items=[(op,op,inputs.get(op,normal),options.get(op,{})) for op in TOOLS]
    items.extend([("split-range","split",normal,{"mode":"range","pages":"3,1-2"}),
                  ("rotate-180","rotate",normal,{"angle":"180"}),("rotate-270","rotate",normal,{"angle":"270"}),
                  ("toimg-png","toimg",normal,{"format":"png"}),("compress-strong","compress",normal,{"level":"strong"}),
                  ("summary-model","summary",normal,{"method":"model","model":"pdfhub-qa-missing"}),
                  ("text-protected","text",locked,{"source_password":"chiave"})])
    return items


def validate(label,op,source,opts,name,data):
    assert data, label
    if name.endswith(".pdf"):
        assert data.startswith(b"%PDF-"), (label,"file extension is .pdf but signature is missing")
        if op!="protect":
            reader=PdfReader(io.BytesIO(data))
            assert reader.pages
        with pdf.open(stream=data) as out:
            if op=="protect": assert out.needs_pass and not out.authenticate("errata") and out.authenticate("segreta") and len(out)==3
            text=" ".join(page.get_text() for page in out)
            if op in ("merge","fromimg","remove","extract","order","split","pdfa","pptin"):
                expected={"merge":6,"fromimg":2,"remove":2,"extract":2,"order":3,"split":3,"pdfa":3}
                if op in expected: assert len(out)==expected[op]
            if op in ("extract","order","split"):assert ("Pagina 2" if op=="extract" else "Pagina 3") in out[0].get_text()
            if op=="remove":assert "Pagina 2" not in text
            if op=="rotate":assert all(page.rotation==int(opts["angle"]) for page in out)
            if op=="compress":assert len(data)<len(source[0][1])
            if op=="crop":assert abs(out[0].rect.width-(360-6*72/25.4))<.02
            if op=="pdfa":
                assert 'pdfaid:part="2"' in out.get_xml_metadata() and "/OutputIntents" in reader.trailer["/Root"]
                assert all(len(p.get_images())==1 for p in out)
            if op=="unlock":assert not out.is_encrypted and "Pagina 1" in text
            if op=="redact":assert "Riservato" not in text and "Documento" in text
            if op=="repair":assert len(out)==3 and "Pagina 2" in text
            if op=="numbers":assert all(str(17+i) in page.get_text() for i,page in enumerate(out))
            if op=="watermark":assert all("Bozza" in page.get_text() for page in out)
            if op=="edit":assert "Nota" in out[1].get_text()
            if op=="sign":assert "Ada Rossi" in out[2].get_text()
            if op=="forms":assert any(w.field_value=="Ada" for w in out[0].widgets())
            if op=="newfield":assert any(w.field_name=="Nuovo" for w in out[0].widgets())
            if op=="ocr":assert "PDFHUB" in text.upper()
            for key,needle in [("wordin","Contenuto Word"),("excelin","Alfa"),("html","HTML locale"),("txtin","città"),("summary","Pagina")]:
                if op==key:assert needle in text,(op,text)
            if op=="pptin":assert any(page.get_images() for page in out)
    elif name.endswith(".docx"):assert any("Pagina 1" in p.text for p in Document(io.BytesIO(data)).paragraphs)
    elif name.endswith((".xlsx",".pptx",".zip")):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            assert not z.testzip()
            if op=="split":assert len(z.namelist())==3 and all(len(PdfReader(io.BytesIO(z.read(n))).pages)==1 for n in z.namelist())
            if op=="toimg":assert len(z.namelist())==3 and all(pdf.Pixmap(z.read(n)).width==720 for n in z.namelist())
            if op=="images":assert any(pdf.Pixmap(z.read(n)).width==360 for n in z.namelist())
            if op=="excelout":assert b"Alfa" in z.read("xl/worksheets/sheet1.xml")
            if op=="pptout":
                assert len(ET.fromstring(z.read("ppt/presentation.xml")).findall("./{*}sldIdLst/{*}sldId"))==3
                assert len([n for n in z.namelist() if n.startswith("ppt/media/")])==3
    elif op=="compare":assert b"Versione" in data and b"diff_" in data
    elif op in ("text","markdown"):assert b"Pagina 1" in data
    else:raise AssertionError(name)


def dependency_case(label):
    return label in ("scan","summary-model","translate")


def check_error(label,error):
    if label=="scan":assert "scanner" in error.lower(),error
    else:assert "ollama" in error.lower() or "modello" in error.lower(),error


def check_worker(items):
    with tempfile.TemporaryDirectory() as temp:
        folder=Path(temp)
        for label,op,source,opts in items:
            paths=[]
            for idx,(name,data) in enumerate(source):
                file=folder/(str(idx)+" "+name)
                file.write_bytes(data);paths.append(str(file))
            job=dict(op=op,options=opts,files=paths,output=str(folder/"result"))
            response=subprocess.run([sys.executable,"-B","-X","utf8",str(ROOT/"worker.py")],input=json.dumps(job).encode(),
                                    capture_output=True,check=True,timeout=320)
            result=json.loads(response.stdout)
            if "error" in result:
                assert dependency_case(label),(label,result)
                check_error(label,result["error"])
                print(label,"REQUISITO ASSENTE",flush=True)
            else:
                validate(label,op,source,opts,result["name"],(folder/"result").read_bytes())
                print(label,"OK",flush=True)


def check_browser(items):
    chrome=Path(os.environ["ProgramFiles"])/"Google/Chrome/Application/chrome.exe"
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp,ThreadingHTTPServer(("127.0.0.1",0),Handler) as server:
        folder=Path(tmp);profile=folder/"chrome";profile.mkdir()
        server.host=f"127.0.0.1:{server.server_port}";server.token="qa-session"
        threading.Thread(target=server.serve_forever,daemon=True).start()
        manifest=[]
        for label,op,source,opts in items:
            manifest.append(dict(label=label,op=op,options=opts,files=[dict(name=n,raw=base64.b64encode(b).decode()) for n,b in source]))
        (folder/"cases.json").write_text(json.dumps(manifest),"utf8")
        browser=subprocess.Popen([str(chrome),"--headless=new","--no-sandbox","--disable-gpu","--in-process-gpu",
            "--no-first-run","--remote-debugging-port=0","--user-data-dir="+str(profile),"http://"+server.host],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            devtools=profile/"DevToolsActivePort"
            for _ in range(150):
                if devtools.exists():break
                time.sleep(.1)
            port=devtools.read_text().splitlines()[0]
            subprocess.run(["node",str(ROOT/"tests/studio.mjs"),str(folder),port,server.host],check=True,timeout=450)
            for label,op,source,opts in items:
                result=json.loads((folder/(label+".json")).read_text("utf8"))
                if "error" in result:
                    assert dependency_case(label),(label,result)
                    check_error(label,result["error"])
                else:
                    validate(label,op,source,opts,result["name"],(folder/(label+".bin")).read_bytes())
        finally:
            browser.terminate();browser.wait();server.shutdown()


def check_native(items):
    framework=Path(os.environ["SystemRoot"])/"Microsoft.NET/Framework64/v4.0.30319"
    def output_extension(op,opts):
        return {"split":".zip" if opts.get("mode")=="all" else ".pdf","text":".txt","markdown":".md","images":".zip",
                "toimg":".zip","compare":".html","pptout":".pptx","excelout":".xlsx","wordout":".docx"}.get(op,".pdf")
    with tempfile.TemporaryDirectory() as temp:
        folder=Path(temp)
        for name in ("engine.py","formats.py","openxml_io.py","worker.py","windows-tools.ps1"):
            shutil.copy2(ROOT/name,folder/name)
        shutil.copytree(ROOT/"ui",folder/"ui")
        shutil.copytree(ROOT/"docs",folder/"docs")
        executable=folder/"NativeChecks.exe"
        references=["System.Windows.Forms","System.Web.Extensions","System.Xaml"]
        args=["/reference:"+n+".dll" for n in references]
        args.extend("/reference:"+str(framework/"WPF"/(n+".dll")) for n in ("WindowsBase","PresentationCore","PresentationFramework"))
        subprocess.run([str(framework/"csc.exe"),"/nologo","/target:exe","/main:NativeChecks","/out:"+str(executable),*args,
                        str(ROOT/"Launcher.cs"),str(ROOT/"QuickEditor.cs"),str(ROOT/"tests/NativeChecks.cs")],check=True)
        manifest=[]
        for label,op,source,opts in items:
            loc=folder/label;loc.mkdir()
            paths=[]
            for i,(name,data) in enumerate(source):
                f=loc/(str(i)+" "+name);f.write_bytes(data);paths.append(str(f))
            manifest.append(dict(label=label,op=op,files=paths,options=opts,target=str(loc/("output"+output_extension(op,opts)))))
        path=folder/"cases.json";path.write_text(json.dumps(manifest),"utf8")
        subprocess.run([str(executable),str(path)],check=True,timeout=450)
        for label,op,source,opts in items:
            dest=folder/label/("output"+output_extension(op,opts))
            if not dest.exists():
                error_file=dest.with_name(dest.name+".error")
                assert dependency_case(label),(label,error_file.read_text("utf8"))
                check_error(label,error_file.read_text("utf8"))
            else:
                validate(label,op,source,opts,dest.name,dest.read_bytes())


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--browser",action="store_true")
    parser.add_argument("--native",action="store_true")
    args=parser.parse_args()
    test_cases=cases()
    (check_native if args.native else check_browser if args.browser else check_worker)(test_cases)
    print(len(test_cases),"casi verificati",flush=True)

