import pandas as pd
import numpy as np
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
                           custom_labels: dict = None) -> Tuple[pd.DataFrame, Dict[int, Any]]:
        """
        Applies Machine Learning clustering (K-Means, GMM, or DBSCAN)
        on multi-dimensional electrical features.
        Supports Ground-Truth manual label overrides for identified clusters.
        """
        if len(events) == 0:
            events['cluster'] = []
            events['machine_name'] = []
            events['color'] = []
            events['custom_label'] = []
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

            # Check Ground-Truth manual label override
            is_custom = False
            custom_name = None
            if custom_labels and isinstance(custom_labels, dict):
                custom_name = custom_labels.get(str(c)) or custom_labels.get(int(c)) or custom_labels.get(c)

            if custom_name and str(custom_name).strip():
                name = str(custom_name).strip()
                category = "Equipo Personalizado (Ground Truth)"
                is_custom = True
            else:
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
                "custom_label": is_custom
            }

        events['machine_name'] = events['cluster'].map(lambda c: cluster_info[c]['name'])
        events['color'] = events['cluster'].map(lambda c: cluster_info[c]['color'])
        events['category'] = events['cluster'].map(lambda c: cluster_info[c]['category'])
        events['custom_label'] = events['cluster'].map(lambda c: cluster_info[c].get('custom_label', False))

        return events, cluster_info

    def disaggregate_load(self, df_work: pd.DataFrame, 
                          events: pd.DataFrame, 
                          cluster_info: Dict[int, Any]):
        """
        Continuous load disaggregation: Reconstructs the power time-series
        for each detected machine using strict ON-OFF event pairing and operational state timeline (Gantt).
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
            
            # Separate turn-ON and turn-OFF transitions
            c_events_on = c_events[c_events['event_type'] == 'ON'].reset_index(drop=True)
            c_events_off = c_events[c_events['event_type'] == 'OFF'].reset_index(drop=True)
            nominal_p = max(0.5, info['avg_delta_p'])
            
            used_off_indices = set()
            
            # Edge case: Machine already running at t=0 before first ON event
            if len(c_events_off) > 0:
                first_off_time = pd.Timestamp(c_events_off['timestamp'].iloc[0])
                first_on_time = pd.Timestamp(c_events_on['timestamp'].iloc[0]) if len(c_events_on) > 0 else None
                if first_on_time is None or first_off_time < first_on_time:
                    if p_total[0] > base_power + 0.3 * nominal_p:
                        off_idx = min(n_points, np.searchsorted(timestamps, np.datetime64(first_off_time.to_datetime64(), 'ns')))
                        if off_idx > 0:
                            disagg_power[c][0:off_idx] = nominal_p
                            start_dt = df_work['timestamp'].iloc[0]
                            end_dt = df_work['timestamp'].iloc[off_idx - 1]
                            dur_minutes = (end_dt - start_dt).total_seconds() / 60.0
                            if dur_minutes >= 0.1:
                                energy_kwh = nominal_p * (dur_minutes / 60.0)
                                timeline_events.append({
                                    "machine_id": c,
                                    "machine_name": info['name'],
                                    "category": info['category'],
                                    "color": info['color'],
                                    "start_time": start_dt.strftime('%H:%M:%S'),
                                    "start_timestamp": str(start_dt),
                                    "end_timestamp": str(end_dt),
                                    "duration_minutes": round(dur_minutes, 1),
                                    "avg_power_kw": round(nominal_p, 2),
                                    "energy_kwh": round(energy_kwh, 3)
                                })
                            used_off_indices.add(0)

            # Pair each ON event with its corresponding OFF transition
            for on_i, ev_on in c_events_on.iterrows():
                ev_on_time = np.datetime64(pd.Timestamp(ev_on['timestamp']).to_datetime64(), 'ns')
                idx_on = np.searchsorted(timestamps, ev_on_time)
                if idx_on >= n_points:
                    continue
                
                # If this ON event falls inside an already active window for this machine, skip duplicate
                if disagg_power[c][idx_on] > 0:
                    continue

                # Determine ceiling: the next ON event for the same machine
                if on_i + 1 < len(c_events_on):
                    next_on_time = np.datetime64(pd.Timestamp(c_events_on['timestamp'].iloc[on_i + 1]).to_datetime64(), 'ns')
                    idx_next_on = min(n_points, np.searchsorted(timestamps, next_on_time))
                else:
                    idx_next_on = n_points

                # Look for a candidate OFF event between idx_on and idx_next_on
                matched_off_idx = None
                best_off_row_idx = None
                
                for off_i, ev_off in c_events_off.iterrows():
                    if off_i in used_off_indices:
                        continue
                    ev_off_time = np.datetime64(pd.Timestamp(ev_off['timestamp']).to_datetime64(), 'ns')
                    idx_off = np.searchsorted(timestamps, ev_off_time)
                    if idx_on < idx_off <= idx_next_on:
                        matched_off_idx = idx_off
                        best_off_row_idx = off_i
                        break
                
                if matched_off_idx is not None:
                    end_idx = matched_off_idx
                    used_off_indices.add(best_off_row_idx)
                else:
                    # If no explicit OFF event was detected in cluster, search signal for power drop
                    # without an arbitrary 2-hour cap (extends up to idx_next_on)
                    end_idx = idx_next_on
                    for j in range(idx_on + 1, idx_next_on):
                        delta_drop = df_work['delta_P'].iloc[j]
                        if delta_drop <= -0.5 * nominal_p:
                            end_idx = j
                            break
                        if df_work['P_total'].iloc[j] < base_power + 0.3 * nominal_p:
                            end_idx = j
                            break

                end_idx = max(idx_on + 1, min(end_idx, n_points))
                disagg_power[c][idx_on:end_idx] = nominal_p
                
                start_dt = df_work['timestamp'].iloc[idx_on]
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
                        "start_timestamp": str(start_dt),
                        "end_timestamp": str(end_dt),
                        "duration_minutes": round(dur_minutes, 1),
                        "avg_power_kw": round(nominal_p, 2),
                        "energy_kwh": round(energy_kwh, 3)
                    })

        # Calculate baseline power curve
        sum_disagg = np.zeros(n_points, dtype=np.float32)
        for c in clusters:
            sum_disagg += disagg_power[c]
            
        baseline_curve = np.maximum(0, p_total - sum_disagg)
        
        # Sort timeline events chronologically
        timeline_events.sort(key=lambda x: x['start_timestamp'])
        
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
                "status": "Active" if total_active_mins > 0 else "Inactive",
                "custom_label": bool(info.get('custom_label', False))
            })

        return disagg_power, baseline_curve, timeline_events, machine_stats

    def estimate_machine_states(self, df_work, cluster_info, events, max_states=3):
        """Estima niveles de potencia para cada maquina usando K-Means con validacion por silueta."""
        machine_states = {}
        
        for c in cluster_info:
            sub = events[events['cluster'] == c]
            if len(sub) < 4:
                nominal = max(0.5, cluster_info[c]['avg_delta_p'])
                machine_states[c] = [nominal]
                continue
            
            power_jumps = sub['delta_P'].abs().values
            power_jumps = power_jumps[power_jumps > 0.1]
            
            if len(power_jumps) < 6:
                nominal = max(0.5, cluster_info[c]['avg_delta_p'])
                machine_states[c] = [nominal]
                continue
            
            power_reshaped = power_jumps.reshape(-1, 1)
            max_k = min(max_states, max(1, len(power_jumps) // 3))
            
            best_score = -1
            best_states = None
            
            # Try k=2..max_k first (multi-state detection)
            for k in range(2, max_k + 1):
                if len(power_jumps) < k * 2:
                    continue
                try:
                    km = KMeans(n_clusters=k, random_state=42, n_init=10)
                    labels = km.fit_predict(power_reshaped)
                    unique = set(labels)
                    if len(unique) >= 2 and len(power_jumps) >= k * 2:
                        score = silhouette_score(power_reshaped, labels)
                        if score > best_score:
                            best_score = score
                            best_k = k
                            states = sorted([float(cent) for cent in km.cluster_centers_.flatten()])
                            best_states = states
                except Exception:
                    continue
            
            # Fallback: single state (mean) if no multi-state model found
            if best_states is None or len(best_states) < 2:
                best_states = [float(np.mean(power_jumps))]
            
            machine_states[c] = best_states
        
        return machine_states

    def disaggregate_load_fhmm(self, df_work, events, cluster_info, machine_states):
        """Inferencia MAP factorial para desagregacion multi-estado."""
        n_points = len(df_work)
        timestamps = pd.to_datetime(df_work['timestamp']).to_numpy(dtype='datetime64[ns]')
        p_total = df_work['P_total'].values
        clusters = sorted(list(cluster_info.keys()))
        disagg_power = {c: np.zeros(n_points, dtype=np.float32) for c in clusters}
        timeline_events = []
        machine_stats = []
        
        for c in clusters:
            info = cluster_info[c]
            states = machine_states.get(c, [info['avg_delta_p']])
            state_levels = sorted(states)
            c_events = events[events['cluster'] == c].sort_values('timestamp')
            if len(c_events) == 0:
                machine_stats.append({
                    "id": c, "name": info['name'], "category": info['category'],
                    "color": info['color'], "nominal_power_kw": round(info['avg_delta_p'], 2),
                    "peak_current_a": round(info['avg_delta_i'], 2), "thd_pct": round(info['avg_thd'], 1),
                    "event_count": info['count'], "active_minutes": 0.0, "energy_kwh": 0.0,
                    "energy_share_pct": 0.0, "status": "Inactivo",
                    "states": [{"name": "Apagado", "level": 0, "kw": 0.0, "minutes": 0.0, "energy_kwh": 0.0, "share_pct": 0.0}],
                    "n_states": 1, "state_count": 1,
                    "load_class": "Desconocido", "harmonic_signature": 0.0,
                    "custom_label": bool(info.get('custom_label', False))
                })
                continue
            
            # Greedy initialization with OFF event recognition
            assigned_states = np.zeros(len(c_events), dtype=int)
            for i, (_, ev) in enumerate(c_events.iterrows()):
                if ev.get('event_type') == 'OFF':
                    assigned_states[i] = -1  # Negative indicates OFF state (0 kW)
                else:
                    power_val = abs(float(ev['delta_P']))
                    best_state = 0
                    best_dist = float('inf')
                    for si, level in enumerate(state_levels):
                        if level > 0:
                            dist = abs(power_val - level)
                            if dist < best_dist:
                                best_dist = dist
                                best_state = si
                    assigned_states[i] = best_state
            
            event_times = pd.to_datetime(c_events['timestamp']).to_numpy(dtype='datetime64[ns]')
            segment_starts, segment_ends, segment_states = [], [], []
            for i, ev_time in enumerate(event_times):
                idx = np.searchsorted(timestamps, ev_time)
                if idx >= n_points:
                    continue
                next_idx = np.searchsorted(timestamps, event_times[i + 1]) if i + 1 < len(event_times) else n_points
                segment_starts.append(idx)
                segment_ends.append(next_idx)
                segment_states.append(assigned_states[i])
            
            self._build_fhmm_segments(df_work, segments_start=segment_starts, segments_end=segment_ends, seg_states=segment_states, state_levels=state_levels, disagg_power=disagg_power, c=c, timeline_events=timeline_events, info=info)
            self._build_fhmm_stats(df_work, c=c, info=info, disagg_power=disagg_power, state_levels=state_levels, timeline_events=timeline_events, machine_stats=machine_stats)

        sum_disagg = np.zeros(n_points, dtype=np.float32)
        for c in clusters:
            sum_disagg += disagg_power[c]
        baseline_curve = np.maximum(0, p_total - sum_disagg)
        timeline_events.sort(key=lambda x: x['start_timestamp'])
        return disagg_power, baseline_curve, timeline_events, machine_stats

    def _build_fhmm_segments(self, df_work, segments_start, segments_end, seg_states, state_levels, disagg_power, c, timeline_events, info):
        """Build timeline segments for FHMM multi-state disaggregation."""
        n_points = len(df_work)
        for seg_i, (start, end, state_idx) in enumerate(zip(segments_start, segments_end, seg_states)):
            if start >= end:
                continue
            if state_idx < 0:
                # Machine turned OFF: 0 kW
                disagg_power[c][start:end] = 0.0
                continue

            power_level = state_levels[state_idx] if state_idx < len(state_levels) else state_levels[-1]
            disagg_power[c][start:end] = power_level
            
            start_dt = df_work['timestamp'].iloc[start]
            end_dt = df_work['timestamp'].iloc[end - 1]
            dur_minutes = (end_dt - start_dt).total_seconds() / 60.0
            
            if dur_minutes >= 0.1 and power_level > 0.1:
                energy_kwh = (power_level * (dur_minutes / 60.0))
                state_name = f"Estado {state_idx + 1}"
                if state_idx == 0 and power_level < 1.0:
                    state_name = "Apagado"
                elif state_idx == len(state_levels) - 1:
                    state_name = "Plena Carga"
                elif state_idx > 0:
                    state_name = "Marcha Parcial"
                
                timeline_events.append({
                    "machine_id": c,
                    "machine_name": info['name'],
                    "category": info['category'],
                    "color": info['color'],
                    "start_time": start_dt.strftime('%H:%M:%S'),
                    "start_timestamp": str(start_dt),
                    "end_timestamp": str(end_dt),
                    "duration_minutes": round(dur_minutes, 1),
                    "avg_power_kw": round(power_level, 2),
                    "energy_kwh": round(energy_kwh, 3),
                    "state": state_name,
                    "state_level": state_idx
                })

    def _build_fhmm_stats(self, df_work, c, info, disagg_power, state_levels, timeline_events, machine_stats):
        """Build machine statistics with multi-state information for FHMM."""
        total_grid_energy = float(df_work['P_total'].sum() * (10.0 / 3600.0))
        c_power = disagg_power[c]
        c_energy = float(c_power.sum() * (10.0 / 3600.0))
        share_pct = (c_energy / total_grid_energy * 100.0) if total_grid_energy > 0 else 0.0
        
        c_timeline = [t for t in timeline_events if t['machine_id'] == c]
        total_active_mins = sum(t['duration_minutes'] for t in c_timeline)
        
        state_stats = []
        total_state_minutes = sum(
            sum(t['duration_minutes'] for t in [e for e in c_timeline if e.get('state_level') == si])
            for si, _ in enumerate(state_levels)
        ) or 1.0
        
        for si, level in enumerate(state_levels):
            if level <= 0:
                state_stats.append({"name": "Apagado", "level": 0, "kw": 0.0, "minutes": 0.0, "energy_kwh": 0.0, "share_pct": 0.0})
                continue
            state_events = [t for t in c_timeline if t.get('state_level') == si]
            state_minutes = sum(t['duration_minutes'] for t in state_events)
            state_energy = sum(t['energy_kwh'] for t in state_events)
            if si == 0 and level < 1.0:
                state_name = "Apagado"
            elif si == len(state_levels) - 1 and len(state_levels) > 1:
                state_name = "Plena Carga"
            elif si > 0:
                state_name = "Marcha Parcial"
            else:
                state_name = "Estado 1"
            state_stats.append({
                "name": state_name,
                "level": si,
                "kw": round(level, 2),
                "minutes": round(state_minutes, 1),
                "energy_kwh": round(state_energy, 2),
                "share_pct": round(state_minutes / total_state_minutes * 100.0, 1)
            })
        
        delta_i = info['avg_delta_i']
        avg_thd = info['avg_thd']
        avg_p = info['avg_delta_p']
        
        if avg_thd >= 35.0 or info.get('harm_ratio_pct', 0) > 5:
            load_class = "Eletronica de Potencia (VFD/Rectificador)"
        elif delta_i >= 20.0 and avg_p >= 15.0:
            load_class = "Motor Inductivo (Arranque DOL)"
        elif avg_p >= 5.0:
            load_class = "Motor / Carga Mixta"
        else:
            load_class = "Carga Resistiva"
        
        machine_stats.append({
            "id": c, "name": info['name'], "category": info['category'],
            "color": info['color'], "nominal_power_kw": round(info['avg_delta_p'], 2),
            "peak_current_a": round(info['avg_delta_i'], 2), "thd_pct": round(info['avg_thd'], 1),
            "event_count": info['count'], "active_minutes": round(total_active_mins, 1),
            "energy_kwh": round(c_energy, 2), "energy_share_pct": round(share_pct, 1),
            "status": "Activo" if total_active_mins > 0 else "Inactivo",
            "states": state_stats, "n_states": len(state_levels),
            "state_count": len(state_levels),
            "load_class": load_class, "harmonic_signature": round(info.get('harm_ratio_pct', 0), 1),
            "custom_label": bool(info.get('custom_label', False))
        })

    def analyze_dataset(self, dataset_id: str,
                        n_clusters: int = 4,
                        algorithm: str = "kmeans",
                        current_threshold: float = 2.0,
                        power_threshold: float = 1.0,
                        use_fhmm: bool = False,
                        max_states: int = 3,
                        labels: dict = None) -> Dict[str, Any]:
        """
        Executes full NILM pipeline and returns structured JSON-ready results.
        """
        if labels is None:
            labels = self.dm.get_labels(dataset_id)

        df = self.dm.load_dataset(dataset_id)
        df_work, events = self.detect_events(df, current_threshold, power_threshold)

        nilmtk_states = self.estimate_nilmtk_power_states(df_work)
        
        events_clustered, cluster_info = self.cluster_appliances(
            events, n_clusters=n_clusters, algorithm=algorithm, custom_labels=labels
        )
        
        if use_fhmm and len(events_clustered) > 0:
            machine_states = self.estimate_machine_states(df_work, cluster_info, events_clustered, max_states)
            disagg_power, baseline_curve, timeline, machine_stats = self.disaggregate_load_fhmm(
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
            "n_clusters": n_clusters,
            "total_events_detected": len(events_clustered),
            "timestamps": timestamps_sampled,
            "p_total": p_total_sampled,
            "baseline": baseline_sampled,
            "disaggregated_machines": disagg_series,
            "machine_statistics": machine_stats,
            "timeline_intervals": timeline[:300],
            "hourly_activity": hourly_distribution,
            "scatter_events": events_data,
            "fhmm_enabled": use_fhmm,
            "multi_state_models": {
                str(c): {
                    "levels_kw": [s.get('kw', 0.0) for s in stat.get('states', [])],
                    "n_states": stat.get('n_states', 1),
                    "states": stat.get('states', [])
                }
                for c, stat in zip(sorted(cluster_info.keys()), machine_stats) if use_fhmm
            } if use_fhmm else {}
        }
