import http.client
import io
import json
import struct
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest
from check_suite import cases, convert, pdf


@pytest.fixture(scope="module")
def sample():
    return next(source for _,op,source,_ in cases() if op=="rotate")


@pytest.mark.parametrize("op,opts,fragment",[
    ("extract",{"pages":"0"},"3 pagine"),("extract",{"pages":"1-8"},"3 pagine"),
    ("order",{"pages":"b"},"intervalli"),("remove",{"pages":"1-3"},"conservare"),
    ("crop",{"margin":"200"},"margine"),("crop",{"margin":"-1"},"margine"),
    ("rotate",{"angle":"10"},"rotazione"),("edit",{"page":"4"},"pagina"),
    ("edit",{"page":"1","x":"900","y":"0"},"posizione"),("protect",{"password":""},"password"),
    ("forms",{"field":"Inesistente","value":"X"},"Cliente"),("redact",{"needle":"Assente"},"trovato"),
    ("merge",{},"numero"),("compare",{},"numero")])
def test_invalid_options(sample,op,opts,fragment):
    with pytest.raises(ValueError,match=fragment):
        convert(op,sample,opts)


def test_repair_damaged_xref(sample):
    data=sample[0][1]
    broken=data[:data.rfind(b"startxref")]
    with pdf.open(stream=broken) as damaged:
        assert damaged.is_repaired
    _,fixed=convert("repair",[("rotto.pdf",broken)],{})
    with pdf.open(stream=fixed) as out:
        assert not out.is_repaired and len(out)==3 and "Pagina 3" in out[-1].get_text()


def test_scan_adapter(sample):
    # Simula il confine hardware: il driver consegna un'immagine come farebbe WIA.
    with pdf.open(stream=sample[0][1]) as doc:
        raw=doc[0].get_pixmap().tobytes("png")
    def capture(op,folder):
        assert op=="scan"
        (folder/"scan.img").write_bytes(raw)
    with patch("formats.windows",side_effect=capture):
        _,data=convert("scan",[],{})
    with pdf.open(stream=data) as doc:
        assert len(doc)==1 and doc[0].get_images()


def test_language_adapter(sample):
    received=[]
    class LocalModel(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            data=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append(data)
            payload={"details":{}} if self.path=="/api/show" else {"response":"Risposta del modello di prova."}
            body=json.dumps(payload).encode()
            self.send_response(200);self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
    connection=http.client.HTTPConnection
    with ThreadingHTTPServer(("127.0.0.1",0),LocalModel) as server:
        threading.Thread(target=server.serve_forever,daemon=True).start()
        def local(host,port,timeout):
            assert (host,port)==("127.0.0.1",11434)
            return connection(host,server.server_port,timeout=timeout)
        try:
            with patch("formats.http.client.HTTPConnection",side_effect=local):
                for op in ("summary","translate"):
                    _,raw=convert(op,sample,{"method":"model","model":"modello-test","language":"Francese"})
                    with pdf.open(stream=raw) as doc:
                        assert "Risposta del modello" in doc[0].get_text()
            assert len(received)==4 and "Francese" in received[-1]["system"] and "Pagina 3" in received[-1]["prompt"]
        finally:server.shutdown()


def test_password_errors(sample):
    _,locked=convert("protect",sample,{"password":"nota"})
    with pytest.raises(ValueError,match="password"):
        convert("unlock",[("locked.pdf",locked)],{"source_password":"errata"})
    _,out=convert("unlock",[("locked.pdf",locked)],{"source_password":"nota"})
    with pdf.open(stream=out) as doc:
        assert not doc.needs_pass and len(doc)==3


def test_image_formats():
    # Un pixel rosso in BMP e un pixel in scala di grigi in TIFF non compresso.
    bmp=struct.pack("<2sIHHI",b"BM",58,0,0,54)+struct.pack("<IiiHHIIiiII",40,1,1,1,24,0,4,0,0,0,0)+b"\0\0\xff\0"
    rows=[(256,4,1),(257,4,1),(258,3,8),(259,3,1),(262,3,1),(273,4,110),(278,4,1),(279,4,1)]
    tif=b"II"+struct.pack("<HIH",42,8,len(rows))+b"".join(struct.pack("<HHII",k,t,1,v) for k,t,v in rows)+bytes(4)+bytes([128])
    for ext,data in [("bmp",bmp),("tif",tif),("tiff",tif)]:
        _,result=convert("fromimg",[("test."+ext,data)],{})
        with pdf.open(stream=result) as doc:
            assert len(doc)==1 and doc[0].get_images()
