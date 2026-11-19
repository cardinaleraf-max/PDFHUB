"""Rigenera l'icona Windows e compila il launcher WPF con .NET Framework."""
import os
import struct
import subprocess
from pathlib import Path
import pymupdf

root=Path(__file__).resolve().parent
sizes=(16,24,32,48,64,128,256)
with pymupdf.open(root/"ui/icon.svg") as source:
    images=[source[0].get_pixmap(matrix=pymupdf.Matrix(n/256,n/256),alpha=True).tobytes("png") for n in sizes]
offset=6+16*len(images)
entries=[]
for size,image in zip(sizes,images):
    entries.append(struct.pack("<BBBBHHII",size%256,size%256,0,0,1,32,len(image),offset))
    offset+=len(image)
(root/"ui/icon.ico").write_bytes(struct.pack("<HHH",0,1,len(entries))+b"".join(entries+images))
framework=Path(os.environ["SystemRoot"])/"Microsoft.NET/Framework64/v4.0.30319"
references=["/reference:"+str(framework/"WPF"/(name+".dll")) for name in ("WindowsBase","PresentationCore","PresentationFramework")]
subprocess.run([str(framework/"csc.exe"),"/nologo","/target:winexe","/out:PDFHub.exe","/win32icon:ui/icon.ico",
                "/reference:System.Windows.Forms.dll","/reference:System.Web.Extensions.dll","/reference:System.Xaml.dll",
                *references,"Launcher.cs","QuickEditor.cs"],cwd=root,check=True)
