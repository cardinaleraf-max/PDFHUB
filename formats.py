"""Adattatori per i formati Office, l'OCR di Windows e i modelli locali."""
import html
import http.client
import io
import json
import subprocess
import tempfile
import zipfile
import os
import re
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import pymupdf as pdf
from docx import Document
from docx.shared import Inches, Pt
from openxml_io import office_html


def windows(task, directory):
    if os.name != "nt":
        raise ValueError("Questa operazione richiede un componente specifico di Windows.")
    script = Path(__file__).with_name("windows-tools.ps1")
    try:
        process = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-STA",
                                  "-ExecutionPolicy", "RemoteSigned",
                                  "-File", str(script), task, str(directory)],
                                 capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
                                 timeout=300)
    except subprocess.TimeoutExpired:
        raise ValueError("Il componente Windows non ha risposto entro cinque minuti.")
    if process.returncode:
        detail = process.stderr.decode("utf-8", "replace").strip()
        raise ValueError(detail or "Il componente Windows richiesto non è disponibile.")


def office_input(op, name, data):
    suffix = {"wordin": ".docx", "excelin": ".xlsx", "pptin": ".pptx"}[op]
    if Path(name).suffix.lower() != suffix or not zipfile.is_zipfile(io.BytesIO(data)):
        raise ValueError("Seleziona un documento " + suffix.upper() + " valido.")
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        for part in package.namelist():
            if any(mark in part.lower() for mark in ("vbaproject", "/embeddings/", "/activex/", "/externallinks/", "/connections.xml")):
                raise ValueError("Per la conversione usa una copia priva di oggetti attivi o collegamenti dati.")
            if part.endswith(".rels"):
                for rel in ET.fromstring(package.read(part)):
                    if rel.get("TargetMode") == "External" and not rel.get("Type","").endswith("/hyperlink"):
                        raise ValueError("Il documento usa risorse esterne. Incorporale prima di convertirlo.")
    with tempfile.TemporaryDirectory(prefix="pdfhub-office-") as tmp:
        folder = Path(tmp)
        (folder / ("input" + suffix)).write_bytes(data)
        try:
            windows(op, folder)
        except ValueError:
            return "-contenuto.pdf",html_pdf(office_html(op,data))
        return ".pdf",(folder / "output.pdf").read_bytes()


def archive_pdf(doc):
    profile = Path(__file__).parent / "docs/sRGB.icc"
    if not profile.is_file():
        raise ValueError("Profilo colore sRGB PDF/A non disponibile.")
    with pdf.open() as out:
        for page in doc:
            dest = out.new_page(width=page.rect.width,height=page.rect.height)
            dest.insert_image(dest.rect,pixmap=page.get_pixmap(dpi=144,colorspace=pdf.csRGB,alpha=False))
        icc=out.get_new_xref()
        out.update_object(icc,"<< /N 3 >>")
        out.update_stream(icc,profile.read_bytes())
        intent=out.get_new_xref()
        out.update_object(intent,f"<< /Type /OutputIntent /S /GTS_PDFA1 /OutputConditionIdentifier (sRGB IEC61966-2.1) /DestOutputProfile {icc} 0 R >>")
        out.xref_set_key(out.pdf_catalog(),"OutputIntents",f"[{intent} 0 R]")
        out.set_xml_metadata('<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about="" xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/" pdfaid:part="2" pdfaid:conformance="B"/></rdf:RDF></x:xmpmeta>')
        return out.tobytes(garbage=4,deflate=True)


def html_pdf(markup):
    story = pdf.Story(html=markup)
    paper = pdf.paper_rect("a4")
    area = paper + (40, 40, -40, -40)
    with story.write_with_links(lambda n, previous: (paper, area, None)) as out:
        return out.tobytes(deflate=True)


def plain_pdf(text):
    return html_pdf("<p>" + html.escape(text).replace("\n","<br>") + "</p>")


def word_document(doc):
    word = Document()
    for number, page in enumerate(doc):
        if number:
            word.add_page_break()
        for block in page.get_text("dict", sort=True)["blocks"]:
            if block["type"] == 1:
                # Converti anche JPEG2000 e immagini CMYK in PNG compatibile con Word.
                pix = pdf.Pixmap(block["image"])
                if pix.colorspace and pix.colorspace.n > 3:
                    pix = pdf.Pixmap(pdf.csRGB, pix)
                word.add_picture(io.BytesIO(pix.tobytes("png")), width=Inches(min(6, block["width"]/96)))
            else:
                for line in block.get("lines", []):
                    paragraph = word.add_paragraph()
                    for span in line["spans"]:
                        run = paragraph.add_run(span["text"])
                        run.bold = bool(span["flags"] & 16)
                        run.italic = bool(span["flags"] & 2)
                        run.font.size = Pt(max(1,min(160,span["size"])))
    out = io.BytesIO()
    word.save(out)
    return out.getvalue()


def spreadsheet(doc):
    rows = []
    for page in doc:
        for table in page.find_tables().tables:
            rows.extend(table.extract())
            rows.append([])
    if not rows:
        raise ValueError("Nessuna tabella riconosciuta. Per le scansioni esegui prima l’OCR.")
    xml = ET.Element("worksheet", xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main")
    sheet = ET.SubElement(xml, "sheetData")
    for values in rows:
        row = ET.SubElement(sheet, "row")
        for value in values:
            cell = ET.SubElement(row, "c", t="inlineStr")
            ET.SubElement(ET.SubElement(cell, "is"), "t").text = str(value or "")
    output = io.BytesIO()
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    def relationship(kind, path):
        return f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{rel_ns}/{kind}" Target="{path}"/></Relationships>'
    with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr("_rels/.rels", relationship("officeDocument","xl/workbook.xml"))
        z.writestr("xl/workbook.xml", f'<workbook xmlns="{xml.attrib["xmlns"]}" xmlns:r="{rel_ns}"><sheets><sheet name="Tabelle" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",relationship("worksheet","worksheets/sheet1.xml"))
        z.writestr("xl/worksheets/sheet1.xml",ET.tostring(xml,encoding="utf-8"))
    return output.getvalue()


def ocr_document(doc):
    with tempfile.TemporaryDirectory(prefix="pdfhub-pages-") as tmp:
        folder = Path(tmp)
        for page in doc:
            if page.get_text().strip():
                continue
            scale = min(2.5, 2400 / max(page.rect.width, page.rect.height))
            pix = page.get_pixmap(matrix=pdf.Matrix(scale,scale))
            pix.save(folder / f"{page.number:07}.png")
        if not any(folder.glob("*.png")):
            raise ValueError("Le pagine contengono già testo selezionabile.")
        windows("ocr", folder)
        recognized = 0
        for path in folder.glob("*.json"):
            page = doc[int(path.stem)]
            info = json.loads(path.read_text(encoding="utf-8-sig"))
            scale = info["width"] / page.rect.width
            for word in info["words"]:
                box = pdf.Rect(word["x"], word["y"], word["x"]+word["w"], word["y"]+word["h"]) / scale
                rect = box * page.derotation_matrix
                # Il testo invisibile segue la posizione delle parole riconosciute.
                page.insert_text(rect.bl + (0,-1),word["text"],fontsize=max(1,rect.height*.76),render_mode=3)
                recognized += 1
        if not recognized:
            raise ValueError("L’OCR non ha riconosciuto parole nelle scansioni.")
        return doc.tobytes(deflate=True)


def local_language(op, content, options):
    if op=="summary" and options.get("method","extractive")=="extractive":
        sentences=[line.strip() for line in re.split(r"(?<=[.!?])\s+|\n+",content) if line.strip()]
        if not sentences:
            raise ValueError("Per riassumere una scansione esegui prima l’OCR.")
        words=[re.findall(r"\b\w{4,}\b",s.lower()) for s in sentences]
        freq=Counter(w for line in words for w in set(line))
        scores=[sum(freq[w] for w in set(line))/max(1,len(line))**.65 for line in words]
        count=min(12,max(1,(len(sentences)+3)//4))
        best=sorted(range(len(sentences)),key=lambda i:scores[i],reverse=True)[:count]
        return "\n\n".join(sentences[i] for i in sorted(best))
    model = options.get("model","").strip()
    if not model or not content.strip():
        raise ValueError("Servono un modello locale e un PDF con testo selezionabile.")
    def post(route, payload):
        conn = http.client.HTTPConnection("127.0.0.1",11434,timeout=240)
        try:
            conn.request("POST",route,json.dumps(payload),{"Content-Type":"application/json"})
            response = conn.getresponse()
            body = json.loads(response.read())
            if response.status != 200:
                raise ValueError("Modello locale non disponibile. Controlla il nome in Ollama.")
            return body
        except OSError:
            raise ValueError("Avvia Ollama con un modello installato sul PC per usare questo strumento.")
        finally:
            conn.close()
    info = post("/api/show",{"model":model})
    if info.get("remote_model") or info.get("remote_host") or model.endswith(":cloud"):
        raise ValueError("Seleziona un modello scaricato sul dispositivo.")
    system = ("Riassumi in italiano il testo fornito." if op=="summary" else
              "Traduci il testo fornito in " + options.get("language","Italiano") + ". Restituisci solo la traduzione.")
    blocks = []
    while content:
        cut = len(content) if len(content)<=9000 else max(content.rfind(" ",4500,9000),4500)
        part, content = content[:cut], content[cut:]
        answer = post("/api/generate",{"model":model,"system":system,"prompt":part,"stream":False})
        blocks.append(answer["response"].strip())
    return "\n\n".join(blocks)

