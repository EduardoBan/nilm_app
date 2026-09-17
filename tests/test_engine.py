"""Motor NILM con datos sintéticos: eventos + clustering + validación de rangos."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.nilm_engine import NILMEngine, hmmlearn_available


class _FakeDM:
    def __init__(self, df=None):
        self._df = df

    def get_labels(self, dataset_id):
        return {}

    def load_dataset(self, dataset_id):
        return self._df if self._df is not None else make_df()


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


def make_df_harm(n=400):
    """Datos sintéticos con contenido armónico: H3/H5/H7 sólo en el escalón
    de 8 A (carga no lineal tipo VFD), ausentes en el de 15 A (motor DOL)."""
    df = make_df(n)
    rng = np.random.default_rng(11)
    shape = np.zeros(n)
    shape[100:200] = 1.0
    for order, gain in ((3, 1.2), (5, 0.9), (7, 0.4)):
        base = gain * shape + rng.normal(0, 0.01, n)
        for ph in ("L1", "L2", "L3"):
            df[f"I H {order} {ph} media [A]"] = base / 3.0
    for ph in ("L1", "L2", "L3"):
        df[f"THD I {ph} media [%]"] = 20.0 + 40.0 * shape + rng.normal(0, 0.5, n)
    return df


def test_harmonic_signature_per_machine_and_event():
    """PASO 1: la firma armónica se agrega por equipo y por evento."""
    eng = NILMEngine(_FakeDM(make_df_harm()))
    res = eng.analyze_dataset("synthetic", n_clusters=2, power_threshold=0.5,
                              current_threshold=2.0)

    sigs = res["harmonic_signatures"]
    assert len(sigs) == res["n_clusters"]
    for sig in sigs:
        assert set(sig) >= {
            "id", "name", "color", "avg_delta_h3", "avg_delta_h5", "avg_delta_h7",
            "harm_ratio_pct", "avg_thd", "avg_delta_p", "count",
        }
        assert sig["avg_delta_h3"] >= 0.0
        assert sig["avg_delta_h5"] >= 0.0
        assert sig["avg_delta_h7"] >= 0.0
        assert sig["harm_ratio_pct"] >= 0.0

    assert len(res["scatter_events"]) > 0
    for ev in res["scatter_events"]:
        assert set(ev) >= {"delta_h3", "delta_h5", "delta_h7", "harm_ratio_pct"}

    # Los equipos del clustering exponen la firma armónica agregada.
    for stat in res["machine_statistics"]:
        assert stat["avg_delta_h5"] >= 0.0
        assert stat["load_class"]


def test_fhmm_exact_viterbi_product_states():
    """PASO 2: FHMM exacto sobre el producto cartesiano de estados."""
    eng = NILMEngine(_FakeDM(make_df_harm()))
    res = eng.analyze_dataset("synthetic", n_clusters=2, use_fhmm=True,
                              max_states=3, power_threshold=0.5,
                              current_threshold=2.0)

    assert res["fhmm_enabled"] is True
    assert "fhmm_exact" in res and "hmmlearn_available" in res
    # La desagregación sigue siendo válida con FHMM activado.
    assert len(res["disaggregated_machines"]) == res["n_clusters"]
    assert len(res["p_total"]) == len(res["timestamps"])

    fx = res["fhmm_exact"]
    if not hmmlearn_available or fx is None:
        return
    assert fx["method"] == "fhmm_exact_viterbi_hmmlearn"
    assert fx["n_comb_states"] == int(np.prod(fx["dims"]))
    assert len(fx["combined_seq_ds"]) == fx["n_points_decoded"]
    assert len(fx["state_means_kw"]) == fx["n_comb_states"]
    assert all(0 <= s < fx["n_comb_states"] for s in fx["combined_seq_ds"])


def test_fhmm_exact_pruning_degrades_without_error():
    """La poda (>max_comb_states) degrada al descenso por eventos sin romper."""
    eng = NILMEngine(_FakeDM())
    df_work, ev = eng.detect_events(make_df_harm(), current_threshold=2.0,
                                    power_threshold=0.5)
    clustered, info = eng.cluster_appliances(ev, n_clusters=2, algorithm="kmeans")
    heavy = {c: [1.0 * k for k in range(1, 7)] for c in info}  # 6 estados/equipo
    # 7 x 7 estados combinados > 10 => podado
    assert eng._fhmm_exact_viterbi(df_work, heavy, info, max_comb_states=10) is None
    if not hmmlearn_available:
        assert eng._fhmm_exact_viterbi(df_work, heavy, info, max_comb_states=10 ** 6) is None
        return
    ok = eng._fhmm_exact_viterbi(df_work, heavy, info, max_comb_states=10 ** 6)
    assert ok is not None
    assert ok["n_comb_states"] == int(np.prod(ok["dims"]))


def test_fhmm_exact_handles_degenerate_input():
    """Entradas degeneradas (sin P_total, serie corta, NaN) no lanzan excepción."""
    eng = NILMEngine(_FakeDM())
    empty = pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=0, freq="1min")})
    assert eng._fhmm_exact_viterbi(empty, {}, {}) is None

    tiny = pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=2, freq="1min"),
                         "P_total": [1.0, 1.0]})
    assert eng._fhmm_exact_viterbi(tiny, {0: [1.0]}, {0: {"avg_delta_p": 1.0}}) is None

    n = 300
    df_work, ev = eng.detect_events(make_df_harm(n), current_threshold=2.0,
                                   power_threshold=0.5)
    df_work.loc[df_work.index[:50], "P_total"] = np.nan
    clustered, info = eng.cluster_appliances(ev, n_clusters=1, algorithm="kmeans")
    eng._fhmm_exact_viterbi(df_work, {c: [1.0] for c in info}, info)


def test_validation_report_keys_and_consistency():
    """PASO 3: informe de validación completo y matemáticamente consistente."""
    eng = NILMEngine(_FakeDM(make_df_harm()))
    res = eng.analyze_dataset("synthetic", n_clusters=2, use_fhmm=True,
                              max_states=2, power_threshold=0.5,
                              current_threshold=2.0)

    val = res.get("validation")
    assert val, "analyze_dataset debe devolver 'validation' con datos suficientes"

    rec = val["reconstruction"]
    assert set(rec) >= {"mae_kw", "rmse_kw", "mape_pct", "energy_explained_pct"}
    assert rec["mae_kw"] >= 0.0 and rec["rmse_kw"] >= rec["mae_kw"] * 0.999

    cg = val["confusion_global"]
    assert set(cg) >= {"tp", "fp", "fn", "tn", "precision", "recall", "f1"}
    # La matriz global es la suma de las matrices por equipo.
    tp = sum(m["confusion"]["tp"] for m in val["machines"])
    fp = sum(m["confusion"]["fp"] for m in val["machines"])
    fn = sum(m["confusion"]["fn"] for m in val["machines"])
    tn = sum(m["confusion"]["tn"] for m in val["machines"])
    assert (tp, fp, fn, tn) == (cg["tp"], cg["fp"], cg["fn"], cg["tn"])
    assert 0.0 <= cg["precision"] <= 1.0 and 0.0 <= cg["recall"] <= 1.0
    assert 0.0 <= cg["f1"] <= 1.0

    assert len(val["machines"]) == res["n_clusters"]
    for m in val["machines"]:
        assert set(m) >= {
            "id", "name", "color", "n_on_events", "jump_mae_kw",
            "confusion", "precision", "recall", "f1",
        }
        assert m["n_on_events"] >= 0
        assert m["jump_mae_kw"] >= 0.0
        assert set(m["confusion"]) == {"tp", "fp", "fn", "tn"}


def test_validation_empty_series_returns_empty_dict():
    """PASO 3: con una serie demasiado corta no se emite informe (dict vacío)."""
    eng = NILMEngine(_FakeDM())
    tiny = pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=2, freq="1min"),
        "P_total": [1.0, 1.0],
    })
    assert eng._validate_disaggregation(tiny, pd.DataFrame(), {}, {}, np.zeros(2)) == {}
