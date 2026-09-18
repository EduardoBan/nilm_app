"""Verificacion E2E de la MEJORA #2 (priors horarios) sobre el dataset real."""
import json
import os
import sys

sys.path.insert(0, os.getcwd())

from backend.data_manager import DataManager
from backend.nilm_engine import NILMEngine

dm = DataManager()
ds = dm.list_datasets()[0]["id"]
r = NILMEngine(dm).analyze_dataset(ds, use_fhmm=True)
fx = r.get("fhmm_exact") or {}

print("dataset:", ds)
print("method:", fx.get("method"))
print("priors_used:", fx.get("priors_used"))
print("features:", fx.get("features"))
print("logprob:", fx.get("logprob"), "| sin priors:", fx.get("logprob_no_priors"),
      "| con priors:", fx.get("logprob_priors"))
print("n_comb_states:", fx.get("n_comb_states"), "| dims:", fx.get("dims"))
print("night_minutes_reduced:", fx.get("night_minutes_reduced"))
before = fx.get("on_minutes_total_before") or []
after = fx.get("on_minutes_total_after") or []
print("on_minutes before (24h):", [round(v, 1) for v in before])
print("on_minutes after  (24h):", [round(v, 1) for v in after])
print("hourly_priors (equipos):", list((fx.get("hourly_priors") or {}).keys()))
for k, rate in (fx.get("hourly_priors") or {}).items():
    print(f"  equipo {k}: min={min(rate):.2f} max={max(rate):.2f} "
          f"horas>1={sum(1 for v in rate if v > 1.0)}")

payload = json.dumps(r, allow_nan=False)
print("json_strict: OK bytes=", len(payload))
ok = (
    fx.get("priors_used") is True
    and fx.get("method") == "fhmm_exact_viterbi_priors_hmmlearn"
    and len(before) == 24 and len(after) == 24
    and fx.get("night_minutes_reduced") is not None
    and fx.get("logprob_no_priors") is not None
)
print("E2E PRIORS:", "OK" if ok else "FALLO")
