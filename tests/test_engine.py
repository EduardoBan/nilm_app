"""Motor NILM con datos sintéticos: eventos + clustering + validación de rangos."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.nilm_engine import NILMEngine


class _FakeDM:
    def get_labels(self, dataset_id):
        return {}


def make_df(n=400):
    rng = np.random.default_rng(7)
    t = pd.date_range("2024-01-01", periods=n, freq="1min")
    # Base 5 A + dos escalones simulando arranques
    i = np.full(n, 5.0) + rng.normal(0, 0.05, n)
    i[100:200] += 8.0
    i[250:330] += 15.0
    return pd.DataFrame({
        "timestamp": t,
        "I *L1 media [A]": i / 3,
        "I *L2 media [A]": i / 3,
        "I *L3 media [A]": i / 3,
        "U L1 media [V]": 230.0,
        "U L2 media [V]": 230.0,
        "U L3 media [V]": 230.0,
        "PF L1 media [---]": 0.9,
        "PF L2 media [---]": 0.9,
        "PF L3 media [---]": 0.9,
    })


def test_detect_events_finds_steps():
    eng = NILMEngine(_FakeDM())
    df_work, ev = eng.detect_events(make_df(), current_threshold=2.0, power_threshold=0.5)
    assert len(ev) >= 2
    assert set(ev["event_type"].unique()) <= {"ON", "OFF"}
    assert (ev[ev["event_type"] == "ON"]["delta_I"] > 0).all()


def test_cluster_on_events_only():
    eng = NILMEngine(_FakeDM())
    df = make_df()
    _, ev = eng.detect_events(df, current_threshold=2.0, power_threshold=0.5)
    clustered, info = eng.cluster_appliances(ev, n_clusters=2, algorithm="kmeans")
    assert len(info) == 2
    # El clustering usa magnitudes absolutas: ON y OFF del mismo equipo caen
    # en el mismo cluster (tantos clusters como escalones simulados: +8A y +15A).
    assert set(clustered["cluster"].unique()) <= set(info.keys())
    assert (clustered["event_type"].isin(["ON", "OFF"])).all()
    assert (clustered[clustered["event_type"] == "ON"]["delta_I"] > 0).all()


def test_disaggregate_produces_timeline():
    eng = NILMEngine(_FakeDM())
    df = make_df()
    df_work, ev = eng.detect_events(df, current_threshold=2.0, power_threshold=0.5)
    clustered, info = eng.cluster_appliances(ev, n_clusters=2, algorithm="kmeans")
    disagg, baseline, timeline, stats = eng.disaggregate_load(df_work, clustered, info)
    assert len(timeline) > 0
    assert all("start_time" in t and "end_time" in t for t in timeline)
    assert len(stats) == len(info)
