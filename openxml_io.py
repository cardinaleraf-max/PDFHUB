"""Conversioni OOXML locali quando le applicazioni Office non sono disponibili."""
import base64
import html
import io
import posixpath
import re
import zipfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import quoteattr

import pymupdf as pdf
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

D = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
Z = "http://schemas.openxmlformats.org/package/2006/relationships"


def image_html(raw):
    try:
        pix = pdf.Pixmap(raw)
        if pix.colorspace and pix.colorspace.n > 3:
            pix = pdf.Pixmap(pdf.csRGB,pix)
        encoded = base64.b64encode(pix.tobytes("png")).decode()
        return f'<img width="{min(460,pix.width)}" src="data:image/png;base64,{encoded}">'
    except (RuntimeError,ValueError):
        return ""


def table_html(rows):
    return "<table border='1'>"+ "".join("<tr>"+"".join("<td>"+html.escape(str(cell))+"</td>" for cell in row)+"</tr>" for row in rows)+"</table>"


def rels(package, part):
    folder,name=posixpath.split(part)
    path=posixpath.join(folder,"_rels",name+".rels")
    if path not in package.namelist():
        return {}
    return {r.get("Id"):posixpath.normpath(posixpath.join(folder,r.get("Target"))).lstrip("/")
            for r in ET.fromstring(package.read(path)) if r.get("TargetMode")!="External"}


def office_html(op, data):
    chunks=[]
    if op=="wordin":
        doc=Document(io.BytesIO(data))
        for block in doc.element.body:
            if block.tag.endswith("}p"):
                paragraph=Paragraph(block,doc)
                chunks.append("<p>"+html.escape(paragraph.text)+"</p>")
                for image in block.iter("{"+D+"}blip"):
                    part=doc.part.related_parts.get(image.get("{"+R+"}embed"))
                    if part:
                        chunks.append(image_html(part.blob))
            elif block.tag.endswith("}tbl"):
                chunks.append(table_html([[cell.text for cell in row.cells] for row in Table(block,doc).rows]))
    else:
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            if op=="pptin":
                part="ppt/presentation.xml"
                slides=ET.fromstring(package.read(part)).findall("./{*}sldIdLst/{*}sldId")
                paths=rels(package,part)
                for number,slide in enumerate(slides,1):
                    path=paths[slide.get("{"+R+"}id")]
                    refs=rels(package,path)
                    chunks.append(f"<h2>Diapositiva {number}</h2>")
                    for el in ET.fromstring(package.read(path)).iter():
                        if el.tag=="{"+D+"}p":
                            text="".join(t.text or "" for t in el.iter("{"+D+"}t"))
                            chunks.append("<p>"+html.escape(text)+"</p>")
                        elif el.tag=="{"+D+"}blip":
                            img=refs.get(el.get("{"+R+"}embed"))
                            if img:
                                chunks.append(image_html(package.read(img)))
            else:
                part="xl/workbook.xml"
                paths=rels(package,part)
                texts=[]
                if "xl/sharedStrings.xml" in package.namelist():
                    texts=["".join(t.text or "" for t in item.iter("{"+S+"}t")) for item in ET.fromstring(package.read("xl/sharedStrings.xml"))]
                for sheet in ET.fromstring(package.read(part)).findall("./{*}sheets/{*}sheet"):
                    chunks.append("<h2>"+html.escape(sheet.get("name",""))+"</h2>")
                    rows=[]
                    for row in ET.fromstring(package.read(paths[sheet.get("{"+R+"}id")])).findall("./{*}sheetData/{*}row"):
                        values=[]
                        for cell in row.findall("{*}c"):
                            value=cell.findtext("{*}v","")
                            if cell.get("t")=="s":
                                value=texts[int(value)]
                            elif cell.get("t")=="inlineStr":
                                value="".join(t.text or "" for t in cell.findall(".//{*}t"))
                            ref=re.match(r"[A-Z]+",cell.get("r",""))
                            if ref:
                                column=0
                                for letter in ref[0]:
                                    column=column*26+ord(letter)-64
                                values.extend([""]*max(0,min(256,column-1)-len(values)))
                            values.append(value)
                        rows.append(values)
                    chunks.append(table_html(rows))
    return "".join(chunks)


def relationship(entries):
    root=ET.Element("Relationships",xmlns=Z)
    for i,(kind,target) in enumerate(entries,1):
        ET.SubElement(root,"Relationship",Id=f"rId{i}",Type=R+"/"+kind,Target=target)
    return ET.tostring(root,encoding="utf-8")


def presentation(doc):
    output=io.BytesIO()
    group='<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
    ns=f'xmlns:p="{P}" xmlns:a="{D}" xmlns:r="{R}"'
    colors='accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" bg1="lt1" bg2="lt2" tx1="dk1" tx2="dk2" hlink="hlink" folHlink="folHlink"'
    width=9144000
    height=max(914400,min(51206400,round(width*doc[0].rect.height/doc[0].rect.width)))
    overrides={}
    with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as z:
        def part(name,kind,body):
            overrides[name]=kind
            z.writestr(name,body)
        z.writestr("_rels/.rels",relationship([("officeDocument","ppt/presentation.xml")]))
        local=io.BytesIO()
        Document().save(local)
        with zipfile.ZipFile(local) as template:
            part("ppt/theme/theme1.xml","application/vnd.openxmlformats-officedocument.theme+xml",template.read("word/theme/theme1.xml"))
        prefix="application/vnd.openxmlformats-officedocument.presentationml."
        blank=f'<p:spTree>{group}</p:spTree>'
        part("ppt/slideMasters/slideMaster1.xml",prefix+"slideMaster+xml",f'<p:sldMaster {ns}><p:cSld>{blank}</p:cSld><p:clrMap {colors}/><p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst><p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>')
        z.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels",relationship([("slideLayout","../slideLayouts/slideLayout1.xml"),("theme","../theme/theme1.xml")]))
        part("ppt/slideLayouts/slideLayout1.xml",prefix+"slideLayout+xml",f'<p:sldLayout {ns} type="blank" preserve="1"><p:cSld name="Blank">{blank}</p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>')
        z.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels",relationship([("slideMaster","../slideMasters/slideMaster1.xml")]))
        ids=[]
        slides=[("slideMaster","slideMasters/slideMaster1.xml")]
        for page in doc:
            n=page.number+1
            scale=min(width/page.rect.width,height/page.rect.height)
            w,h=round(scale*page.rect.width),round(scale*page.rect.height)
            z.writestr(f"ppt/media/page{n}.png",page.get_pixmap(dpi=144).tobytes("png"))
            pic=f'<p:pic><p:nvPicPr><p:cNvPr id="2" name="Pagina {n}"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="rId2"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr><a:xfrm><a:off x="{(width-w)//2}" y="{(height-h)//2}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>'
            part(f"ppt/slides/slide{n}.xml",prefix+"slide+xml",f'<p:sld {ns}><p:cSld><p:spTree>{group}{pic}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>')
            z.writestr(f"ppt/slides/_rels/slide{n}.xml.rels",relationship([("slideLayout","../slideLayouts/slideLayout1.xml"),("image",f"../media/page{n}.png")]))
            ids.append(f'<p:sldId id="{255+n}" r:id="rId{n+1}"/>')
            slides.append(("slide",f"slides/slide{n}.xml"))
        part("ppt/presentation.xml",prefix+"presentation.main+xml",f'<p:presentation {ns}><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst><p:sldIdLst>{"".join(ids)}</p:sldIdLst><p:sldSz cx="{width}" cy="{height}"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>')
        z.writestr("ppt/_rels/presentation.xml.rels",relationship(slides))
        types=''.join(f'<Override PartName="/{n}" ContentType={quoteattr(t)}/>' for n,t in overrides.items())
        z.writestr("[Content_Types].xml",'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="png" ContentType="image/png"/>'+types+'</Types>')
    return output.getvalue()
