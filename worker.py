import json
import sys
from pathlib import Path
from engine import convert


def process(job):
    paths = [Path(p) for p in job["files"]]
    if sum(p.stat().st_size for p in paths)>200*1024**2:
        raise ValueError("Limite di 200 MB per operazione.")
    name,data = convert(job["op"],[(p.name,p.read_bytes()) for p in paths],job["options"])
    Path(job["output"]).write_bytes(data)
    return name


if __name__=="__main__":
    try:
        job=json.load(sys.stdin)
        # Alcuni lettori di tabelle stampano messaggi informativi.
        from contextlib import redirect_stdout
        with redirect_stdout(sys.stderr):
            result={"name":process(job)}
    except Exception as exc:
        result={"error":str(exc)}
    print(json.dumps(result))
