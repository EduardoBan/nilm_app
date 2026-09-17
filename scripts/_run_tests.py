"""Runner minimo de tests (pytest no esta instalado en este entorno).

Ademas ejecuta los tests de tests/, valida que el payload real sea JSON
estricto (sin NaN/Infinity ni tipos numpy) localizando el campo culpable.
"""
import json
import math
import os
import sys
import traceback

import numpy as np

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


def scan_bad(obj, path="$"):
    """Localiza valores no serializables (numpy, NaN/Inf) con su ruta."""
    bad = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            bad += scan_bad(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            bad += scan_bad(v, f"{path}[{i}]")
    elif isinstance(obj, float):
        if not math.isfinite(obj):
            bad.append(f"{path} = {obj} (no finito)")
    elif isinstance(obj, (bool, int, str)) or obj is None:
        pass
    elif isinstance(obj, (np.integer, np.floating)):
        bad.append(f"{path} = {obj} ({type(obj).__name__} numpy)")
    else:
        bad.append(f"{path} = {obj} ({type(obj).__name__} no JSON)")
    return bad


from backend.data_manager import DataManager
from backend.nilm_engine import NILMEngine

dm = DataManager()
ds = dm.list_datasets()[0]["id"]
json_ok = True
for use_fhmm in (True, False):
    result = NILMEngine(dm).analyze_dataset(ds, use_fhmm=use_fhmm)
    problems = scan_bad(result)
    for p in problems[:15]:
        json_ok = False
        print(f"  !! {p}")
    try:
        payload = json.dumps(result, allow_nan=False)
        print(f"json use_fhmm={use_fhmm}: bytes={len(payload)} problemas={len(problems)}")
    except (TypeError, ValueError) as exc:
        json_ok = False
        print(f"json use_fhmm={use_fhmm}: FALLO ({type(exc).__name__}: {exc})")

print("JSON_STRICT:", "OK" if json_ok else "FALLO")
sys.exit(1 if fails or not json_ok else 0)
