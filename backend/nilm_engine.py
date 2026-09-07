import numpy as np
import pandas as pd
from sklearn.cluster import KMeans, DBSCAN
from sklearn.mixture import GaussianMixture
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
from typing import Dict, List, Any, Optional, Tuple

try:
    from nilmtk.feature_detectors.cluster import cluster as nilmtk_cluster_states
except ImportError:
    nilmtk_cluster_states = None

class NILMEngine:
    """
    Advanced NILM (Non-Intrusive Load Monitoring) Engine
    Provides event detection, multi-feature clustering, state tracking,
    and continuous load disaggregation for industrial and commercial energy data.
    """
    def __init__(self, data_manager):
        self.dm = data_manager
        self.nilmtk_available = nilmtk_cluster_states is not None

    def estimate_nilmtk_power_states(self, df_work: pd.DataFrame, max_states: int = 8) -> List[float]:
        """Estimate aggregate power states with NILMTK when it is installed."""
        if nilmtk_cluster_states is None or 'P_total' not in df_work:
            return []

        try:
            power_series = pd.Series(
                df_work['P_total'].to_numpy(dtype=float),
                name='active_power'
            )
            states = nilmtk_cluster_states(
                power_series.abs(),
                max_num_clusters=max_states,
                random_state=42
            )
            return [float(state) for state in np.asarray(states).flatten() if float(state) > 0]
        except Exception:
            return []

    def detect_events(self, df: pd.DataFrame, 
                      current_threshold: float = 2.0, 
                      power_threshold: float = 1.0) -> pd.DataFrame:
        """
        Detects electrical switching events (turn-on and turn-off transients)
        using multi-parameter step changes.
        Each detected transition is labelled in the 'event_type' column:
        'ON' for positive transitions (turn-on) and 'OFF' for negative ones.
        """
        i_cols = [c for c in ['I *L1 media [A]', 'I *L2 media [A]', 'I *L3 media [A]'] if c in df.columns]
        v_cols = [c for c in ['U L1 media [V]', 'U L2 media [V]', 'U L3 media [V]'] if c in df.columns]
        pf_cols = [c for c in ['PF L1 media [---]', 'PF L2 media [---]', 'PF L3 media [---]'] if c in df.columns]
        thd_cols = [c for c in df.columns if 'THD I' in c and 'media [%]' in c and 'N' not in c]
        
        df_work = df.copy()
        
        if i_cols:
            df_work['I_total'] = df_work[i_cols].sum(axis=1)
        else:
            df_work['I_total'] = 10.0

        if v_cols:
            df_work['V_avg'] = df_work[v_cols].mean(axis=1)
        else:
            df_work['V_avg'] = 230.0

        if pf_cols:
            df_work['PF_avg'] = df_work[pf_cols].abs().mean(axis=1)
        else:
            df_work['PF_avg'] = 0.92

        # 3-Phase Active Power (kW) = (V_avg * I_total * PF_avg) / 1000.0
        df_work['P_total'] = (df_work['V_avg'] * df_work['I_total'] * df_work['PF_avg']) / 1000.0
        
        # Reactive Power Q (kvar) = sqrt(S^2 - P^2)
        df_work['S_total'] = (df_work['V_avg'] * df_work['I_total']) / 1000.0
        df_work['Q_total'] = np.sqrt(np.maximum(0, df_work['S_total']**2 - df_work['P_total']**2))

        if thd_cols:
            df_work['THD_avg'] = df_work[thd_cols].mean(axis=1).fillna(0)
        else:
            df_work['THD_avg'] = 15.0

        # --- Harmonic transient tracking (Opción A - Punto 3) ---
        # Sum of harmonic currents (orders 3..13 across phases). The variation
        # of this signal at the instant of a start-up transient discriminates
        # power-electronics loads (VFDs, welders, rectifiers) from purely
        # inductive machines (DOL / star-delta motor starts).
        harm_total = None
        for h_order in (3, 5, 7, 9, 11, 13):
            h_cols = [c for c in df_work.columns
                      if c.startswith(f'I H {h_order} L') and 'media [A]' in c]
            if h_cols:
                h_series = df_work[h_cols].sum(axis=1)
                harm_total = h_series if harm_total is None else harm_total + h_series
        df_work['H_total'] = harm_total if harm_total is not None else 0.0

        # Step differences (deltas)
        df_work['delta_P'] = df_work['P_total'].diff().fillna(0)
        df_work['delta_Q'] = df_work['Q_total'].diff().fillna(0)
        df_work['delta_I'] = df_work['I_total'].diff().fillna(0)
        df_work['delta_H'] = df_work['H_total'].diff().fillna(0)
        df_work['delta_THD'] = df_work['THD_avg'].diff().fillna(0)
        
        # Detect turn-on events (positive transitions)
        mask_on = (df_work['delta_I'] >= current_threshold) | (df_work['delta_P'] >= power_threshold)
        # Detect turn-off events (negative transitions)
        mask_off = (df_work['delta_I'] <= -current_threshold) | (df_work['delta_P'] <= -power_threshold)

        events = df_work[mask_on | mask_off].copy()
        events['event_type'] = np.where(
            mask_on.reindex(events.index).fillna(False).values, 'ON', 'OFF'
        )
        
        # Additional features
        events['hour_of_day'] = events['timestamp'].dt.hour + events['timestamp'].dt.minute / 60.0

        # Harmonic transient signature: harmonic-current step (ΔIh, H3..H13)
        # relative to the fundamental-current step (ΔI1 ≈ ΔI total), in %.
        # High values => non-linear power-electronics load; low values with a
        # large reactive inrush => induction motor with direct start.
        denom = events['delta_I'].abs().clip(lower=0.1)
        events['harm_ratio_pct'] = (events['delta_H'].abs() / denom * 100.0).clip(upper=500.0)
        events['delta_thd'] = events['delta_THD']

        return df_work, events

    def cluster_appliances(self, events: pd.DataFrame, 
                           n_clusters: int = 4, 
                           algorithm: str = "kmeans",
                           labels: Optional[Dict[str, str]] = None) -> Tuple[pd.DataFrame, Dict[int, Any]]:
        """
        Applies Machine Learning clustering (K-Means, GMM, or DBSCAN)
        on multi-dimensional electrical features.
        """
        if len(events) == 0:
            events['cluster'] = []
            events['machine_name'] = []
            events['color'] = []
            return events, {}

        # Feature vector based on absolute magnitudes so that the turn-ON and
        # turn-OFF transitions of the same machine (same size, opposite sign)
        # cluster together.
        events['abs_delta_P'] = events['delta_P'].abs()
        events['abs_delta_I'] = events['delta_I'].abs()
        events['abs_delta_Q'] = events['delta_Q'].abs()
        features = ['abs_delta_P', 'abs_delta_I', 'THD_avg', 'abs_delta_Q']
        X = events[features].fillna(0).values
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        n_samples = len(events)
        effective_k = min(n_clusters, max(1, n_samples // 2))

        if algorithm.lower() == 'gmm':
            model = GaussianMixture(n_components=effective_k, random_state=42, max_iter=200)
            cluster_labels = model.fit_predict(X_scaled)
        elif algorithm.lower() == 'dbscan':
            model = DBSCAN(eps=0.75, min_samples=4)
            cluster_labels = model.fit_predict(X_scaled)
            unique_labels = sorted(list(set(cluster_labels)))
            label_map = {l: i for i, l in enumerate(unique_labels)}
            cluster_labels = np.array([label_map[l] for l in cluster_labels])
        else: # Default KMeans
            model = KMeans(n_clusters=effective_k, random_state=42, n_init=10)
            cluster_labels = model.fit_predict(X_scaled)

        events['cluster'] = cluster_labels

        colors = [
            "#3B82F6", "#10B981", "#F59E0B", "#EF4444", 
            "#8B5CF6", "#EC4899", "#06B6D4", "#84CC16"
        ]

        cluster_info = {}
        # Sort clusters by average power descending
        raw_clusters = sorted(events['cluster'].unique())
        avg_powers = {c: float(events[events['cluster'] == c]['delta_P'].abs().mean()) for c in raw_clusters}
        sorted_clusters = sorted(raw_clusters, key=lambda c: avg_powers[c], reverse=True)

        for rank, c in enumerate(sorted_clusters):
            sub = events[events['cluster'] == c]
            # Cluster magnitude (absolute delta) = nominal step of the machine,
            # valid for both ON and OFF transitions.
            avg_p = float(sub['delta_P'].abs().mean())
            avg_i = float(sub['delta_I'].abs().mean())
            avg_q = float(sub['delta_Q'].abs().mean()) if 'delta_Q' in sub else 0.0
            avg_thd = float(sub['THD_avg'].mean())

            # --- Harmonic transient refinement (Opción A - Punto 3) ---
            # Median harmonic step ratio (ΔIh / ΔI1) over the start-up
            # transients of the cluster and reactive/active step ratio.
            if 'harm_ratio_pct' in sub.columns:
                harm_ratio = float(sub['harm_ratio_pct'].median())
            else:
                harm_ratio = 0.0
            q_p_ratio = (avg_q / avg_p) if avg_p > 1e-6 else 0.0
            signature = self.classify_load_signature(avg_thd, harm_ratio, q_p_ratio)

            # Heuristic machine naming based on electrical signature
            if avg_p >= 25.0 or avg_i >= 40.0:
                name = f"Compresor / Motor Principal ({avg_p:.1f} kW)"
                category = "Compresor / Gran Potencia"
            elif avg_thd >= 40.0:
                name = f"Variador / Carga Electrónica (THD {avg_thd:.0f}%)"
                category = "Variador de Frecuencia"
            elif avg_p >= 8.0:
                name = f"Bomba / Ventilación Ind. ({avg_p:.1f} kW)"
                category = "Bomba / Ventilador"
            elif avg_p >= 2.0:
                name = f"Motor / Carga Secundaria ({avg_p:.1f} kW)"
                category = "Motor Mediano"
            else:
                name = f"Auxiliares / Standby ({avg_p:.1f} kW)"
                category = "Iluminación / Auxiliar"

            # The harmonic/transient classification refines the technology
            # category (non-linear vs inductive vs resistive).
            category = signature['load_class']

            cluster_info[c] = {
                "name": name,
                "category": category,
                "color": colors[rank % len(colors)],
                "avg_delta_p": round(avg_p, 2),
                "avg_delta_i": round(avg_i, 2),
                "avg_delta_q": round(avg_q, 2),
                "avg_thd": round(avg_thd, 1),
                "count": len(sub),
                "on_count": int((sub['event_type'] == 'ON').sum()),
                "off_count": int((sub['event_type'] == 'OFF').sum()),
                "load_class": signature['load_class'],
                "load_icon": signature['load_icon'],
                "load_family": signature['family'],
                "harmonic_signature_pct": round(harm_ratio, 1),
                "q_p_ratio": round(q_p_ratio, 2),
                "custom_label": False
            }

        # --- Manual Ground-Truth renaming (Opción A - Punto 2) ---
        # User-defined labels persisted per dataset+cluster override the
        # automatic heuristic names on every subsequent analysis.
        if labels:
            for key, custom_name in labels.items():
                try:
                    c_idx = int(key)
                except (TypeError, ValueError):
                    continue
                clean = str(custom_name).strip() if custom_name else ""
                if c_idx in cluster_info and clean:
                    cluster_info[c_idx]["name"] = clean
                    cluster_info[c_idx]["custom_label"] = True

        events['machine_name'] = events['cluster'].map(lambda c: cluster_info[c]['name'])
        events['color'] = events['cluster'].map(lambda c: cluster_info[c]['color'])
        events['category'] = events['cluster'].map(lambda c: cluster_info[c]['category'])

        return events, cluster_info

    @staticmethod
    def classify_load_signature(avg_thd: float, harm_ratio_pct: float, q_p_ratio: float) -> Dict[str, str]:
        """
        Discriminates the load technology using the start-up transient
        (Opción A - Punto 3: Refinamiento por Armónicos Transitorios):

        - Non-linear loads (variable frequency drives, welders, rectifiers)
          inject a strong harmonic step: high ΔIh/ΔI1 ratio and high THD.
        - Purely inductive machines (DOL / star-delta motor starts) draw a
          large reactive inrush (high ΔQ/ΔP) with a clean, low-harmonic wave.
        - Resistive loads (heaters, lighting) show neither reactive nor
          harmonic steps.
        """
        harm_ratio_pct = max(0.0, float(harm_ratio_pct))
        q_p_ratio = max(0.0, float(q_p_ratio))
        avg_thd = max(0.0, float(avg_thd))

        if harm_ratio_pct >= 15.0 or avg_thd >= 35.0:
            if q_p_ratio <= 0.30:
                return {
                    "load_class": "Electrónica de Potencia (Variador / Rectificador)",
                    "load_icon": "🎛️",
                    "family": "no_lineal"
                }
            return {
                "load_class": "Carga No Lineal (Soldadora / Arco Eléctrico)",
                "load_icon": "⚡",
                "family": "no_lineal"
            }
        if q_p_ratio >= 0.45:
            return {
                "load_class": "Motor Inductivo (Arranque Directo / Estrella-Tríangulo)",
                "load_icon": "⚙️",
                "family": "inductiva"
            }
        if q_p_ratio >= 0.18:
            return {
                "load_class": "Motor / Carga Mixta (Arranque Suave)",
                "load_icon": "🌀",
                "family": "inductiva"
            }
        return {
            "load_class": "Carga Resistiva (Calefacción / Iluminación)",
            "load_icon": "🔥",
            "family": "resistiva"
        }

    def estimate_machine_states(self, events: pd.DataFrame,
                                cluster_info: Dict[int, Any],
                                max_states: int = 3) -> Dict[int, Dict[str, Any]]:
        """
        Multi-state level estimation per appliance (FHMM front-end).
        (Opción A - Punto 1: Modelado Multi-Estado FHMM/HMM)

        Clusters the turn-ON power steps of every appliance into intermediate
        operating levels using K-Means + silhouette validation, so complex
        industrial machines (e.g. a compressor running unloaded / loaded /
        stopped) are modeled with more than a binary ON/OFF state.
        Level 0 is always OFF (0 kW).
        """
        machine_states: Dict[int, Dict[str, Any]] = {}
        if len(events) == 0:
            return machine_states

        max_states = max(2, int(max_states))
        state_names_by_count = {
            1: ["Apagado", "Encendido (Plena Carga)"],
            2: ["Apagado", "Marcha en Vacío (Parcial)", "Plena Carga"],
            3: ["Apagado", "Carga Baja", "Carga Media", "Plena Carga"],
            4: ["Apagado", "Nivel Mínimo", "Nivel Bajo", "Nivel Medio", "Plena Carga"]
        }

        for c, info in cluster_info.items():
            sub = events[(events['cluster'] == c) & (events['event_type'] == 'ON')]
            vals = sub['delta_P'].abs().clip(lower=0.2).to_numpy(dtype=float)
            nominal = max(0.5, float(info['avg_delta_p']))
            levels = [nominal]

            # Only look for intermediate states when there is enough evidence
            # (>= 6 ON transitions) and the user allows more than 2 states.
            if len(vals) >= 6 and max_states > 2:
                best_k, best_score = 1, 0.0
                k_upper = min(max_states - 1, len(vals) - 1, 4)
                for k in range(2, k_upper + 1):
                    km = KMeans(n_clusters=k, random_state=42, n_init=10)
                    k_labels = km.fit_predict(vals.reshape(-1, 1))
                    if len(np.unique(k_labels)) < 2:
                        continue
                    score = float(silhouette_score(vals.reshape(-1, 1), k_labels))
                    if score > best_score:
                        best_score, best_k = score, k
                if best_k > 1 and best_score >= 0.20:
                    km = KMeans(n_clusters=best_k, random_state=42, n_init=10)
                    km.fit(vals.reshape(-1, 1))
                    raw_levels = sorted(float(x) for x in km.cluster_centers_.flatten())
                    # Merge nearly-identical levels (< 25% of the top level)
                    merged = [raw_levels[0]]
                    for lv in raw_levels[1:]:
                        if lv - merged[-1] >= 0.25 * max(raw_levels):
                            merged.append(lv)
                    if len(merged) >= 2:
                        levels = merged

            names = state_names_by_count.get(
                len(levels),
                ["Apagado"] + [f"Nivel {i}" for i in range(1, len(levels))] + ["Plena Carga"]
            )
            states_list = [{"level": 0, "kw": 0.0, "name": names[0]}]
            for i, lv in enumerate(levels):
                states_list.append({
                    "level": i + 1,
                    "kw": round(float(lv), 2),
                    "name": names[i + 1] if i + 1 < len(names) else f"Nivel {i + 1}"
                })
            machine_states[c] = {
                "levels": np.array([0.0] + [float(s['kw']) for s in states_list[1:]]),
                "states": states_list,
                "n_states": len(states_list)
            }
        return machine_states

    def disaggregate_load_fhmm(self, df_work: pd.DataFrame,
                               events: pd.DataFrame,
                               cluster_info: Dict[int, Any],
                               machine_states: Dict[int, Dict[str, Any]],
                               switch_cost: float = 20.0):
        """
        Factorial Hidden Markov Model (FHMM) disaggregation.
        (Opción A - Punto 1: Modelado Multi-Estado FHMM/HMM)

        The aggregate measurement is modeled as the superposition (sum) of the
        hidden state of every appliance plus a background baseline:

            P_total(t) ≈ P_base + Σ_c  level_c(state_c(t))

        MAP inference is approximated with tractable event-driven coordinate
        descent: signal segmentation at detected events, greedy forward
        initialization, and block-coordinate Viterbi refinement per appliance
        (Gaussian emissions around each power level + switching cost).

        Returns (disagg_power, baseline_curve, timeline_events, machine_stats, fhmm_models)
        """
        n_points = len(df_work)
        timestamps = pd.to_datetime(df_work['timestamp']).to_numpy(dtype='datetime64[ns]')
        p_total = df_work['P_total'].values.astype(float)

        clusters = sorted([c for c in cluster_info.keys() if c in machine_states])
        levels = {c: machine_states[c]['levels'] for c in clusters}
        base_power = float(np.percentile(p_total, 5))

        disagg_power = {c: np.zeros(n_points, dtype=np.float32) for c in clusters}

        # --- Event-driven segmentation: hidden states only change at events ---
        ev_times = pd.to_datetime(events['timestamp']).to_numpy(dtype='datetime64[ns]')
        bounds = np.unique(np.searchsorted(timestamps, ev_times))
        bounds = bounds[bounds < n_points]
        seg_starts = np.concatenate(([0], bounds)).astype(int)
        seg_ends = np.concatenate((bounds, [n_points])).astype(int)
        n_segments = len(seg_starts)

        seg_obs = np.zeros(n_segments)
        seg_len = np.zeros(n_segments)
        for j in range(n_segments):
            chunk = p_total[seg_starts[j]:seg_ends[j]]
            if len(chunk) > 0:
                seg_obs[j] = float(np.median(chunk))
                seg_len[j] = float(len(chunk))

        # Decision points per machine: segment index where each of its events
        # takes effect (the segment that starts right after the boundary).
        decisions: Dict[int, List[int]] = {c: [] for c in clusters}
        for _, ev in events.iterrows():
            c = ev['cluster']
            if c not in decisions:
                continue
            ev_time = np.datetime64(pd.Timestamp(ev['timestamp']).to_datetime64(), 'ns')
            idx = int(np.searchsorted(timestamps, ev_time))
            k = int(np.searchsorted(bounds, idx, side='left'))
            decisions[c].append(min(k + 1, n_segments - 1))
        for c in clusters:
            decisions[c] = sorted(set(decisions[c]))

        seg_state = {c: np.zeros(n_segments, dtype=int) for c in clusters}

        def sum_others(c: int, seg: int) -> float:
            return float(sum(levels[cc][seg_state[cc][seg]] for cc in clusters if cc != c))

        def next_decision(c: int, seg: int) -> int:
            for s in decisions[c]:
                if s > seg:
                    return s
            return n_segments

        # --- Greedy forward initialization ---
        chrono = sorted((s, c) for c in clusters for s in decisions[c])
        cur_state = {c: 0 for c in clusters}
        for seg, c in chrono:
            current = cur_state[c]
            best_l, best_cost = current, float('inf')
            for l in range(len(levels[c])):
                pred = base_power + sum_others(c, seg) + levels[c][l]
                cost = seg_len[seg] * (seg_obs[seg] - pred) ** 2
                if l != current:
                    cost += switch_cost
                if cost < best_cost:
                    best_cost, best_l = cost, l
            cur_state[c] = int(best_l)
            seg_state[c][seg:next_decision(c, seg)] = best_l

        # --- Block-coordinate Viterbi refinement (2 sweeps) ---
        for _ in range(2):
            for c in clusters:
                if not decisions[c]:
                    continue
                others = np.zeros(n_segments)
                for cc in clusters:
                    if cc != c:
                        others += levels[cc][seg_state[cc]]
                residual = seg_obs - base_power - others

                block_bounds = [0] + decisions[c] + [n_segments]
                n_blocks = len(block_bounds) - 1
                s_count = len(levels[c])
                emit = np.zeros((n_blocks, s_count))
                for b in range(n_blocks):
                    b0, b1 = block_bounds[b], block_bounds[b + 1]
                    if b1 <= b0:
                        continue
                    for l in range(s_count):
                        emit[b, l] = float((seg_len[b0:b1] * (residual[b0:b1] - levels[c][l]) ** 2).sum())

                # Viterbi over blocks (switch cost between consecutive blocks)
                dp = emit[0].copy()
                back = np.zeros((n_blocks, s_count), dtype=int)
                for b in range(1, n_blocks):
                    cand = dp[:, None] + np.where(
                        np.arange(s_count)[None, :] != np.arange(s_count)[:, None],
                        switch_cost, 0.0
                    )
                    back[b] = np.argmin(cand, axis=0)
                    dp = emit[b] + cand[np.arange(s_count), back[b]]
                path = np.zeros(n_blocks, dtype=int)
                path[-1] = int(np.argmin(dp))
                for b in range(n_blocks - 1, 0, -1):
                    path[b - 1] = back[b, path[b]]
                for b in range(n_blocks):
                    seg_state[c][block_bounds[b]:block_bounds[b + 1]] = path[b]

        # --- Reconstruct per-appliance power curves and state timeline ---
        for c in clusters:
            for j in range(n_segments):
                if seg_state[c][j] > 0:
                    disagg_power[c][seg_starts[j]:seg_ends[j]] = levels[c][seg_state[c][j]]

        timeline_events: List[Dict[str, Any]] = []
        for c in clusters:
            info = cluster_info[c]
            st_list = machine_states[c]['states']
            j = 0
            while j < n_segments:
                l = int(seg_state[c][j])
                j2 = j
                while j2 + 1 < n_segments and int(seg_state[c][j2 + 1]) == l:
                    j2 += 1
                if l > 0:
                    start_idx = int(seg_starts[j])
                    end_idx = min(int(seg_ends[j2]) - 1, n_points - 1)
                    start_dt = pd.Timestamp(timestamps[start_idx])
                    end_dt = pd.Timestamp(timestamps[end_idx])
                    dur_minutes = (end_dt - start_dt).total_seconds() / 60.0
                    if dur_minutes >= 0.1:
                        level_kw = float(levels[c][l])
                        state_name = st_list[l]['name'] if l < len(st_list) else f"Nivel {l}"
                        timeline_events.append({
                            "machine_id": c,
                            "machine_name": info['name'],
                            "category": info['category'],
                            "color": info['color'],
                            "start_time": start_dt.strftime('%H:%M:%S'),
                            "end_time": end_dt.strftime('%H:%M:%S'),
                            "start_timestamp": str(start_dt),
                            "end_timestamp": str(end_dt),
                            "duration_minutes": round(dur_minutes, 1),
                            "avg_power_kw": round(level_kw, 2),
                            "energy_kwh": round(level_kw * (dur_minutes / 60.0), 3),
                            "state_level": l,
                            "state_name": state_name
                        })
                j = j2 + 1
        timeline_events.sort(key=lambda t: (t['machine_id'], t['start_timestamp']))

        # --- Baseline and machine metrics ---
        sum_disagg = np.zeros(n_points)
        for c in clusters:
            sum_disagg += disagg_power[c]
        baseline_curve = np.maximum(0, p_total - sum_disagg)

        hours_per_sample = 10.0 / 3600.0  # 10 s sampling period
        total_grid_energy = float(p_total.sum() * hours_per_sample)

        machine_stats: List[Dict[str, Any]] = []
        fhmm_models: Dict[int, Any] = {}
        for c in clusters:
            info = cluster_info[c]
            c_power = disagg_power[c]
            c_energy = float(c_power.sum() * hours_per_sample)
            share_pct = (c_energy / total_grid_energy * 100.0) if total_grid_energy > 0 else 0.0

            c_timeline = [t for t in timeline_events if t['machine_id'] == c]
            total_active_mins = sum(t['duration_minutes'] for t in c_timeline)

            states_summary = []
            for si, s in enumerate(machine_states[c]['states']):
                mask = seg_state[c] == si
                minutes = float((seg_len[mask] * (10.0 / 60.0)).sum())
                kw = float(levels[c][si])
                energy = kw * minutes / 60.0
                share_active = (minutes / total_active_mins * 100.0) if total_active_mins > 0 else 0.0
                states_summary.append({
                    "level": si,
                    "name": s['name'],
                    "kw": round(kw, 2),
                    "minutes": round(minutes, 1),
                    "energy_kwh": round(energy, 3),
                    "share_pct": round(share_active, 1)
                })

            machine_stats.append({
                "id": c,
                "name": info['name'],
                "category": info['category'],
                "color": info['color'],
                "nominal_power_kw": round(info['avg_delta_p'], 2),
                "peak_current_a": round(info['avg_delta_i'], 2),
                "thd_pct": round(info['avg_thd'], 1),
                "event_count": info['count'],
                "active_minutes": round(total_active_mins, 1),
                "energy_kwh": round(c_energy, 2),
                "energy_share_pct": round(share_pct, 1),
                "status": "Activo" if total_active_mins > 0 else "Inactivo",
                "load_class": info.get('load_class', ''),
                "load_icon": info.get('load_icon', '⚙️'),
                "load_family": info.get('load_family', 'inductiva'),
                "harmonic_signature_pct": info.get('harmonic_signature_pct', 0.0),
                "q_p_ratio": info.get('q_p_ratio', 0.0),
                "custom_label": info.get('custom_label', False),
                "n_states": machine_states[c]['n_states'],
                "states": states_summary
            })
            fhmm_models[c] = {
                "levels_kw": [round(float(x), 2) for x in levels[c]],
                "n_states": machine_states[c]['n_states'],
                "states": states_summary
            }

        return disagg_power, baseline_curve, timeline_events, machine_stats, fhmm_models

    def disaggregate_load(self, df_work: pd.DataFrame, 
                          events: pd.DataFrame, 
                          cluster_info: Dict[int, Any]):
        """
        Continuous load disaggregation: Reconstructs the power time-series
        for each detected machine and operational state timeline (Gantt).
        """
        n_points = len(df_work)
        timestamps = pd.to_datetime(df_work['timestamp']).to_numpy(dtype='datetime64[ns]')
        p_total = df_work['P_total'].values
        
        clusters = sorted(list(cluster_info.keys()))
        
        # Disaggregated power array: [n_clusters, n_points]
        disagg_power = {c: np.zeros(n_points, dtype=np.float32) for c in clusters}
        timeline_events = []
        base_power = float(np.percentile(p_total, 5))
        
        for c in clusters:
            info = cluster_info[c]
            c_events = events[events['cluster'] == c].sort_values('timestamp')
            # Separate turn-ON and turn-OFF transitions: each run window starts
            # at a turn-ON and ends at the next turn-OFF of the same machine.
            c_events_on = c_events[c_events['event_type'] == 'ON']
            c_events_off = c_events[c_events['event_type'] == 'OFF']
            off_times = pd.to_datetime(c_events_off['timestamp']).to_numpy(dtype='datetime64[ns]')
            nominal_p = max(0.5, info['avg_delta_p'])
            
            for _, ev in c_events.iterrows():
                ev_time = np.datetime64(pd.Timestamp(ev['timestamp']).to_datetime64(), 'ns')
                idx = np.searchsorted(timestamps, ev_time)
                if idx >= n_points:
                    continue
                
                # Search run window until power drops
                run_len = 12 # Default 2 minutes
                for j in range(idx + 1, min(idx + 720, n_points)):
                    delta_drop = df_work['delta_P'].iloc[j]
                    if delta_drop <= -0.5 * nominal_p:
                        run_len = j - idx
                        break
                    if df_work['P_total'].iloc[j] < base_power + 0.5:
                        run_len = j - idx
                        break
                
                end_idx = min(idx + run_len, n_points)
                disagg_power[c][idx:end_idx] = nominal_p
                
                start_dt = df_work['timestamp'].iloc[idx]
                end_dt = df_work['timestamp'].iloc[end_idx - 1]
                dur_minutes = (end_dt - start_dt).total_seconds() / 60.0
                if dur_minutes >= 0.1:
                    energy_kwh = (nominal_p * (dur_minutes / 60.0))
                    timeline_events.append({
                        "machine_id": c,
                        "machine_name": info['name'],
                        "category": info['category'],
                        "color": info['color'],
                        "start_time": start_dt.strftime('%H:%M:%S'),
                        "end_time": end_dt.strftime('%H:%M:%S'),
                        "start_timestamp": str(start_dt),
                        "end_timestamp": str(end_dt),
                        "duration_minutes": round(dur_minutes, 1),
                        "avg_power_kw": round(nominal_p, 2),
                        "energy_kwh": round(energy_kwh, 3),
                        "state_level": 1,
                        "state_name": "Encendido (ON)"
                    })

        # Calculate baseline power curve
        sum_disagg = np.zeros(n_points)
        for c in clusters:
            sum_disagg += disagg_power[c]
            
        baseline_curve = np.maximum(0, p_total - sum_disagg)
        
        # Calculate machine metrics
        machine_stats = []
        total_grid_energy = float(df_work['P_total'].sum() * (10.0 / 3600.0))
        
        for c in clusters:
            info = cluster_info[c]
            c_power = disagg_power[c]
            c_energy = float(c_power.sum() * (10.0 / 3600.0))
            share_pct = (c_energy / total_grid_energy * 100.0) if total_grid_energy > 0 else 0.0
            
            c_timeline = [t for t in timeline_events if t['machine_id'] == c]
            total_active_mins = sum(t['duration_minutes'] for t in c_timeline)
            
            machine_stats.append({
                "id": c,
                "name": info['name'],
                "category": info['category'],
                "color": info['color'],
                "nominal_power_kw": round(info['avg_delta_p'], 2),
                "peak_current_a": round(info['avg_delta_i'], 2),
                "thd_pct": round(info['avg_thd'], 1),
                "event_count": info['count'],
                "active_minutes": round(total_active_mins, 1),
                "energy_kwh": round(c_energy, 2),
                "energy_share_pct": round(share_pct, 1),
                "status": "Activo" if total_active_mins > 0 else "Inactivo",
                "load_class": info.get('load_class', ''),
                "load_icon": info.get('load_icon', '⚙️'),
                "load_family": info.get('load_family', 'inductiva'),
                "harmonic_signature_pct": info.get('harmonic_signature_pct', 0.0),
                "q_p_ratio": info.get('q_p_ratio', 0.0),
                "custom_label": info.get('custom_label', False),
                "n_states": 2,
                "states": []
            })

        return disagg_power, baseline_curve, timeline_events, machine_stats

    def analyze_dataset(self, dataset_id: str, 
                        n_clusters: int = 4, 
                        algorithm: str = "kmeans",
                        current_threshold: float = 2.0,
                        power_threshold: float = 1.0,
                        use_fhmm: bool = False,
                        max_states: int = 3,
                        labels: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Executes full NILM pipeline and returns structured JSON-ready results.
        Supports binary (ON/OFF) disaggregation or multi-state FHMM modeling,
        harmonic-transient load classification and manual Ground-Truth labels.
        """
        df = self.dm.load_dataset(dataset_id)
        df_work, events = self.detect_events(df, current_threshold, power_threshold)

        nilmtk_states = self.estimate_nilmtk_power_states(df_work)
        
        events_clustered, cluster_info = self.cluster_appliances(events, n_clusters, algorithm, labels=labels)

        fhmm_models: Dict[int, Any] = {}
        if use_fhmm:
            machine_states = self.estimate_machine_states(
                events_clustered, cluster_info, max_states=max_states
            )
            disagg_power, baseline_curve, timeline, machine_stats, fhmm_models = self.disaggregate_load_fhmm(
                df_work, events_clustered, cluster_info, machine_states
            )
        else:
            disagg_power, baseline_curve, timeline, machine_stats = self.disaggregate_load(
                df_work, events_clustered, cluster_info
            )

        # Prepare 24h Hourly Activity Heatmap
        hourly_distribution = []
        for h in range(24):
            h_events = events_clustered[events_clustered['timestamp'].dt.hour == h]
            counts_by_machine = {}
            for c in cluster_info:
                counts_by_machine[f"m_{c}"] = int(len(h_events[h_events['cluster'] == c]))
            counts_by_machine['hour'] = f"{h:02d}:00"
            counts_by_machine['total'] = int(len(h_events))
            hourly_distribution.append(counts_by_machine)

        # Prepare decimation for disaggregated curves (max 1000 points)
        n = len(df_work)
        step = max(1, n // 1000)
        indices = np.arange(0, n, step)
        
        timestamps_sampled = df_work['timestamp'].iloc[indices].dt.strftime('%H:%M:%S').tolist()
        p_total_sampled = df_work['P_total'].iloc[indices].round(2).tolist()
        baseline_sampled = [round(float(baseline_curve[i]), 2) for i in indices]
        
        disagg_series = []
        for c in sorted(cluster_info.keys()):
            disagg_series.append({
                "id": c,
                "name": cluster_info[c]['name'],
                "color": cluster_info[c]['color'],
                "data": [round(float(disagg_power[c][i]), 2) for i in indices]
            })

        # Event Scatter data (Delta P vs Delta Q / Delta I vs THD)
        ev_sample = events_clustered.sample(min(600, len(events_clustered)), random_state=42) if len(events_clustered) > 600 else events_clustered
        
        events_data = []
        for _, r in ev_sample.iterrows():
            events_data.append({
                "timestamp": r['timestamp'].strftime('%H:%M:%S'),
                "time_minutes": float(r['timestamp'].hour * 60 + r['timestamp'].minute + r['timestamp'].second / 60.0),
                "current": round(float(r['I_total']), 2),
                "voltage": round(float(r['V_avg']), 2) if 'V_avg' in r else 230.0,
                "delta_p": round(float(r['delta_P']), 2),
                "delta_q": round(float(r['delta_Q']), 2) if 'delta_Q' in r else 0.0,
                "delta_i": round(float(r['delta_I']), 2),
                "thd": round(float(r['THD_avg']), 1),
                "cluster": int(r['cluster']),
                "machine_name": r['machine_name'],
                "color": r['color']
            })

        return {
            "dataset_id": dataset_id,
            "algorithm": algorithm,
            "nilmtk_available": self.nilmtk_available,
            "nilmtk_power_states_kw": [round(state, 2) for state in nilmtk_states],
            "fhmm_enabled": bool(use_fhmm),
            "max_states": int(max_states),
            "multi_state_models": {str(k): v for k, v in fhmm_models.items()},
            "n_clusters": n_clusters,
            "total_events_detected": len(events_clustered),
            "timestamps": timestamps_sampled,
            "p_total": p_total_sampled,
            "baseline": baseline_sampled,
            "disaggregated_machines": disagg_series,
            "machine_statistics": machine_stats,
            "timeline_intervals": timeline[:300],
            "hourly_activity": hourly_distribution,
            "scatter_events": events_data
        }
