import numpy as np
import pandas as pd
from sklearn.cluster import KMeans, DBSCAN
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler
from typing import Dict, List, Any, Optional

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

        # Step differences (deltas)
        df_work['delta_P'] = df_work['P_total'].diff().fillna(0)
        df_work['delta_Q'] = df_work['Q_total'].diff().fillna(0)
        df_work['delta_I'] = df_work['I_total'].diff().fillna(0)
        
        # Filter turn-on events (positive transitions)
        mask_on = (df_work['delta_I'] >= current_threshold) | (df_work['delta_P'] >= power_threshold)
        events = df_work[mask_on].copy()
        
        # Additional features
        events['hour_of_day'] = events['timestamp'].dt.hour + events['timestamp'].dt.minute / 60.0
        
        return df_work, events

    def cluster_appliances(self, events: pd.DataFrame, 
                           n_clusters: int = 4, 
                           algorithm: str = "kmeans") -> pd.DataFrame:
        """
        Applies Machine Learning clustering (K-Means, GMM, or DBSCAN)
        on multi-dimensional electrical features.
        """
        if len(events) == 0:
            events['cluster'] = []
            events['machine_name'] = []
            events['color'] = []
            return events, {}

        # Refined feature vector: delta_P, delta_I, THD_avg, delta_Q
        features = ['delta_P', 'delta_I', 'THD_avg', 'delta_Q']
        X = events[features].fillna(0).values
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        n_samples = len(events)
        effective_k = min(n_clusters, max(1, n_samples // 2))

        if algorithm.lower() == 'gmm':
            model = GaussianMixture(n_components=effective_k, random_state=42, max_iter=200)
            labels = model.fit_predict(X_scaled)
        elif algorithm.lower() == 'dbscan':
            model = DBSCAN(eps=0.75, min_samples=4)
            labels = model.fit_predict(X_scaled)
            unique_labels = sorted(list(set(labels)))
            label_map = {l: i for i, l in enumerate(unique_labels)}
            labels = np.array([label_map[l] for l in labels])
        else: # Default KMeans
            model = KMeans(n_clusters=effective_k, random_state=42, n_init=10)
            labels = model.fit_predict(X_scaled)

        events['cluster'] = labels

        colors = [
            "#3B82F6", "#10B981", "#F59E0B", "#EF4444", 
            "#8B5CF6", "#EC4899", "#06B6D4", "#84CC16"
        ]

        cluster_info = {}
        # Sort clusters by average power descending
        raw_clusters = sorted(events['cluster'].unique())
        avg_powers = {c: float(events[events['cluster'] == c]['delta_P'].mean()) for c in raw_clusters}
        sorted_clusters = sorted(raw_clusters, key=lambda c: avg_powers[c], reverse=True)

        for rank, c in enumerate(sorted_clusters):
            sub = events[events['cluster'] == c]
            avg_p = float(sub['delta_P'].mean())
            avg_i = float(sub['delta_I'].mean())
            avg_thd = float(sub['THD_avg'].mean())
            avg_q = float(sub['delta_Q'].mean()) if 'delta_Q' in sub else 0.0

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
                "count": len(sub)
            }

        events['machine_name'] = events['cluster'].map(lambda c: cluster_info[c]['name'])
        events['color'] = events['cluster'].map(lambda c: cluster_info[c]['color'])
        events['category'] = events['cluster'].map(lambda c: cluster_info[c]['category'])

        return events, cluster_info

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
                        "energy_kwh": round(energy_kwh, 3)
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
                "status": "Activo" if total_active_mins > 0 else "Inactivo"
            })

        return disagg_power, baseline_curve, timeline_events, machine_stats

    def analyze_dataset(self, dataset_id: str, 
                        n_clusters: int = 4, 
                        algorithm: str = "kmeans",
                        current_threshold: float = 2.0,
                        power_threshold: float = 1.0) -> Dict[str, Any]:
        """
        Executes full NILM pipeline and returns structured JSON-ready results.
        """
        df = self.dm.load_dataset(dataset_id)
        df_work, events = self.detect_events(df, current_threshold, power_threshold)

        nilmtk_states = self.estimate_nilmtk_power_states(df_work)
        
        events_clustered, cluster_info = self.cluster_appliances(events, n_clusters, algorithm)
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
            "scatter_events": events_data
        }
