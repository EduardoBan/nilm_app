import os
import glob
import json
import time
import tempfile
import threading
import pandas as pd
import numpy as np

VALID_EXTENSIONS = (".xlsx", ".xls", ".csv")

class DataManager:
    """
    Manages loading, caching, and downsampling of electrical data from Excel/Pickle files.
    """
    def __init__(self, data_dir=None, cache_dir=None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # En la distribucion portable el ejecutable fija NILM_APP_HOME; en
        # desarrollo se conserva la carpeta de datos historica si existe.
        app_home = os.environ.get("NILM_APP_HOME", base_dir)
        default_data = os.path.join(app_home, "Data")
        bundled_data = os.path.join(base_dir, "Data")
        if not os.path.exists(default_data) and os.path.exists(bundled_data):
            default_data = bundled_data
        if data_dir is None:
            data_dir = default_data if os.path.exists(default_data) else os.path.join(app_home, "Data")
        if cache_dir is None:
            cache_dir = os.path.join(app_home, "cache")

        self.data_dir = data_dir
        self.cache_dir = cache_dir
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        self._memory_cache = {}
        self._memory_order = []  # LRU: evita crecimiento infinito de RAM
        self._memory_limit = 4

    def _remember(self, dataset_id: str, df) -> None:
        """Guarda en caché RAM con política LRU (máx. _memory_limit datasets)."""
        if dataset_id in self._memory_cache:
            self._memory_order.remove(dataset_id)
        self._memory_cache[dataset_id] = df
        self._memory_order.append(dataset_id)
        while len(self._memory_order) > self._memory_limit:
            oldest = self._memory_order.pop(0)
            self._memory_cache.pop(oldest, None)

    def save_upload(self, filename: str, content: bytes) -> str:
        clean_name = os.path.basename(filename)
        dest_path = os.path.join(self.data_dir, clean_name)
        with open(dest_path, "wb") as f:
            f.write(content)
        slug = self.get_slug(clean_name)
        if slug in self._memory_cache:
            del self._memory_cache[slug]
        if slug in self._memory_order:
            self._memory_order.remove(slug)
        pkl_path = os.path.join(self.cache_dir, f"{slug}.pkl")
        if os.path.exists(pkl_path):
            try:
                os.remove(pkl_path)
            except OSError:
                pass
        return dest_path

    def get_slug(self, filename: str) -> str:
        base = os.path.basename(filename).strip()
        # Insensible a mayúsculas (.XLSX/.XLS/.CSV) y a espacios
        low = base.lower()
        for ext in VALID_EXTENSIONS:
            if low.endswith(ext):
                base = base[: -len(ext)]
                break
        return base.replace(" ", "_").lower()

    # ------------------------------------------------------------------
    # Manual Ground-Truth appliance labels (Opción A - Punto 2)
    # Persisted per dataset + cluster id in backend/load_labels.json so the
    # user's custom equipment names survive restarts and re-analyses.
    # ------------------------------------------------------------------
    def _labels_file(self) -> str:
        # Las etiquetas son estado de usuario: en modo congelado deben vivir
        # junto a la aplicacion, no en el directorio temporal de PyInstaller.
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_home = os.environ.get("NILM_APP_HOME", base_dir)
        return os.path.join(app_home, "backend", "load_labels.json")

    def _read_labels(self) -> dict:
        try:
            with open(self._labels_file(), "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    # + hilo: protege load_labels.json ante POST concurrentes.
    _labels_lock = threading.Lock()

    def _write_labels(self, data: dict) -> None:
        """Escritura atómica (tmp + rename) para no corromper ante cortes/concurrentes."""
        path = self._labels_file()
        try:
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, path)
            except BaseException:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise
        except OSError:
            pass

    def get_labels(self, dataset_id: str) -> dict:
        """Returns {cluster_id: custom_name} for the given dataset."""
        return dict(self._read_labels().get(dataset_id, {}))

    def set_label(self, dataset_id: str, cluster_id: int, name: str) -> dict:
        """Stores (or clears, when name is empty) a custom appliance label."""
        clean = (name or "").strip()
        if clean and len(clean) > 80:
            raise ValueError("El nombre personalizado no puede superar 80 caracteres")
        with self._labels_lock:
            data = self._read_labels()
            bucket = data.get(dataset_id, {})
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

    def clear_labels(self, dataset_id: str) -> dict:
        """Clears all manual Ground-Truth labels for the dataset."""
        with self._labels_lock:
            data = self._read_labels()
            data.pop(dataset_id, None)
            self._write_labels(data)
            return {}

    def list_datasets(self):
        files = sorted(f for ext in VALID_EXTENSIONS
                       for f in glob.glob(os.path.join(self.data_dir, f"*{ext}")))
        datasets = []
        for f in files:
            slug = self.get_slug(f)
            pkl_path = os.path.join(self.cache_dir, f"{slug}.pkl")
            is_cached = os.path.exists(pkl_path)

            base = os.path.basename(f)
            label = base
            for ext in VALID_EXTENSIONS:
                if label.lower().endswith(ext):
                    label = label[: -len(ext)]
                    break
            label = label.replace("coop gouge V2 ", "").replace("_", " ").strip().capitalize()
            
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
                self._remember(dataset_id, df)
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
        self._remember(dataset_id, df_clean)
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

    # ------------------------------------------------------------------
    # MEJORA #21: Diagnostico de Calidad Energetica
    # Tension (±10%), desequilibrio (EN 50160), corriente de neutro,
    # K-factor (IEEE C57.110), THD U/I y eventos de sag/swell.
    # ------------------------------------------------------------------
    def get_power_quality(self, dataset_id: str, max_points: int = 600):
        df = self.load_dataset(dataset_id)
        if 'timestamp' not in df.columns:
            raise ValueError("El dataset no tiene columna timestamp")

        df = df.sort_values('timestamp').reset_index(drop=True)

        v_cols = [c for c in ['U L1 media [V]', 'U L2 media [V]', 'U L3 media [V]']
                  if c in df.columns]
        i_cols = [c for c in ['I *L1 media [A]', 'I *L2 media [A]', 'I *L3 media [A]']
                  if c in df.columns]

        # Tension nominal comercial mas cercana a la mediana medida
        v_avg_phase = df[v_cols].mean(axis=1) if v_cols else pd.Series(230.0, index=df.index)
        nominal_candidates = [230.0, 220.0, 240.0, 208.0, 277.0, 400.0, 415.0, 480.0]
        vnom = float(min(nominal_candidates,
                         key=lambda n: abs(n - float(np.median(v_avg_phase)))))

        def _phase_stats(col: str) -> dict:
            if col in df.columns:
                s = pd.to_numeric(df[col], errors='coerce').dropna()
                if len(s):
                    return {"mean": round(float(s.mean()), 2),
                            "min": round(float(s.min()), 2),
                            "max": round(float(s.max()), 2)}
            return {"mean": 0.0, "min": 0.0, "max": 0.0}

        voltage_stats = {
            "l1": _phase_stats('U L1 media [V]'),
            "l2": _phase_stats('U L2 media [V]'),
            "l3": _phase_stats('U L3 media [V]')
        }

        # Desvio de tension por muestra (todas las fases): EN 50160 evalua el
        # 95% de las muestras, no el extremo absoluto. Un unico transitorio de
        # sag no debe marcar el registro completo como incumplimiento, pero si
        # debe verse en la nota (P95 + maximo + muestras fuera de +-10%).
        if v_cols:
            v_num = df[v_cols].apply(pd.to_numeric, errors='coerce')
            v_dev_stack = ((v_num - vnom).abs() / vnom * 100.0).stack().dropna()
            voltage_stats["p95_dev"] = round(float(v_dev_stack.quantile(0.95)), 2)
            voltage_stats["max_dev"] = round(float(v_dev_stack.max()), 2)
            voltage_stats["samples_out"] = int((v_dev_stack > 10.0).sum())
        else:
            voltage_stats["p95_dev"] = 0.0
            voltage_stats["max_dev"] = 0.0
            voltage_stats["samples_out"] = 0

        # Desequilibrio de tension: U2/U1 (secuencia negativa) si el analizador
        # lo exporta; si no, LVUR = (max-min)/media * 100
        u2u1_col = next((c for c in df.columns if 'U2/U1' in c), None)
        if u2u1_col:
            unbalance_series = pd.to_numeric(df[u2u1_col], errors='coerce').dropna()
            unbalance_source = "U2/U1 (secuencia negativa)"
        elif v_cols:
            v_mat = df[v_cols].apply(pd.to_numeric, errors='coerce')
            v_mean_row = v_mat.mean(axis=1)
            unbalance_series = ((v_mat.max(axis=1) - v_mat.min(axis=1)) / v_mean_row * 100.0).dropna()
            unbalance_source = "calculado (max-min)/media"
        else:
            unbalance_series = pd.Series(dtype=float)
            unbalance_source = "no disponible"
        unbalance = {
            "mean": round(float(unbalance_series.mean()), 3) if len(unbalance_series) else 0.0,
            "p95": round(float(unbalance_series.quantile(0.95)), 3) if len(unbalance_series) else 0.0,
            "max": round(float(unbalance_series.max()), 3) if len(unbalance_series) else 0.0,
            "source": unbalance_source
        }

        # THD de tension y de corriente (media entre fases)
        thd_u_cols = [c for c in df.columns if c.startswith('THD U') and 'media [%]' in c]
        thd_i_cols = [c for c in df.columns if c.startswith('THD I') and 'media [%]' in c
                      and 'N' not in c]
        thd_u_avg = df[thd_u_cols].mean(axis=1) if thd_u_cols else pd.Series(0.0, index=df.index)
        thd_i_avg = df[thd_i_cols].mean(axis=1) if thd_i_cols else pd.Series(0.0, index=df.index)
        # Muestras "con carga" (I media >= 30% del pico): THD I y K-factor solo
        # son interpretables con carga; en vacio ambos se disparan sin sentido
        # operativo (IEEE 519 evalua el THD I a carga nominal). Sobre este
        # registro, THD I pasa de 49.4% (todas) a un valor de carga real y
        # K-factor de max=327 a max=22.
        if i_cols:
            i_peak = float(df[i_cols].apply(pd.to_numeric, errors='coerce').max().max())
            loaded_mask = (df[i_cols].apply(pd.to_numeric, errors='coerce')
                           .mean(axis=1) >= 0.30 * i_peak)
            loaded_scope = "muestras con I >= 30% del pico"
        else:
            i_peak = 0.0
            loaded_mask = pd.Series(True, index=df.index)
            loaded_scope = "todas las muestras"

        # THD de corriente de las FASES (se excluye el neutro: su THD describe
        # la distorsion triplen, no la carga del transformador).
        thd_i_loaded = thd_i_avg[loaded_mask.values]
        thd_u = {"mean": round(float(thd_u_avg.mean()), 2),
                 "p95": round(float(thd_u_avg.quantile(0.95)), 2),
                 "max": round(float(thd_u_avg.max()), 2)}
        thd_i = {"mean": round(float(thd_i_loaded.mean()), 2) if len(thd_i_loaded) else 0.0,
                 "p95": round(float(thd_i_loaded.quantile(0.95)), 2) if len(thd_i_loaded) else 0.0,
                 "max": round(float(thd_i_loaded.max()), 2) if len(thd_i_loaded) else 0.0,
                 "scope": loaded_scope}

        # Corriente de neutro: sobrecarga por cargas monofasicas y triplen
        n_col = next((c for c in df.columns if c.startswith('I *N') and 'media [A]' in c), None)
        i_phase_avg = float(df[i_cols].mean().mean()) if i_cols else 0.0
        if n_col:
            n_series = pd.to_numeric(df[n_col], errors='coerce').dropna()
            neutral = {
                "mean_a": round(float(n_series.mean()), 2),
                "p95_a": round(float(n_series.quantile(0.95)), 2),
                "max_a": round(float(n_series.max()), 2),
                "pct_of_phase": round(float(n_series.max()) / i_phase_avg * 100.0, 1) if i_phase_avg > 0 else 0.0
            }
        else:
            neutral = {"mean_a": 0.0, "p95_a": 0.0, "max_a": 0.0, "pct_of_phase": 0.0}

        # K-factor (derating de transformador, IEEE C57.110). Solo tiene sentido
        # con carga: en vacio K se dispara artificialmente (el registro daba
        # max=327 sobre todas las muestras y 22 sobre las muestras con carga).
        # Se excluye la columna del neutro (K N describe la distorsion triplen).
        k_cols = [c for c in df.columns if c.startswith('K ') and 'media [---]' in c
                  and ' N ' not in c]
        if k_cols:
            k_mat = pd.concat(
                [pd.to_numeric(df.loc[loaded_mask.values, c], errors='coerce')
                 for c in k_cols]
            ).dropna()
        else:
            k_mat = pd.Series(dtype=float)
        k_factor = {
            "mean": round(float(k_mat.mean()), 2) if len(k_mat) else 0.0,
            "p95": round(float(k_mat.quantile(0.95)), 2) if len(k_mat) else 0.0,
            "max": round(float(k_mat.max()), 2) if len(k_mat) else 0.0,
            "samples": int(len(k_mat)),
            "scope": loaded_scope
        }

        # Crest factor (U/I): clipping/notching si CF se aleja de sqrt(2)
        cf_u_cols = [c for c in df.columns if c.startswith('CF U') and 'media [---]' in c]
        cf_i_cols = [c for c in df.columns if c.startswith('CF I') and 'media [---]' in c]
        cf_u = pd.concat([pd.to_numeric(df[c], errors='coerce') for c in cf_u_cols]).dropna() if cf_u_cols else pd.Series(dtype=float)
        cf_i = pd.concat([pd.to_numeric(df[c], errors='coerce') for c in cf_i_cols]).dropna() if cf_i_cols else pd.Series(dtype=float)
        crest = {
            "u": round(float(cf_u.mean()), 3) if len(cf_u) else 0.0,
            "i": round(float(cf_i.mean()), 3) if len(cf_i) else 0.0
        }

        # Frecuencia (EN 50160: ±0.5 Hz)
        f_col = next((c for c in df.columns if c.startswith('f ') and 'media [Hz]' in c), None)
        if f_col:
            f_series = pd.to_numeric(df[f_col], errors='coerce').dropna()
            f_dev = (f_series - 50.0).abs()
            frequency = {
                "mean": round(float(f_series.mean()), 3),
                "p95_dev": round(float(f_dev.quantile(0.95)), 3) if len(f_dev) else 0.0,
                "min": round(float(f_series.min()), 3),
                "max": round(float(f_series.max()), 3)
            }
        else:
            frequency = {"mean": 0.0, "p95_dev": 0.0, "min": 0.0, "max": 0.0}

        # Eventos de sag/swell sostenidos (agrupa muestras contiguas)
        def _group_events(mask: pd.Series, depth_series: pd.Series, kind: str):
            evts = []
            in_event = False
            start_i = 0
            for i, flag in enumerate(mask.values):
                if flag and not in_event:
                    in_event = True
                    start_i = i
                elif not flag and in_event:
                    in_event = False
                    evts.append((start_i, i - 1))
            if in_event:
                evts.append((start_i, len(mask) - 1))
            out = []
            for s_i, e_i in evts:
                seg = depth_series.iloc[s_i:e_i + 1]
                depth = float(seg.min()) if kind == 'sag' else float(seg.max())
                worst_phase = None
                if v_cols:
                    worst_col = seg.idxmin() if kind == 'sag' else seg.idxmax()
                    worst_phase = str(worst_col).split(' ')[1] if ' ' in str(worst_col) else str(worst_col)
                out.append({
                    "start": df['timestamp'].iloc[s_i].strftime('%H:%M:%S'),
                    "end": df['timestamp'].iloc[e_i].strftime('%H:%M:%S'),
                    "duration_min": round(float((df['timestamp'].iloc[e_i] - df['timestamp'].iloc[s_i]).total_seconds() / 60.0), 1),
                    "extreme_v": round(depth, 1),
                    "depth_pct": round(abs(depth - vnom) / vnom * 100.0, 1),
                    "phase": worst_phase
                })
            return out

        v_min_phase = df[v_cols].min(axis=1) if v_cols else pd.Series(vnom, index=df.index)
        v_max_phase = df[v_cols].max(axis=1) if v_cols else pd.Series(vnom, index=df.index)
        sag_mask = v_min_phase < 0.90 * vnom
        swell_mask = v_max_phase > 1.10 * vnom
        sags = _group_events(sag_mask, v_min_phase, 'sag')
        swells = _group_events(swell_mask, v_max_phase, 'swell')

        # Checks de cumplimiento (EN 50160 / IEC 61000)
        def _status(value, ok_max, warn_max):
            if value <= ok_max:
                return "ok"
            if value <= warn_max:
                return "warn"
            return "bad"

        if v_cols:
            v_dev_pct = voltage_stats["p95_dev"]
        else:
            v_dev_pct = 0.0

        checks = [
            {"id": "voltage", "label": "Tensión (±10%)",
             "value": f"{voltage_stats['l1']['mean']:.1f} V",
             "limit": f"±10% de {vnom:.0f} V (P95)",
             "status": _status(v_dev_pct, 10.0, 12.0),
             "note": f"P95 {v_dev_pct:.1f}% · máx {voltage_stats['max_dev']:.1f}% · "
                     f"{voltage_stats['samples_out']} muestras fuera"},
            {"id": "unbalance", "label": "Desequilibrio de tensión",
             "value": f"{unbalance['mean']:.2f} %",
             "limit": "< 2% P95 (EN 50160)",
             "status": _status(unbalance['p95'], 2.0, 3.0),
             "note": f"P95 {unbalance['p95']:.2f}% · máx {unbalance['max']:.2f}% · {unbalance['source']}"},
            {"id": "thd_u", "label": "THD de tensión",
             "value": f"{thd_u['mean']:.1f} %",
             "limit": "< 8% P95 (EN 50160 LV)",
             "status": _status(thd_u['p95'], 5.0, 8.0),
             "note": f"P95 {thd_u['p95']:.1f}% · máx {thd_u['max']:.1f}%"},
            {"id": "thd_i", "label": "THD de corriente",
             "value": f"{thd_i['mean']:.1f} %",
             "limit": "informativo",
             "status": _status(thd_i['p95'], 30.0, 60.0),
             "note": f"P95 {thd_i['p95']:.1f}% · máx {thd_i['max']:.1f}% · "
                     f"{thd_i['scope']} · alto = electrónica de potencia"},
            {"id": "neutral", "label": "Corriente de neutro",
             "value": f"{neutral['max_a']:.1f} A",
             "limit": "< 50% de fase",
             "status": _status(neutral['pct_of_phase'], 50.0, 80.0),
             "note": f"P95 {neutral['p95_a']:.1f} A · {neutral['pct_of_phase']:.0f}% de la fase · riesgo por triplen"},
            {"id": "k_factor", "label": "K-factor (transformador)",
             "value": f"{k_factor['mean']:.1f}",
             "limit": "< 4 P95 (IEEE C57.110)",
             "status": _status(k_factor['p95'], 4.0, 9.0),
             "note": f"P95 {k_factor['p95']:.1f} · máx {k_factor['max']:.1f} · {k_factor['scope']}"},
            {"id": "frequency", "label": "Frecuencia",
             "value": f"{frequency['mean']:.2f} Hz",
             "limit": "50 Hz ±0.5 (P95)",
             "status": _status(frequency['p95_dev'], 0.5, 1.0),
             "note": f"Desvío P95 {frequency['p95_dev']:.3f} Hz · "
                     f"rango {frequency['min']:.2f}-{frequency['max']:.2f} Hz"},
            {"id": "sags", "label": "Sags / Swells",
             "value": f"{len(sags)} / {len(swells)}",
             "limit": "0 sostenidos",
             "status": "ok" if len(sags) == 0 and len(swells) == 0 else "warn",
             "note": f"U<90%: {len(sags)} · U>110%: {len(swells)}"}
        ]

        # Series temporales decimadas para los graficos
        step = max(1, len(df) // max(1, max_points))
        idx = np.arange(0, len(df), step)

        def _series(col: str, default: float = 0.0):
            if col in df.columns:
                s = pd.to_numeric(df[col], errors='coerce').fillna(default)
                return [round(float(v), 2) for v in s.iloc[idx]]
            return [default] * len(idx)

        timestamps_out = df['timestamp'].iloc[idx].dt.strftime('%H:%M:%S').tolist()

        return {
            "vnom": vnom,
            "samples": int(len(df)),
            "method": "Cumplimiento evaluado con el percentil 95 de las muestras "
                      "(criterio EN 50160); el extremo absoluto se reporta en la nota. "
                      "K-factor restringido a muestras con carga.",
            "voltage": voltage_stats,
            "unbalance": unbalance,
            "thd_u": thd_u,
            "thd_i": thd_i,
            "neutral": neutral,
            "k_factor": k_factor,
            "crest": crest,
            "frequency": frequency,
            "checks": checks,
            "sags": sags,
            "swells": swells,
            "timeseries": {
                "timestamps": timestamps_out,
                "v_l1": _series('U L1 media [V]', 0.0),
                "v_l2": _series('U L2 media [V]', 0.0),
                "v_l3": _series('U L3 media [V]', 0.0),
                "thd_u": [round(float(v), 2) for v in thd_u_avg.iloc[idx]],
                "i_n": _series(n_col, 0.0) if n_col else [],
                "u2u1": [round(float(v), 3) for v in unbalance_series.iloc[idx]] if u2u1_col else [],
                "i_l1": _series('I *L1 media [A]', 0.0),
                "i_l2": _series('I *L2 media [A]', 0.0),
                "i_l3": _series('I *L3 media [A]', 0.0)
            }
        }
