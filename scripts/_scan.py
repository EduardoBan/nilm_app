"""Localiza la ruta exacta de los valores no serializables por json.dumps."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())

from backend.data_manager import DataManager
from backend.nilm_engine import NILMEngine

dm = DataManager()
ds = dm.list_datasets()[0]["id"]

found = []


def walk(obj, path):
    if isinstance(obj, dict):
        for k, v in obj.items():
            walk(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            walk(v, f"{path}[{i}]")
    elif isinstance(obj, (bool, type(None), str, int, float)):
        if type(obj).__module__ == "numpy":
            found.append((path, type(obj).__name__, repr(obj)))
        elif isinstance(obj, float) and (obj != obj or obj in (float("inf"), float("-inf"))):
            found.append((path, "non-finite float", repr(obj)))


for use_fhmm in (True, False):
    r = NILMEngine(dm).analyze_dataset(ds, use_fhmm=use_fhmm)
    found.clear()
    walk(r, f"use_fhmm={use_fhmm}")
    print(f"=== use_fhmm={use_fhmm}: {len(found)} problemas ===")
    for path, tname, val in found[:25]:
        print("  ", path, "->", tname, val)
    if len(found) > 25:
        print("   ... y", len(found) - 25, "mas")