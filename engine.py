"""Operazioni locali sui documenti per PDFHub."""
import io
import difflib
import html
import json
import tempfile
import secrets
import zipfile
from pathlib import Path
from contextlib import ExitStack

import pymupdf as pdf
import formats
from openxml_io import presentation

CATALOG = json.loads((Path(__file__).parent / "ui/catalog.json").read_text(encoding="utf-8"))
TOOLS = {t["id"]: t for group in CATALOG["groups"] for t in group["tools"]}


def need(options, key):
    value = str(options.get(key, "")).strip()
    if not value:
        raise ValueError("Completa il campo " + CATALOG["fields"][key][0] + ".")
    return value


def apply_tool(op, doc, documents, stem, options):
    name = stem + "-" + op + ".pdf"
    if op in ("extract","order","remove"):
        selected = pages(need(options,"pages"),len(doc))
        if op == "remove":
            excluded = set(selected)
            selected = [n for n in range(len(doc)) if n not in excluded]
            if not selected:
                raise ValueError("Il PDF deve conservare almeno una pagina.")
        doc.select(selected)
    elif op in ("unlock","repair"):
        return name, doc.tobytes(garbage=4,clean=True,deflate=True)
    elif op == "crop":
        inset = float(need(options,"margin")) * 72/25.4
        for page in doc:
            box = page.cropbox
            if not 0 < inset < min(box.width,box.height)/2:
                raise ValueError("Il margine supera lo spazio disponibile.")
            page.set_cropbox(box + (inset,inset,-inset,-inset))
    elif op in ("numbers","watermark"):
        for page in doc:
            bounds = page.rect * page.derotation_matrix
            if op == "numbers":
                text = str(int(need(options,"start")) + page.number)
                rect = pdf.Rect(bounds.x0,bounds.y1-min(32,bounds.height),bounds.x1,bounds.y1)
                size, opacity = 11, 1
            else:
                text = need(options,"caption")
                rect = pdf.Rect(bounds.x0,bounds.y0+bounds.height*.41,bounds.x1,bounds.y0+bounds.height*.65)
                size, opacity = 42, .28
            page.insert_htmlbox(rect, '<div style="text-align:center;font-size:'+str(size)+'pt">'+html.escape(text)+'</div>',opacity=opacity)
    elif op in ("edit","sign","newfield"):
        page_index = int(need(options,"page")) - 1
        if not 0 <= page_index < len(doc):
            raise ValueError(f"Scegli una pagina tra 1 e {len(doc)}.")
        page = doc[page_index]
        bounds = page.rect
        x,y = (float(need(options,k))*72/25.4 for k in ("x","y"))
        if not (0<=x<bounds.width-12 and 0<=y<bounds.height-12):
            raise ValueError("La posizione scelta è fuori dalla pagina.")
        rect = pdf.Rect(x,y,min(bounds.width,x+220),min(bounds.height,y+48)) * page.derotation_matrix
        if op == "newfield":
            field = pdf.Widget()
            field.field_name = need(options,"field")
            field.field_type = pdf.PDF_WIDGET_TYPE_TEXT
            field.rect = rect
            field.border_width = 1
            field.border_color = (.4,.4,.4)
            page.add_widget(field)
        else:
            text = html.escape(need(options,"signature" if op=="sign" else "caption"))
            style = "font:italic 22pt serif" if op=="sign" else "font:14pt sans-serif"
            page.insert_htmlbox(rect,f'<span style="{style}">{text}</span>')
    elif op == "forms":
        field_name = need(options,"field")
        present, changed = set(), False
        for page in doc:
            for field in page.widgets():
                if field.field_type == pdf.PDF_WIDGET_TYPE_TEXT:
                    present.add(field.field_name)
                    if field.field_name == field_name:
                        field.field_value = options.get("value","")
                        field.update()
                        changed = True
        if not changed:
            raise ValueError("Campi di testo disponibili: " + (", ".join(sorted(present)) or "nessuno"))
    elif op == "redact":
        hits = 0
        for page in doc:
            matches = page.search_for(need(options,"needle"))
            for rect in matches:
                page.add_redact_annot(rect,fill=(0,0,0))
            if matches:
                page.apply_redactions()
                hits += len(matches)
        if not hits:
            raise ValueError("Testo non trovato. Le scansioni richiedono una verifica visiva.")
    elif op == "compare":
        lines = ["\n".join(p.get_text(sort=True) for p in d).splitlines() for d in documents]
        if not all(any(s.strip() for s in group) for group in lines):
            raise ValueError("Per confrontare il testo delle scansioni esegui prima l’OCR.")
        report = difflib.HtmlDiff(wrapcolumn=76).make_file(*lines,fromdesc="Prima versione",todesc="Seconda versione")
        return stem+"-confronto.html",report.encode()
    elif op == "images":
        pictures = {}
        for page in doc:
            for image in page.get_images():
                xref = image[0]
                if xref and xref not in pictures:
                    item = doc.extract_image(xref)
                    if item:
                        pictures[xref] = (f'immagine-{xref}.{item["ext"]}',item["image"])
        if not pictures:
            raise ValueError("Nessuna immagine incorporata estraibile.")
        return stem+"-immagini.zip",packed(pictures.values())
    elif op == "wordout":
        return stem+".docx",formats.word_document(doc)
    elif op == "excelout":
        return stem+".xlsx",formats.spreadsheet(doc)
    elif op == "pdfa":
        return name,formats.archive_pdf(doc)
    elif op == "pptout":
        return stem+".pptx",presentation(doc)
    elif op == "ocr":
        return name,formats.ocr_document(doc)
    elif op == "markdown":
        output = []
        for page in doc:
            for block in page.get_text("dict",sort=True)["blocks"]:
                for line in block.get("lines",[]):
                    spans = line["spans"]
                    if spans:
                        size = max(s["size"] for s in spans)
                        prefix = "# " if size >= 20 else "## " if size >= 15 else ""
                        output.append(prefix+"".join(s["text"] for s in spans))
        if not output:
            raise ValueError("Nessun testo selezionabile.")
        return stem+".md","\n\n".join(output).encode()
    elif op in ("summary","translate"):
        source = "\n\n".join(p.get_text(sort=True) for p in doc)
        answer = formats.local_language(op,source,options)
        return name,formats.plain_pdf(answer)
    else:
        raise ValueError("Operazione sconosciuta.")
    return name,doc.tobytes(garbage=4,deflate=True)


def pages(spec, total):
    selected = []
    for part in spec.split(","):
        ends = part.strip().split("-")
        if len(ends) > 2 or any(not s.strip().isdigit() for s in ends):
            raise ValueError("Inserisci pagine o intervalli, ad esempio 1, 3-5.")
        start, end = int(ends[0]), int(ends[-1])
        if not 1 <= start <= end <= total:
            raise ValueError(f"Il documento contiene {total} pagine. Controlla l’intervallo.")
        selected.extend(range(start - 1, end))
    return selected


def packed(items):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in items:
            archive.writestr(name, data)
    return output.getvalue()


def convert(op, inputs, options):
    tool = TOOLS.get(op)
    if not tool or not tool["min"] <= len(inputs) <= tool["max"]:
        raise ValueError("Controlla il numero di file richiesto per questa operazione.")
    if sum(len(data) for _,data in inputs)>200*1024**2:
        raise ValueError("Limite di 200 MB per operazione.")
    if op == "scan":
        with tempfile.TemporaryDirectory(prefix="pdfhub-scan-") as tmp:
            formats.windows(op,Path(tmp))
            with pdf.open(stream=(Path(tmp)/"scan.img").read_bytes()) as scan:
                return "scansione.pdf",scan.convert_to_pdf()
    stem = Path(inputs[0][0]).stem[:100] or "documento"
    if op in ("wordin","excelin","pptin"):
        suffix,data=formats.office_input(op,*inputs[0])
        return stem+suffix,data
    if op in ("html","txtin"):
        source = inputs[0][1].decode("utf-8-sig")
        return stem+".pdf",(formats.html_pdf(source) if op=="html" else formats.plain_pdf(source))
    with ExitStack() as stack:
        result = stack.enter_context(pdf.open())
        documents = []
        for name, data in inputs:
            if not data:
                raise ValueError("Uno dei file è vuoto.")
            doc = stack.enter_context(pdf.open(stream=data))
            documents.append(doc)
            if op == "fromimg":
                if Path(name).suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"} or doc.is_pdf:
                    raise ValueError("Scegli immagini JPG, PNG, BMP o TIFF.")
                with pdf.open(stream=doc.convert_to_pdf()) as converted:
                    result.insert_pdf(converted)
                continue
            if not doc.is_pdf:
                raise ValueError("Questa operazione richiede un file PDF.")
            if doc.needs_pass and not doc.authenticate(options.get("source_password", "")):
                raise ValueError("Il PDF è protetto. Inserisci la password di apertura corretta.")
            if op == "merge":
                result.insert_pdf(doc)
        if op in ("merge", "fromimg"):
            return ("documenti-uniti.pdf" if op == "merge" else "immagini.pdf"), result.tobytes(deflate=True)
        if op == "split":
            if options.get("mode") == "all":
                def parts():
                    for i in range(len(doc)):
                        with pdf.open() as one:
                            one.insert_pdf(doc, from_page=i, to_page=i)
                            yield f"pagina-{i+1:04}.pdf", one.tobytes(deflate=True)
                return stem + "-pagine.zip", packed(parts())
            doc.select(pages(options.get("pages", ""), len(doc)))
            return stem + "-estratto.pdf", doc.tobytes(garbage=4, deflate=True)
        if op == "compress":
            if options.get("level") == "strong":
                doc.rewrite_images(dpi_threshold=150, dpi_target=120, quality=65)
            output = doc.tobytes(garbage=4, deflate=True, use_objstms=1)
            if len(output) >= len(inputs[0][1]):
                raise ValueError("Questo PDF è già ottimizzato per il livello scelto. La dimensione non si è ridotta.")
            return stem + "-compresso.pdf", output
        if op == "rotate":
            angle = int(options.get("angle", "90"))
            if angle not in (90, 180, 270):
                raise ValueError("Scegli una rotazione valida.")
            for page in doc:
                page.set_rotation((page.rotation + angle) % 360)
            return stem + "-ruotato.pdf", doc.tobytes(deflate=True)
        if op == "toimg":
            fmt = "jpeg" if options.get("format") == "jpg" else "png"
            def images():
                for page in doc:
                    yield f"pagina-{page.number+1:04}.{fmt}", page.get_pixmap(dpi=144).tobytes(fmt)
            return stem + "-immagini.zip", packed(images())
        if op == "text":
            content = "\n\n".join(page.get_text(sort=True) for page in doc)
            if not content.strip():
                raise ValueError("Il PDF non contiene testo selezionabile. Le scansioni richiedono OCR.")
            return stem + ".txt", content.encode("utf-8-sig")
        if op == "protect":
            password = options.get("password", "")
            if not password or len(password.encode()) > 40:
                raise ValueError("Scegli una password da 1 a 40 byte.")
            return stem + "-protetto.pdf", doc.tobytes(encryption=pdf.PDF_ENCRYPT_AES_256,
                owner_pw=secrets.token_hex(16), user_pw=password, deflate=True)
        return apply_tool(op,doc,documents,stem,options)
