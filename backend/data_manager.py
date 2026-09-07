import os
import glob
import json
import time
import pandas as pd
import numpy as np

class DataManager:
    """
    Manages loading, caching, and downsampling of electrical data from Excel/Pickle files.
    """
    def __init__(self, data_dir=None, cache_dir=None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        default_data = r"C:\Users\local\Documents\IA\Energia\Data"
        if data_dir is None:
            if os.path.exists(default_data):
                data_dir = default_data
            else:
                data_dir = os.path.join(base_dir, "Data")
        if cache_dir is None:
            cache_dir = os.path.join(os.path.dirname(data_dir), "cache")

        self.data_dir = data_dir
        self.cache_dir = cache_dir
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        self._memory_cache = {}

    def save_upload(self, filename: str, content: bytes) -> str:
        clean_name = os.path.basename(filename)
        dest_path = os.path.join(self.data_dir, clean_name)
        with open(dest_path, "wb") as f:
            f.write(content)
        slug = self.get_slug(clean_name)
        if slug in self._memory_cache:
            del self._memory_cache[slug]
        pkl_path = os.path.join(self.cache_dir, f"{slug}.pkl")
        if os.path.exists(pkl_path):
            try:
                os.remove(pkl_path)
            except OSError:
                pass
        return dest_path

    def get_slug(self, filename: str) -> str:
        base = os.path.basename(filename)
        return base.replace(".xlsx", "").replace(".xls", "").replace(".csv", "").replace(" ", "_").lower()

    # ------------------------------------------------------------------
    # Manual Ground-Truth appliance labels (Opción A - Punto 2)
    # Persisted per dataset + cluster id in backend/load_labels.json so the
    # user's custom equipment names survive restarts and re-analyses.
    # ------------------------------------------------------------------
    def _labels_file(self) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "load_labels.json")

    def _read_labels(self) -> dict:
        try:
            with open(self._labels_file(), "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write_labels(self, data: dict) -> None:
        try:
            with open(self._labels_file(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def get_labels(self, dataset_id: str) -> dict:
        """Returns {cluster_id: custom_name} for the given dataset."""
        return dict(self._read_labels().get(dataset_id, {}))

    def set_label(self, dataset_id: str, cluster_id: int, name: str) -> dict:
        """Stores (or clears, when name is empty) a custom appliance label."""
        data = self._read_labels()
        bucket = data.get(dataset_id, {})
        clean = (name or "").strip()
        if clean:
            bucket[str(int(cluster_id))] = clean
        else:
            bucket.pop(str(int(cluster_id)), None)
        if bucket:
            data[dataset_id] = bucket
        else:
            data.pop(dataset_id, None)
        self._write_labels(data)
        return dict(bucket)

    def list_datasets(self):
        files = sorted(glob.glob(os.path.join(self.data_dir, "*.xlsx")) + glob.glob(os.path.join(self.data_dir, "*.csv")))
        datasets = []
        for f in files:
            slug = self.get_slug(f)
            pkl_path = os.path.join(self.cache_dir, f"{slug}.pkl")
            is_cached = os.path.exists(pkl_path)
            
            label = os.path.basename(f).replace("coop gouge V2 ", "").replace(".xlsx", "").replace(".csv", "").capitalize()
            
            datasets.append({
                "id": slug,
                "filename": os.path.basename(f),
                "label": f"Medición {label}",
                "cached": is_cached,
                "size_mb": round(os.path.getsize(f) / (1024 * 1024), 2) if os.path.exists(f) else 0
            })
        return datasets

    def load_dataset(self, dataset_id: str) -> pd.DataFrame:
        if dataset_id in self._memory_cache:
            return self._memory_cache[dataset_id]

        pkl_path = os.path.join(self.cache_dir, f"{dataset_id}.pkl")
        if os.path.exists(pkl_path):
            try:
                df = pd.read_pickle(pkl_path)
                self._memory_cache[dataset_id] = df
                return df
            except (ValueError, TypeError, ImportError, NotImplementedError):
                # Rebuild caches created with an incompatible pandas version.
                try:
                    os.remove(pkl_path)
                except OSError:
                    pass

        # Fallback to loading original file if not cached yet
        all_files = (glob.glob(os.path.join(self.data_dir, "*.xlsx")) + 
                     glob.glob(os.path.join(self.data_dir, "*.xls")) + 
                     glob.glob(os.path.join(self.data_dir, "*.csv")))
        matching = [f for f in all_files if self.get_slug(f) == dataset_id]
        if not matching:
            raise FileNotFoundError(f"Dataset {dataset_id} no encontrado en {self.data_dir}")

        f = matching[0]
        if f.lower().endswith('.csv'):
            try:
                df = pd.read_csv(f, sep=None, engine='python')
            except Exception:
                df = pd.read_csv(f)
        else:
            df = pd.read_excel(f)
        df.columns = [str(c).strip() for c in df.columns]

        date_col = 'Fecha' if 'Fecha' in df.columns else df.columns[0]
        time_col = 'Tiempo (UTC+0)' if 'Tiempo (UTC+0)' in df.columns else df.columns[1]

        ts = pd.to_datetime(df[date_col].astype(str).str.strip() + ' ' + df[time_col].astype(str).str.strip(), errors='coerce')
        
        numeric_dict = {}
        for c in df.columns:
            if c not in [date_col, time_col]:
                numeric_dict[c] = pd.to_numeric(df[c], errors='coerce')
                
        df_clean = pd.DataFrame(numeric_dict)
        df_clean['timestamp'] = ts
        df_clean = df_clean.dropna(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)

        df_clean.to_pickle(pkl_path)
        self._memory_cache[dataset_id] = df_clean
        return df_clean

    def get_summary_stats(self, dataset_id: str):
        df = self.load_dataset(dataset_id)
        
        # Currents
        i_cols = [c for c in ['I *L1 media [A]', 'I *L2 media [A]', 'I *L3 media [A]'] if c in df.columns]
        v_cols = [c for c in ['U L1 media [V]', 'U L2 media [V]', 'U L3 media [V]'] if c in df.columns]
        pf_cols = [c for c in ['PF L1 media [---]', 'PF L2 media [---]', 'PF L3 media [---]'] if c in df.columns]
        
        # Physical 3-phase Active Power (kW) calculated from V, I and PF
        if i_cols and v_cols:
            i_tot = df[i_cols].sum(axis=1)
            v_avg = df[v_cols].mean(axis=1)
            pf_avg = df[pf_cols].abs().mean(axis=1) if pf_cols else pd.Series(0.92, index=df.index)
            # Apparent power S = 3 * V_phase * I_phase (or V_avg * I_tot)
            # Active power P (kW) = (V_avg * I_tot * pf_avg) / 1000.0
            p_tot = (v_avg * i_tot * pf_avg) / 1000.0
        else:
            p_cols = [c for c in ['P L1 media [kW]', 'P L2 media [kW]', 'P L3 media [kW]'] if c in df.columns]
            p_tot = df[p_cols].abs().sum(axis=1) if p_cols else pd.Series(0, index=df.index)
            i_tot = pd.Series(0, index=df.index)
            pf_avg = pd.Series(0.92, index=df.index)

        # Sampling step
        time_diffs = df['timestamp'].diff().dt.total_seconds().fillna(10)
        hours = time_diffs / 3600.0
        energy_kwh = float((p_tot * hours).sum())
        
        peak_p = float(p_tot.max())
        min_p = float(p_tot.min())
        avg_p = float(p_tot.mean())
        mean_pf = float(pf_avg.mean())
        
        total_samples = len(df)
        start_time = str(df['timestamp'].iloc[0])
        end_time = str(df['timestamp'].iloc[-1])
        duration_hours = float((df['timestamp'].iloc[-1] - df['timestamp'].iloc[0]).total_seconds() / 3600.0)

        i_max = float(i_tot.max()) if len(i_tot) > 0 else 0.0

        return {
            "dataset_id": dataset_id,
            "start_time": start_time,
            "end_time": end_time,
            "duration_hours": round(duration_hours, 2),
            "samples": total_samples,
            "total_energy_kwh": round(energy_kwh, 2),
            "peak_power_kw": round(peak_p, 2),
            "min_power_kw": round(min_p, 2),
            "avg_power_kw": round(avg_p, 2),
            "avg_power_factor": round(mean_pf, 3),
            "max_current_a": round(i_max, 2)
        }

    def get_decimated_timeseries(self, dataset_id: str, max_points: int = 1200):
        """Downsamples time-series data using min-max peak preserving decimation"""
        df = self.load_dataset(dataset_id)
        n = len(df)
        
        step = max(1, n // max_points)
        indices = np.arange(0, n, step)
        if indices[-1] != n - 1:
            indices = np.append(indices, n - 1)
            
        sub_df = df.iloc[indices].copy()
        
        timestamps = sub_df['timestamp'].dt.strftime('%H:%M:%S').tolist()
        timestamps_full = sub_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S').tolist()

        i_l1 = sub_df['I *L1 media [A]'].fillna(0).round(2).tolist() if 'I *L1 media [A]' in sub_df else []
        i_l2 = sub_df['I *L2 media [A]'].fillna(0).round(2).tolist() if 'I *L2 media [A]' in sub_df else []
        i_l3 = sub_df['I *L3 media [A]'].fillna(0).round(2).tolist() if 'I *L3 media [A]' in sub_df else []
        
        v_l1 = sub_df['U L1 media [V]'].fillna(0).round(1).tolist() if 'U L1 media [V]' in sub_df else []
        v_l2 = sub_df['U L2 media [V]'].fillna(0).round(1).tolist() if 'U L2 media [V]' in sub_df else []
        v_l3 = sub_df['U L3 media [V]'].fillna(0).round(1).tolist() if 'U L3 media [V]' in sub_df else []

        pf_l1 = sub_df['PF L1 media [---]'].abs().fillna(0.92) if 'PF L1 media [---]' in sub_df else pd.Series(0.92, index=sub_df.index)
        pf_l2 = sub_df['PF L2 media [---]'].abs().fillna(0.92) if 'PF L2 media [---]' in sub_df else pd.Series(0.92, index=sub_df.index)
        pf_l3 = sub_df['PF L3 media [---]'].abs().fillna(0.92) if 'PF L3 media [---]' in sub_df else pd.Series(0.92, index=sub_df.index)

        # Consistent 3-phase Active Power (kW)
        if 'I *L1 media [A]' in sub_df and 'U L1 media [V]' in sub_df:
            p_l1 = ((sub_df['U L1 media [V]'] * sub_df['I *L1 media [A]'] * pf_l1) / 1000.0).round(2).tolist()
            p_l2 = ((sub_df['U L2 media [V]'] * sub_df['I *L2 media [A]'] * pf_l2) / 1000.0).round(2).tolist()
            p_l3 = ((sub_df['U L3 media [V]'] * sub_df['I *L3 media [A]'] * pf_l3) / 1000.0).round(2).tolist()
            p_tot = [round(p_l1[i] + p_l2[i] + p_l3[i], 2) for i in range(len(p_l1))]
            i_tot = (sub_df['I *L1 media [A]'] + sub_df['I *L2 media [A]'] + sub_df['I *L3 media [A]']).round(2).tolist()
        else:
            p_tot = sub_df['P Σ media [kW]'].abs().fillna(0).round(2).tolist()
            p_l1, p_l2, p_l3 = [], [], []
            i_tot = []

        pf_avg = ((pf_l1 + pf_l2 + pf_l3) / 3.0).round(3).tolist()

        thd_i_l1 = sub_df['THD I L1 media [%]'].fillna(0).round(1).tolist() if 'THD I L1 media [%]' in sub_df else []
        thd_i_l2 = sub_df['THD I L2 media [%]'].fillna(0).round(1).tolist() if 'THD I L2 media [%]' in sub_df else []
        thd_i_l3 = sub_df['THD I L3 media [%]'].fillna(0).round(1).tolist() if 'THD I L3 media [%]' in sub_df else []

        return {
            "timestamps": timestamps,
            "timestamps_full": timestamps_full,
            "p_total": p_tot,
            "p_l1": p_l1,
            "p_l2": p_l2,
            "p_l3": p_l3,
            "pf_total": pf_avg,
            "i_l1": i_l1,
            "i_l2": i_l2,
            "i_l3": i_l3,
            "i_total": i_tot,
            "v_l1": v_l1,
            "v_l2": v_l2,
            "v_l3": v_l3,
            "thd_i_l1": thd_i_l1,
            "thd_i_l2": thd_i_l2,
            "thd_i_l3": thd_i_l3
        }

    def get_harmonics_summary(self, dataset_id: str):
        df = self.load_dataset(dataset_id)
        
        # Harmonic orders 1 to 25
        orders = [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25]
        v_harmonics = []
        i_harmonics = []
        
        for h in orders:
            col_v1 = f"U H {h} L1 media [V]"
            col_v2 = f"U H {h} L2 media [V]"
            col_v3 = f"U H {h} L3 media [V]"
            v_val = 0.0
            v_cols = [c for c in [col_v1, col_v2, col_v3] if c in df.columns]
            if v_cols:
                v_val = float(df[v_cols].mean().mean())
            v_harmonics.append(round(v_val, 2))

            col_i1 = f"I H {h} L1 media [A]"
            col_i2 = f"I H {h} L2 media [A]"
            col_i3 = f"I H {h} L3 media [A]"
            
            i_val = 0.0
            i_cols = [c for c in [col_i1, col_i2, col_i3] if c in df.columns]
            if i_cols:
                i_val = float(df[i_cols].mean().mean())
            i_harmonics.append(round(i_val, 2))

        return {
            "harmonic_orders": [f"H{h}" for h in orders],
            "voltage_harmonics_v": v_harmonics,
            "current_harmonics_a": i_harmonics
        }
