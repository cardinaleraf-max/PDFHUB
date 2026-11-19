import subprocess
import sys
import tempfile
from pathlib import Path
import pymupdf

svg, destination = map(Path, sys.argv[1:])
with tempfile.TemporaryDirectory() as temp:
    iconset=Path(temp)/"PDFHub.iconset"
    iconset.mkdir()
    with pymupdf.open(svg) as source:
        for size in (16,32,64,128,256,512):
            for scale in (1,2):
                n=size*scale
                name=f"icon_{size}x{size}{'@2x' if scale==2 else ''}.png"
                image=source[0].get_pixmap(matrix=pymupdf.Matrix(n/256,n/256),alpha=True).tobytes("png")
                (iconset/name).write_bytes(image)
    subprocess.run(["iconutil","-c","icns",str(iconset),"-o",str(destination)],check=True)
