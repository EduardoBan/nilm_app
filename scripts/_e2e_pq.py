"""Verificacion E2E de las MEJORAS #20 y #21 sobre el dataset real.

#11 Firmas extendidas en el clustering:
    el motor debe exponer cos(phi) medio, ratio de inrush y tipo de fase
    (mono/asimetrico/trifasico) por equipo en machine_statistics y en
    harmonic_signatures, y usarlos en _classify_load_class.
#12 Diagnostico de Calidad Energetica (/api/powerquality):
    DataManager.get_power_quality debe devolver el informe completo
    (checks EN 50160/IEC, sags/swells, series decimadas) y ser JSON
    estricto (sin NaN/Infinity ni tipos numpy).
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())

from backend.data_manager import DataManager
from backend.nilm_engine import NILMEngine


def ascii_safe(text) -> str:
    """Evita UnicodeEncodeError al imprimir en consolas cp1252."""
    return str(text).encode("ascii", "replace").decode("ascii")


dm = DataManager()
ds = dm.list_datasets()[0]["id"]
print("dataset:", ascii_safe(ds))

# ---------------- MEJORA #21: informe de calidad energetica -------------
pq = dm.get_power_quality(ds, max_points=600)
print("PQ vnom:", pq["vnom"], "V | muestras:", pq["samples"])
print("PQ metodo:", ascii_safe(pq.get("method")))
for c in pq["checks"]:
    print(f"  [{c['status']:>4}] {ascii_safe(c['label'])}: {ascii_safe(c['value'])} "
          f"({ascii_safe(c['limit'])}) - {ascii_safe(c['note'])}")
print("PQ unbalance:", pq["unbalance"])
print("PQ thd_u:", pq["thd_u"], "| thd_i:", pq["thd_i"])
print("PQ neutro:", pq["neutral"], "| K-factor:", pq["k_factor"])
print("PQ crest:", pq["crest"], "| frecuencia:", pq["frequency"])
print("PQ sags:", len(pq["sags"]), "| swells:", len(pq["swells"]))
print("PQ series:", {k: len(v) for k, v in pq["timeseries"].items()})
pq_json = json.dumps(pq, allow_nan=False)
print("PQ json_strict: OK bytes=", len(pq_json))

# ---------------- MEJORA #20: firmas extendidas del motor ---------------
r = NILMEngine(dm).analyze_dataset(ds)
print("equipos:", len(r["machine_statistics"]))
cosphi_rng_ok = True
inrush_rng_ok = True
for m in r["machine_statistics"]:
    cosphi = m.get("avg_cosphi")
    inrush = m.get("avg_inrush")
    if not (0.0 <= float(cosphi) <= 1.0):
        cosphi_rng_ok = False
    if not (0.2 <= float(inrush) <= 20.0):
        inrush_rng_ok = False
    print("  equipo {} {:<34} cosphi={:.3f} arranque=x{:.2f} fases={:<22} | {}".format(
        m["id"], ascii_safe(m["name"])[:34], float(cosphi), float(inrush),
        ascii_safe(m.get("phase_type")), ascii_safe(m.get("load_class"))))

sigs = r.get("harmonic_signatures") or []
sigs_ext = sum(1 for s in sigs if {"avg_cosphi", "avg_inrush", "phase_type"} <= set(s))
print(f"firmas armonicas: {len(sigs)} | con firmas extendidas: {sigs_ext}")

stats_ok = bool(r["machine_statistics"]) and all(
    {"avg_cosphi", "avg_inrush", "phase_type"} <= set(m) for m in r["machine_statistics"]
)
sigs_ok = bool(sigs) and sigs_ext == len(sigs)
payload = json.dumps(r, allow_nan=False)
print("analyze json_strict: OK bytes=", len(payload))

checks_ok = {c["id"] for c in pq["checks"]} >= {
    "voltage", "unbalance", "thd_u", "thd_i", "neutral", "k_factor", "frequency", "sags"
}
pq_fields_ok = all(
    k in pq[key] for key, k in (
        ("unbalance", "p95"), ("thd_u", "p95"), ("thd_i", "p95"),
        ("neutral", "p95_a"), ("k_factor", "p95"), ("k_factor", "samples"),
        ("frequency", "p95_dev"),
    )
) and all(k in pq["voltage"] for k in ("p95_dev", "max_dev", "samples_out"))
ts = pq["timeseries"]
series_ok = bool(ts["timestamps"]) and all(len(v) == len(ts["timestamps"]) for v in ts.values())
ok = (checks_ok and pq_fields_ok and stats_ok and sigs_ok and series_ok
      and cosphi_rng_ok and inrush_rng_ok)
print("checks_ok:", checks_ok, "| pq_fields_ok:", pq_fields_ok,
      "| stats_ok:", stats_ok, "| sigs_ok:", sigs_ok, "| series_ok:", series_ok)
print("|cos(phi)| en (0,1]:", cosphi_rng_ok, "| arranque en [0.2,20]:", inrush_rng_ok)
print("E2E PQ (#11 + #12):", "OK" if ok else "FALLO")
sys.exit(0 if ok else 1)
