import json
import os
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

from engine import CATALOG, convert
import pymupdf

UI = Path(__file__).resolve().parent / "ui"
ASSETS = {"/": ("index.html", "text/html; charset=utf-8"),
          "/style.css": ("style.css", "text/css"), "/app.js": ("app.js", "text/javascript"),
          "/icon.svg": ("icon.svg", "image/svg+xml")}


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, body, content_type, filename=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if filename:
            self.send_header("X-Filename", quote(filename, safe=""))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        asset = ASSETS.get(self.path)
        if not asset or self.headers.get("Host") != self.server.host:
            return self.send_error(404)
        body = (UI / asset[0]).read_bytes()
        if self.path == "/":
            body = body.replace(b"__SESSION__", self.server.token.encode())
            body = body.replace(b"__CATALOG__", json.dumps(CATALOG).encode())
        self.respond(200, body, asset[1])

    def do_POST(self):
        if (self.path not in ("/convert","/ready") or self.headers.get("Host") != self.server.host
                or self.headers.get("X-Session") != self.server.token):
            return self.send_error(403)
        if self.path == "/ready":
            if hasattr(self.server,"ready"):
                self.server.ready.set()
            return self.respond(200,b"","text/plain")
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 201 * 1024**2:
                raise ValueError("Scegli file fino a 200 MB complessivi.")
            mime = self.headers.get("Content-Type", "")
            body = self.rfile.read(length)
            message = BytesParser(policy=policy.default).parsebytes(
                b"Content-Type: " + mime.encode() + b"\r\n\r\n" + body)
            fields, files = {}, []
            for part in message.iter_parts():
                key = part.get_param("name", header="content-disposition")
                data = part.get_payload(decode=True)
                if key == "files":
                    files.append((part.get_filename() or "documento", data))
                else:
                    fields[key] = data.decode()
            name, output = convert(fields["operation"], files, json.loads(fields["options"]))
        except (pymupdf.FileDataError, RuntimeError, KeyError):
            return self.respond(400, "File illeggibile o non supportato.".encode(), "text/plain")
        except ValueError as error:
            return self.respond(400, str(error).encode(), "text/plain; charset=utf-8")
        except Exception:
            return self.respond(500, "Impossibile completare la conversione.".encode(), "text/plain")
        self.respond(200, output, "application/octet-stream", name)

    def log_message(self, *args):
        pass


def main():
    browsers = [Path(os.environ.get(root, "")) / path for path in
                ("Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe")
                for root in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    installed = [path for path in browsers if path.is_file()]
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        server.token = secrets.token_hex(24)
        server.ready = threading.Event()
        server.host = f"127.0.0.1:{server.server_port}"
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            for browser in installed:
                profile = tempfile.mkdtemp(prefix="pdfhub-")
                try:
                    command = [str(browser), "--app=http://" + server.host,
                        "--user-data-dir=" + profile, "--window-size=1420,940",
                        "--no-first-run", "--no-default-browser-check", "--disable-background-mode"]
                    server.ready.clear()
                    with subprocess.Popen(command) as window:
                        deadline=time.monotonic()+6
                        while window.poll() is None and time.monotonic()<deadline:
                            if server.ready.wait(.1):
                                window.wait()
                                return
                        if window.poll() is None:
                            window.terminate()
                        elif window.returncode==0:
                            return
                finally:
                    shutil.rmtree(profile, ignore_errors=True)
            # Il selettore nativo permette anche di caricare manualmente i file.
            subprocess.Popen([str(UI.parent/"PDFHub.exe"),"--manual"])
        finally:
            server.shutdown()


if __name__ == "__main__":
    main()
