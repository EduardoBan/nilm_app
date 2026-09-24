"""Diagnostico E2E use_fhmm=False con progreso granular (temporal)."""
import faulthandler
import os
import sys
import threading
import time
import traceback

faulthandler.enable()
sys.path.insert(0, os.getcwd())

LOG = os.path.join(os.getcwd(), ".tmp_diag_nofhmm.log")


def say(msg):
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


open(LOG, "w", encoding="utf-8").close()

_stop = threading.Event()


def heartbeat():
    while not _stop.wait(5):
        say(f"HB t={int(time.time() % 10000)}")


threading.Thread(target=heartbeat, daemon=True).start()
say("START")
try:
    from backend.data_manager import DataManager
    from backend.nilm_engine import NILMEngine
    say("IMPORT_OK")
    dm = DataManager()
    ds = dm.list_datasets()[0]["id"]
    say(f"DATASET_OK {ds}")
    result = NILMEngine(dm).analyze_dataset(ds, use_fhmm=False)
    say(f"ANALYZE_OK keys={len(result)} standby={'si' if result.get('standby') else 'no'}")
    import json
    payload = json.dumps(result, allow_nan=False)
    say(f"JSON_OK bytes={len(payload)}")
except BaseException as exc:
    say(f"EXC {type(exc).__name__}: {exc}")
    traceback.print_exc(file=sys.stderr)
    _stop.set()
    sys.exit(1)
_stop.set()
say("DONE")
print("DONE_OK")