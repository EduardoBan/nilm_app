"""Verificacion HTTP real de los endpoints nuevos (MEJORA #12).

Levanta la app Tornado en un puerto de prueba (8123), consulta
/api/powerquality y /api/datasets, valida el JSON devuelto y comprueba que
el bundle compilado incluye la pestaña de Calidad Energetica.
"""
import json
import os
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.getcwd())

import tornado.ioloop

from backend.server import make_app

PORT = 8123
BASE = f"http://127.0.0.1:{PORT}"

app = make_app()
app.listen(PORT)
loop = tornado.ioloop.IOLoop.current()
threading.Thread(target=loop.start, daemon=True).start()
time.sleep(1.0)


def get(path: str, timeout: float = 180.0):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


try:
    st, ds = get("/api/datasets")
    dataset_id = ds["data"][0]["id"]
    print("GET /api/datasets ->", st, "| dataset:", dataset_id)

    st, pq = get(f"/api/powerquality?dataset_id={dataset_id}&max_points=400")
    body = pq.get("data") or {}
    print("GET /api/powerquality ->", st, "| status:", pq.get("status"))
    print("  vnom:", body.get("vnom"), "| muestras:", body.get("samples"))
    for c in body.get("checks", []):
        print(f"  [{c['status']:>4}] {c['id']}: {c['value']}  ({c['limit']})")
    print("  sags:", len(body.get("sags") or []), "| swells:", len(body.get("swells") or []))
    ts = body.get("timeseries") or {}
    print("  series:", {k: len(v) for k, v in ts.items()})

    checks = {c["id"] for c in body.get("checks", [])}
    ok_checks = checks >= {"voltage", "unbalance", "thd_u", "thd_i", "neutral",
                           "k_factor", "frequency", "sags"}
    ok_status = all(c["status"] in ("ok", "warn", "bad") for c in body.get("checks", []))
    ok_series = bool(ts.get("timestamps")) and all(
        len(v) == len(ts["timestamps"]) for v in ts.values()
    )
    # Decimation uses step = len//max_points, so the actual count can
    # superar ligeramente el limite pedido (8477/400 -> step 21 -> 404 puntos).
    ok_limit = len(ts.get("timestamps", [])) <= int(400 * 1.05) + 2

    # JSON estricto (sin NaN/Infinity): lo valida el decoder estricto de Python
    strict = json.dumps(body, allow_nan=False)
    print("  json estricto: OK bytes=", len(strict))

    with open(os.path.join("frontend", "dist", "bundle.js"), encoding="utf-8") as fh:
        bundle = fh.read()
    ok_bundle = ("renderPowerQualityTab" in bundle) and ("powerquality" in bundle)
    print("bundle con pestana PQ:", ok_bundle, "| KB:", round(len(bundle) / 1024, 1))

    ok = ok_checks and ok_status and ok_series and ok_limit and ok_bundle
    print("E2E HTTP PQ:", "OK" if ok else "FALLO")
finally:
    loop.add_callback(loop.stop)
    time.sleep(0.3)

sys.exit(0 if ok else 1)
