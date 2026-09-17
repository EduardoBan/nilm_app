"""Runner minimo de tests (pytest no esta instalado en este entorno)."""
import json
import os
import sys
import traceback

sys.path.insert(0, os.getcwd())

import tests.test_engine as te
import tests.test_labels as tl

total = 0
fails = 0
for mod in (te, tl):
    for name in sorted(dir(mod)):
        if not name.startswith("test_"):
            continue
        total += 1
        try:
            getattr(mod, name)()
            print(f"PASS {mod.__name__}.{name}")
        except Exception as exc:
            fails += 1
            print(f"FAIL {mod.__name__}.{name}: {type(exc).__name__}: {exc}")
            traceback.print_exc()

print(f"TESTS: {total - fails}/{total} PASS")

# Validacion extra: reproducir el encoder exacto del servidor (NumpyEncoder,
# backend/server.py) y comprobar ademas que los campos NUEVOS son JSON estrictos.
import json as _json

import numpy as _np

from backend.data_manager import DataManager
from backend.nilm_engine import NILMEngine
from backend.server import NumpyEncoder

dm = DataManager()
ds = dm.list_datasets()[0]["id"]
new_keys = ("harmonic_signatures", "fhmm_exact", "hmmlearn_available")

for use_fhmm in (True, False):
    res = NILMEngine(dm).analyze_dataset(ds, use_fhmm=use_fhmm)

    # 1) Serializacion real del servidor: debe funcionar y no emitir NaN/Infinity.
    payload = _json.dumps(res, cls=NumpyEncoder, ensure_ascii=False)
    bad = [tok for tok in ("NaN", "Infinity", "-Infinity") if tok in payload]
    print(f"server_json use_fhmm={use_fhmm}: bytes={len(payload)} invalid_tokens={bad}")
    assert not bad, f"payload no estricto: {bad}"

    # 2) NEW fields must be serializable with the STANDARD ENCODER
    #    (sin depender del NumpyEncoder del servidor).
    subset = {k: res.get(k) for k in new_keys}
    strict = _json.dumps(subset)
    print(f"strict_json new_fields use_fhmm={use_fhmm}: bytes={len(strict)} OK")

    # 2b) Los eventos scatter deben exponer las claves armonicas como float/int
    #     nativos (los campos heredados id/cluster usan enteros numpy y los
    #     cubre NumpyEncoder, ya validado en el paso 1).
    for ev in res["scatter_events"]:
        for f in ("delta_h3", "delta_h5", "delta_h7", "harm_ratio_pct"):
            assert isinstance(ev[f], float), f"{f} no es float: {type(ev[f])}"

    # 3) Estructura esperada por las pestanas del frontend.
    assert len(res["harmonic_signatures"]) == res["n_clusters"]
    for sig in res["harmonic_signatures"]:
        assert isinstance(sig["id"], int) and not isinstance(sig["id"], bool)
        for f in ("avg_delta_h3", "avg_delta_h5", "avg_delta_h7", "harm_ratio_pct"):
            assert isinstance(sig[f], float)
    if use_fhmm:
        assert res["fhmm_exact"] is not None or not res["hmmlearn_available"]
        if res["fhmm_exact"]:
            assert res["fhmm_exact"]["n_comb_states"] == int(_np.prod(res["fhmm_exact"]["dims"]))
    else:
        assert res["fhmm_exact"] is None
    print(f"structure use_fhmm={use_fhmm}: OK")

print("ALL CHECKS OK")