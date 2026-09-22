"""Smoke test HTTP de los endpoints del servidor Tornado (sin navegador).

Arranca el servidor en un proceso y consulta /api/datasets, /api/powerquality
(MEJORA #21) y /api/harmonics, validando el JSON estricto de cada respuesta.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8011"

proc = subprocess.Popen(
    [sys.executable, "-u", "-c",
     "import os, sys; sys.path.insert(0, os.getcwd());"
     "import tornado.ioloop;"
     "from backend.server import make_app;"
     "app = make_app(); app.listen(8011);"
     "tornado.ioloop.IOLoop.current().start()"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=os.getcwd(),
)

try:
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{BASE}/api/datasets", timeout=1).read()
            break
        except Exception:
            time.sleep(0.5)
    else:
        raise SystemExit("servidor no respondio")

    def hit(path):
        with urllib.request.urlopen(BASE + path, timeout=180) as r:
            raw = r.read().decode("utf-8")
        payload = json.loads(raw)
        print(f"{path} -> HTTP {r.status} | {len(raw)} bytes | status={payload.get('status')}")
        return payload

    ds = json.loads(urllib.request.urlopen(f"{BASE}/api/datasets", timeout=30).read())["data"]
    ds_id = ds[0]["id"] if isinstance(ds, list) else ds["datasets"][0]["id"]
    print("dataset:", ds_id)

    pq = hit(f"/api/powerquality?dataset_id={ds_id}&max_points=400")
    d = pq["data"]
    print("  checks:", [(c["id"], c["status"]) for c in d["checks"]])
    print("  vnom:", d["vnom"], "| sags:", len(d["sags"]), "| swells:", len(d["swells"]))
    print("  series pts:", len(d["timeseries"]["timestamps"]))
    print("  thd_i:", d["thd_i"], "| k_factor:", d["k_factor"])

    h = hit(f"/api/harmonics?dataset_id={ds_id}")
    print("  armonicos: claves =", list(h["data"].keys())[:8])

    ok = (
        pq.get("status") == "success"
        and {c["id"] for c in d["checks"]} >= {"voltage", "unbalance", "thd_u", "thd_i",
                                               "neutral", "k_factor", "frequency", "sags"}
        and len(d["timeseries"]["timestamps"]) > 0
        and h.get("status") == "success"
    )
    print("SMOKE HTTP:", "OK" if ok else "FALLO")
    sys.exit(0 if ok else 1)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
