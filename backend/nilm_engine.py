import json
import os
import re

import pandas as pd
import numpy as np
from sklearn.cluster import KMeans, DBSCAN
from sklearn.mixture import GaussianMixture
from sklearn.metrics import silhouette_score, davies_bouldin_score
from sklearn.preprocessing import StandardScaler
from typing import Dict, List, Any, Optional, Tuple
from itertools import product as _cartesian_product

try:
    from nilmtk.feature_detectors.cluster import cluster as nilmtk_cluster_states
except ImportError:
    nilmtk_cluster_states = None

# --- PASO 2: FHMM exacto (Viterbi) sobre el producto cartesiano de estados ---
# El modelo factorial se construye con hmmlearn cuando esta disponible; si no
# esta instalado, el motor degrada al descenso por eventos
# (disaggregate_load_fhmm) sin romper el analisis.
try:
    from hmmlearn.hmm import GaussianHMM as _GaussianHMM
    hmmlearn_available = True
except Exception:
    _GaussianHMM = None
    hmmlearn_available = False

# --- MEJORA #8: pareo ON/OFF por asignacion optima (algoritmo hungaro) ---
# scipy ya es dependencia declarada (requirements.txt); si faltara, el motor
# degrada al pareo secuencial clasico sin romper el analisis.
try:
    from scipy.optimize import linear_sum_assignment as _linear_sum_assignment
except Exception:
    _linear_sum_assignment = None

class NILMEngine:
    """
    Advanced NILM (Non-Intrusive Load Monitoring) Engine
    Provides event detection, multi-feature clustering, state tracking,
    and continuous load disaggregation for industrial and commercial energy data.
    """
    def __init__(self, data_manager):
        self.dm = data_manager
        self.nilmtk_available = nilmtk_cluster_states is not None

    @staticmethod
    def _classify_load_class(avg_p: float, avg_i: float, avg_thd: float,
                             harm_ratio_pct: float, harm_sum: float,
                             avg_cosphi: float = 0.0,
                             avg_inrush: float = 1.0) -> str:
        """
        PASO 1: clasifica la familia de carga combinando la firma armonica
        transitoria (ΔH/ΔI) con la firma de potencia. Un ratio armonico alto
        con ΔP modesto identifica electronica de potencia (VFD/Rectificador);
        un ΔP/ΔQ alto con ΔH bajo identifica un motor de arranque directo.
        MEJORA #20: el amortiguamiento del transitorio (pico de arranque o
        valle de parada respecto al nivel estable) y el |cos(phi)| medio
        refuerzan las reglas: transitorio >= 2x -> arranque DOL de motor;
        transitorio ~1x con |cos(phi)| >= 0.95 -> carga resistiva pura.
        (Con medias de 10 s el inrush electrico no es observable: este rasgo
        mide la sobre-oscilacion del arranque, no el pico de medio ciclo.)
        """
        if harm_ratio_pct >= 35.0 and harm_sum > 0.3:
            return "Electronica de Potencia (VFD/Rectificador)"
        if avg_thd >= 35.0:
            return "Electronica de Potencia (VFD/Rectificador)"
        if avg_inrush >= 2.0 and avg_i >= 5.0:
            return "Motor Inductivo (Arranque DOL)"
        if avg_inrush <= 1.15 and avg_cosphi >= 0.95 and avg_p >= 1.0:
            return "Carga Resistiva (Calentador)"
        if avg_i >= 20.0 and avg_p >= 15.0:
            return "Motor Inductivo (Arranque DOL)"
        if avg_p >= 5.0:
            return "Motor / Carga Mixta"
        if harm_ratio_pct >= 15.0:
            return "Carga No Lineal (Auxiliar)"
        return "Carga Resistiva"

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

    @staticmethod
    def _cusum_change_points(values, drift_k: float = 0.5, h_sigma: float = 5.0,
                             min_step_floor: float = 0.2, min_sep: int = 2):
        """MEJORA #7: change-points por CUSUM con umbral ADAPTATIVO (MAD).

        Detecta cambios persistentes de nivel sin depender del ajuste manual
        de umbrales: la escala de ruido sale de los propios datos
        (sigma = 1.4826 * MAD de las diferencias), la deriva es
        k = drift_k*sigma y el umbral de decision h = h_sigma*sigma. La
        posicion del cruce se refina al pico de |delta| mas cercano (el
        cambio real) y su magnitud se estima de forma robusta con medianas
        antes/despues; los saltos menores que max(min_step_floor, 2*sigma)
        se descartan por ruido.

        Devuelve (cambios, info): `cambios` es {posicion: salto_estimado} y
        `info` es JSON-safe (sigma, drift, h, min_step, samples, candidates).
        """
        x = np.asarray(values, dtype=float)
        info = {'samples': int(x.size), 'sigma': 0.0, 'drift': 0.0,
                'h': 0.0, 'min_step': float(min_step_floor), 'candidates': 0}
        n = int(x.size)
        if n < 6:
            return {}, info
        x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
        d = np.diff(x)
        mad = float(np.median(np.abs(d - np.median(d))))
        sigma = 1.4826 * mad
        if not np.isfinite(sigma) or sigma <= 1e-9:
            return {}, info
        k = float(drift_k) * sigma
        h = float(h_sigma) * sigma
        min_step = max(float(min_step_floor), 2.0 * sigma)
        info.update({'sigma': round(sigma, 6), 'drift': round(k, 6),
                     'h': round(h, 6), 'min_step': round(min_step, 6)})
        mu = float(np.median(x))

        # CUSUM de dos colas (tabular): el cambio se declara cuando el desvio
        # acumulado supera h; despues se reinicia para detectar el siguiente.
        cruces = []
        s_pos = s_neg = 0.0
        for i in range(n):
            s_pos = max(0.0, s_pos + (x[i] - mu - k))
            s_neg = min(0.0, s_neg + (x[i] - mu + k))
            if s_pos > h or s_neg < -h:
                cruces.append(i)
                s_pos = s_neg = 0.0
        if not cruces:
            return {}, info

        cambios = {}
        for i in cruces:
            lo = max(0, i - 4)
            hi = min(n - 2, i + 2)
            if hi < lo:
                continue
            row = lo + int(np.argmax(np.abs(d[lo:hi + 1]))) + 1
            antes = x[max(0, row - 3):row]
            despues = x[row:min(n, row + 6)]
            if antes.size == 0 or despues.size == 0:
                continue
            salto = float(np.median(despues) - np.median(antes))
            if abs(salto) < min_step:
                continue
            if row in cambios:
                if abs(salto) > abs(cambios[row]):
                    cambios[row] = salto
            else:
                cambios[row] = salto

        # Fusiona cambios contiguos (<= min_sep muestras): conserva el mayor.
        depurado = {}
        for row in sorted(cambios):
            if depurado:
                prev = max(depurado)
                if row - prev <= min_sep:
                    if abs(cambios[row]) > abs(depurado[prev]):
                        depurado.pop(prev)
                        depurado[row] = cambios[row]
                    continue
            depurado[row] = cambios[row]
        info['candidates'] = len(depurado)
        return {int(r): round(float(s), 4) for r, s in depurado.items()}, info

    def detect_events(self, df: pd.DataFrame, 
                      current_threshold: float = 2.0, 
                      power_threshold: float = 1.0,
                      detection_method: str = 'threshold'
                      ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Detects electrical switching events (turn-on and turn-off transients)
        using multi-parameter step changes.
        Each detected transition is labelled in the 'event_type' column:
        'ON' for positive transitions (turn-on) and 'OFF' for negative ones.
        Returns (df_work, events): the working frame with computed signals
        (P_total, delta_P, delta_I, ...) and the frame of detected events,
        both with the original index preserved.

        MEJORA #7: `detection_method` elige el detector de cambios:
        'threshold' (umbrales fijos actuales), 'cusum' (solo change-points con
        umbral adaptativo por MAD) o 'hybrid' (union de ambos: complementa el
        umbral manual con los cambios que este no alcanza). El informe queda
        en _change_points_report.
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
        # --- Per-harmonic transient steps: ΔIh for orders 3/5/7 (summed L1+L2+L3).
        # These discriminate electronics (VFD/rectifier => big ΔH3/ΔH5 with
        # modest ΔP) from induction motors (big ΔP/ΔQ, small ΔH).
        harm_orders = {}
        for h_order in (3, 5, 7):
            h_cols = [c for c in df_work.columns
                      if c.startswith(f'I H {h_order} L') and 'media [A]' in c]
            if h_cols:
                harm_orders[h_order] = df_work[h_cols].sum(axis=1).fillna(0)
        for h_order, h_series in harm_orders.items():
            df_work[f'H{h_order}_total'] = h_series
            df_work[f'delta_H{h_order}'] = h_series.diff().fillna(0)
        if 3 not in harm_orders:
            df_work['H3_total'] = 0.0
            df_work['delta_H3'] = 0.0
        if 5 not in harm_orders:
            df_work['H5_total'] = 0.0
            df_work['delta_H5'] = 0.0
        if 7 not in harm_orders:
            df_work['H7_total'] = 0.0
            df_work['delta_H7'] = 0.0

        # Aggregate harmonic current (orders 3..13) preserved for Q/P-level
        # ratios: H_total + delta_H feed harm_ratio_pct below.
        harm_total = None
        for h_order in (3, 5, 7, 9, 11, 13):
            h_cols = [c for c in df_work.columns
                      if c.startswith(f'I H {h_order} L') and 'media [A]' in c]
            if h_cols:
                h_series = df_work[h_cols].sum(axis=1).fillna(0)
                harm_total = h_series if harm_total is None else harm_total + h_series
        df_work['H_total'] = harm_total if harm_total is not None else 0.0

        # Step differences (deltas)
        df_work['delta_P'] = df_work['P_total'].diff().fillna(0)
        df_work['delta_Q'] = df_work['Q_total'].diff().fillna(0)
        df_work['delta_S'] = df_work['S_total'].diff().fillna(0)
        df_work['delta_I'] = df_work['I_total'].diff().fillna(0)
        df_work['delta_H'] = df_work['H_total'].diff().fillna(0)
        df_work['delta_THD'] = df_work['THD_avg'].diff().fillna(0)

        # --- MEJORA #20: firmas extendidas por evento -------------------
        # (a) cos(phi) medio de las FASES en valor absoluto y su salto
        #     transitorio Δcos(phi): un motor DOL arranca con |cos| bajo y
        #     sube al cargar; una resistencia mantiene |cos| ≈ 1; un VFD
        #     mantiene |cos| alto con PF penalizado por THD.
        #     Se excluye la columna Σ (mezcla signos de las tres fases) y se
        #     toma valor absoluto: en este analizador L1/L2 salen negativas
        #     por convencion de cuadrante, y promediar con signo daba -0.23
        #     (inutil); |cos| por fase da 0.67 y si es comparable con 1.
        cosphi_cols = [c for c in df_work.columns
                       if c.startswith('cos(') and 'media [---]' in c
                       and any(f' {ph} ' in c for ph in ('L1', 'L2', 'L3'))]
        if cosphi_cols:
            df_work['cosphi_avg'] = df_work[cosphi_cols].abs().mean(axis=1)
        elif 'PF_avg' in df_work:
            df_work['cosphi_avg'] = df_work['PF_avg'].abs()
        else:
            df_work['cosphi_avg'] = 0.92
        df_work['delta_cosphi'] = df_work['cosphi_avg'].diff().fillna(0)

        # (b) amortiguamiento del transitorio (antes "inrush"): con medias de
        #     10 s el inrush electrico (ms) es invisible en el export, pero SI
        #     se mide el pico de arranque / valle de parada respecto al nivel
        #     estable siguiente:
        #       ON  -> max(I[k:k+6]) / mediana(I[k+7:k+12])
        #       OFF -> mediana(I[k-3:k]) / min(I[k:k+6])
        #     Sobre el registro real: mediana 1.11 (ON) / 1.27 (OFF) y cola
        #     hasta 5-10x, por lo que discrimina arranques con sobre-oscilacion
        #     (DOL, compresor) de arranques suaves. Sustituye a |ΔI|/I_previa,
        #     que con carga de fondo en el bus daba 0.15 de mediana y nunca
        #     disparaba la regla de arranque directo (metrica muerta).
        i_series = df_work['I_total']
        i_pre_med = i_series.shift(1).rolling(3, min_periods=1).median()
        fwd_block = pd.concat([i_series.shift(-k) for k in range(6)], axis=1)
        i_settled = pd.concat(
            [i_series.shift(-k) for k in range(7, 12)], axis=1
        ).median(axis=1)
        over_on = fwd_block.max(axis=1) / i_settled.clip(lower=0.5)
        over_off = i_pre_med / fwd_block.min(axis=1).clip(lower=0.5)
        df_work['inrush_ratio'] = pd.Series(
            np.where(df_work['delta_I'].values >= 0,
                     over_on.fillna(1.0).values, over_off.fillna(1.0).values),
            index=df_work.index
        ).clip(lower=0.2, upper=20.0).fillna(1.0)

        # (c) concentracion de fase: max(|ΔI fase|)/sum(|ΔI fase|).
        #     ~1/3 trifasico equilibrado; ~1 monofasico (una sola fase).
        #     Calibrado sobre el registro real: en eventos P50=0.37,
        #     29% >= 0.80 (monofasico) y 2% entre 0.55 y 0.80 (asimetrico).
        phase_i_cols = [c for c in ['I *L1 media [A]', 'I *L2 media [A]',
                                    'I *L3 media [A]'] if c in df_work.columns]
        if len(phase_i_cols) >= 2:
            dphase = df_work[phase_i_cols].diff().abs().fillna(0)
            dmax = dphase.max(axis=1)
            dsum = dphase.sum(axis=1)
            df_work['phase_concentration'] = np.where(
                dsum > 0.01, (dmax / dsum).clip(0.0, 1.0), 1.0 / 3.0
            )
        else:
            df_work['phase_concentration'] = 1.0 / 3.0

        
        # Detect turn-on events (positive transitions)
        mask_on = (df_work['delta_I'] >= current_threshold) | (df_work['delta_P'] >= power_threshold)
        # Detect turn-off events (negative transitions)
        mask_off = (df_work['delta_I'] <= -current_threshold) | (df_work['delta_P'] <= -power_threshold)

        # --- MEJORA #7: detector de cambios (umbral fijo / CUSUM / hibrido) ---
        # 'threshold' = comportamiento historico; 'cusum' sustituye el umbral
        # manual por change-points con umbral adaptativo (MAD); 'hybrid' los
        # COMPLEMENTA: anade los cambios que el umbral fijo no alcanza, sin
        # duplicar los ya detectados (+-1 muestra).
        method = str(detection_method or 'threshold').strip().lower()
        if method not in ('threshold', 'cusum', 'hybrid'):
            method = 'threshold'
        sel: Dict[int, str] = {}
        for p in np.flatnonzero(mask_off.to_numpy()):
            sel[int(p)] = 'OFF'
        for p in np.flatnonzero(mask_on.to_numpy()):
            sel[int(p)] = 'ON'   # ON gana si ambos disparan (igual que antes)
        cp_info = {'requested': method, 'threshold_events': len(sel),
                   'cusum_candidates': 0, 'cusum_added': 0,
                   'cusum_duplicated': 0, 'events_final': len(sel),
                   'relaxed': False, 'sigma': 0.0, 'drift': 0.0,
                   'h': 0.0, 'min_step': 0.0, 'signal': 'I_total'}
        if method in ('cusum', 'hybrid'):
            cambios, cp_stats = self._cusum_change_points(
                df_work['I_total'].to_numpy(dtype=float)
            )
            for _key in ('sigma', 'drift', 'h', 'min_step'):
                cp_info[_key] = cp_stats.get(_key, 0.0)
            cp_info['cusum_candidates'] = int(cp_stats.get('candidates', 0) or 0)
            if method == 'cusum':
                sel = {}
            thr_sorted = np.array(sorted(sel.keys()), dtype=int)
            for row, salto in sorted(cambios.items()):
                if thr_sorted.size and bool(np.any(np.abs(thr_sorted - row) <= 1)):
                    cp_info['cusum_duplicated'] += 1
                    continue
                sel[int(row)] = 'ON' if salto > 0 else 'OFF'
                cp_info['cusum_added'] += 1
        cp_info['events_final'] = len(sel)
        self._change_points_report = cp_info

        filas = sorted(sel.keys())
        events = df_work.iloc[filas].copy()
        events['event_type'] = pd.Series([sel[f] for f in filas],
                                         index=events.index, dtype=object)

        # Additional features
        events['hour_of_day'] = events['timestamp'].dt.hour + events['timestamp'].dt.minute / 60.0

        # --- Fallback anti-Gantt-vacio: si el detector no encontro nada, se
        # relaja el umbral de potencia a la mitad (los transitorios reales de
        # esta medicion suelen quedar justo por debajo del umbral por defecto).
        relaxed = False
        if len(events) == 0 and power_threshold > 0.2:
            relaxed_thr = max(0.2, power_threshold / 2.0)
            mask_on = df_work['delta_P'] >= relaxed_thr
            mask_off = df_work['delta_P'] <= -relaxed_thr
            events = df_work[mask_on | mask_off].copy()
            if len(events) > 0:
                events['event_type'] = np.where(
                    mask_on.reindex(events.index).fillna(False).values, 'ON', 'OFF'
                )
                events['hour_of_day'] = events['timestamp'].dt.hour + events['timestamp'].dt.minute / 60.0
                relaxed = True
        if relaxed or len(events) == 0:
            print(f"Event detection (relaxed={relaxed}): {len(events)} events")
        # MEJORA #7: el informe de change-points refleja el resultado final
        # (incluye la relajacion anti-Gantt-vacio si se aplico).
        cp_info['relaxed'] = bool(relaxed)
        cp_info['events_final'] = int(len(events))
        self._change_points_report = cp_info

        # Harmonic transient signature: harmonic-current step (ΔIh, H3..H13)
        # relative to the fundamental-current step (ΔI1 ≈ ΔI total), in %.
        # High values => non-linear power-electronics load; low values with a
        # large reactive inrush => induction motor with direct start.
        denom = events['delta_I'].abs().clip(lower=0.1)
        events['harm_ratio_pct'] = (events['delta_H'].abs() / denom * 100.0).clip(upper=500.0)
        events['delta_thd'] = events['delta_THD']

        # Return working frame with computed signals + event frame for callers
        # (df_work has P_total/delta_P/delta_I/H_total; events has event rows).
        return df_work, events

    # Vector de features compartido: clustering, seleccion automatica de K
    # (MEJORA #6) y persistencia de modelos (MEJORA #17).
    _FEATURES = ['abs_delta_P', 'abs_delta_I', 'THD_avg', 'abs_delta_Q',
                 'abs_delta_H3', 'abs_delta_H5', 'abs_delta_H7',
                 'abs_delta_cosphi', 'feat_inrush', 'phase_concentration']

    @staticmethod
    def _feature_raw(events):
        """Monta las columnas crudas (sin escalar) del vector de features.

        Mutates `events` adding the abs_* columns and returns the raw matrix.
        Magnitudes absolutas para que los eventos ON y OFF del mismo equipo
        caigan juntos; incluye armonicos transitorios (#5) y firmas
        extendidas (#20). Base del scaler que se persiste en la MEJORA #17.
        """
        events['abs_delta_P'] = events['delta_P'].abs()
        events['abs_delta_I'] = events['delta_I'].abs()
        events['abs_delta_Q'] = events['delta_Q'].abs()
        # MEJORA #5: los saltos armonicos transitorios del PASO 1 entran al
        # vector de features -> separa electronica de potencia de motores
        # desde el propio clustering, sin depender del post-nombrado.
        for h_order in (3, 5, 7):
            h_col = f'delta_H{h_order}'
            events[f'abs_delta_H{h_order}'] = (
                events[h_col].abs() if h_col in events else 0.0
            )
        # MEJORA #20: firmas extendidas en el vector de features:
        # Δcos(phi) transitorio (motor/resistencia/VFD), amortiguamiento del
        # arranque (pico/regimen, log1p para compactar su cola) y
        # concentracion de fase (~1/3 trifasico, ~1 monofasico).
        events['abs_delta_cosphi'] = (
            events['delta_cosphi'].abs() if 'delta_cosphi' in events else 0.0
        )
        events['feat_inrush'] = np.log1p(
            (events['inrush_ratio'] - 1.0).clip(lower=0.0)
            if 'inrush_ratio' in events else 0.0
        )
        if 'phase_concentration' not in events:
            events['phase_concentration'] = 1.0 / 3.0
        return events[NILMEngine._FEATURES].fillna(0).values

    @staticmethod
    def _feature_frame(events, return_scaler=False):
        """Vector de features estandarizado del clustering.

        Compartido por cluster_appliances y por la seleccion automatica de K
        (MEJORA #6) para que ambos evaluen exactamente las mismas columnas.
        Con return_scaler devuelve (X_scaled, scaler) para que el clustering
        pueda persistir media/desviacion del scaler (MEJORA #17).
        """
        X = NILMEngine._feature_raw(events)
        scaler = StandardScaler().fit(X)
        X_scaled = scaler.transform(X)
        if return_scaler:
            return X_scaled, scaler
        return X_scaled

    @staticmethod
    def _auto_select_k(X_scaled, k_min=2, k_max=8):
        """MEJORA #6: propone el numero de equipos (K) automaticamente.

        Barre KMeans con k in [k_min, k_max] (semilla fija -> reproducible)
        y elige el k de MAYOR Silhouette; los empates se resuelven con el
        MENOR Davies-Bouldin. Devuelve un dict JSON-safe:
        {k, silhouette, davies_bouldin, candidates, method}. Con menos de
        4 eventos (o si todo falla) devuelve fallback k=2 sin candidatos.
        """
        try:
            n = int(len(X_scaled))
            lo = max(2, int(k_min))
            hi = min(int(k_max), n - 1)
            candidates = []
            best = None  # (clave, k, silhouette, davies_bouldin)
            if n >= 4 and hi >= lo:
                for k in range(lo, hi + 1):
                    try:
                        labels = KMeans(n_clusters=k, random_state=42,
                                        n_init=10).fit_predict(X_scaled)
                        if len(set(int(l) for l in labels)) < 2:
                            continue
                        sil = float(silhouette_score(X_scaled, labels))
                        db = float(davies_bouldin_score(X_scaled, labels))
                    except Exception:
                        continue
                    candidates.append({
                        'k': int(k),
                        'silhouette': round(sil, 4),
                        'davies_bouldin': round(db, 4),
                    })
                    clave = (sil, -db)
                    if best is None or clave > best[0]:
                        best = (clave, k, sil, db)
            if best is None:
                return {'k': 2, 'silhouette': None, 'davies_bouldin': None,
                        'candidates': [],
                        'method': 'Silhouette/Davies-Bouldin no aplicables '
                                  '(pocos eventos); fallback k=2.'}
            return {'k': int(best[1]),
                    'silhouette': round(best[2], 4),
                    'davies_bouldin': round(best[3], 4),
                    'candidates': candidates,
                    'method': 'Silhouette maximo + Davies-Bouldin de '
                              'desempate (KMeans, semilla 42).'}
        except Exception:
            return {'k': 2, 'silhouette': None, 'davies_bouldin': None,
                    'candidates': [], 'method': 'fallback (error interno).'}

    # ------------------------------------------------------------------
    # MEJORA #17: persistencia de modelos (centroides + scaler + etiquetas)
    # Se guardan por dataset en cache/models/<slug>.json (gitignored) para
    # que la siguiente medicion asigne los eventos con el mismo scaler y
    # conserve los nombres/colores (etiquetado consistente entre datasets).
    # ------------------------------------------------------------------
    _MODEL_VERSION = 1

    def _models_dir(self) -> str:
        base = getattr(self.dm, 'cache_dir', None)
        if not base:
            base = os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), 'cache')
        d = os.path.join(base, 'models')
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
        return d

    def _model_path(self, dataset_id: str) -> str:
        slug = re.sub(r'[^a-z0-9_\-]+', '_',
                      str(dataset_id).lower()).strip('_') or 'dataset'
        return os.path.join(self._models_dir(), f'{slug}.json')

    @classmethod
    def _model_compatible(cls, model) -> bool:
        """True si el modelo guardado sirve para asignar por nearest-centroid."""
        if not isinstance(model, dict):
            return False
        try:
            if int(model.get('version', -1)) != cls._MODEL_VERSION:
                return False
        except (TypeError, ValueError):
            return False
        cents = model.get('centroids')
        machines = model.get('machines')
        scaler = model.get('scaler')
        if not (isinstance(cents, list) and cents
                and isinstance(machines, dict) and machines
                and isinstance(scaler, dict)):
            return False
        if len(cents) != len(machines):
            return False
        if list(model.get('features') or []) != list(cls._FEATURES):
            return False
        mean, scale = scaler.get('mean'), scaler.get('scale')
        return (isinstance(mean, list) and isinstance(scale, list)
                and len(mean) == len(cls._FEATURES)
                and len(scale) == len(cls._FEATURES))

    def load_model(self, dataset_id: str) -> dict:
        """Modelo persistido del dataset o {} (ausente/corrupto/incompatible)."""
        try:
            with open(self._model_path(dataset_id), 'r', encoding='utf-8') as f:
                data = json.load(f)
            if self._model_compatible(data):
                return data
        except (OSError, ValueError, TypeError):
            pass
        return {}

    def save_model(self, dataset_id: str, cluster_info: dict) -> bool:
        """Persiste centroides+scaler del ultimo fit y las etiquetas por sitio.

        Escritura atomica (tmp + replace, como load_labels); devuelve False si
        no hay ajuste util (p. ej. DBSCAN no expone centroides) o si falla.
        """
        fit = getattr(self, '_last_fit', None)
        if not fit or not cluster_info:
            return False
        try:
            machines = {
                str(int(c)): {
                    'name': str(info.get('name', '')),
                    'category': str(info.get('category', '')),
                    'color': str(info.get('color', '')),
                }
                for c, info in cluster_info.items()
            }
            payload = {
                'version': self._MODEL_VERSION,
                'dataset_id': str(dataset_id),
                'saved_at': pd.Timestamp.now().isoformat(timespec='seconds'),
                'features': list(self._FEATURES),
                'scaler': {'mean': fit['mean'], 'scale': fit['scale']},
                'centroids': fit['centroids'],
                'k': len(fit['centroids']),
                'machines': machines,
            }
            path = self._model_path(dataset_id)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False)
            os.replace(tmp, path)
            return True
        except (OSError, TypeError, ValueError, KeyError):
            return False

    def cluster_appliances(self, events: pd.DataFrame,
                           n_clusters: int = 4, 
                           algorithm: str = "kmeans",
                           custom_labels: dict = None,
                           saved_model: dict = None) -> Tuple[pd.DataFrame, Dict[int, Any]]:
        """
        Applies Machine Learning clustering (K-Means, GMM, or DBSCAN)
        on multi-dimensional electrical features.
        Supports Ground-Truth manual label overrides for identified clusters.
        MEJORA #17: con saved_model asigna por nearest-centroid usando el
        scaler/centroides persistidos; deja el ultimo ajuste en self._last_fit.
        """
        self._last_fit = None
        if len(events) == 0:
            events['cluster'] = []
            events['machine_name'] = []
            events['color'] = []
            events['custom_label'] = []
            return events, {}

        # Vector de features compartido con la seleccion automatica de K
        # (MEJORA #6) y con el modelo persistido (MEJORA #17).
        X_raw = self._feature_raw(events)
        scaler = StandardScaler().fit(X_raw)
        X_scaled = scaler.transform(X_raw)

        n_samples = len(events)
        # Auto-reduce K cuando hay menos eventos que clusters pedidos
        # (KMeans/GMM fallan si n_samples < n_clusters y el Gantt quedaba vacio).
        # Minimo 1 cluster + fallback seguro con 1 solo evento (scaler necesita
        # al menos 1 muestra; silhouette se omite con <3 muestras).
        effective_k = max(1, min(n_clusters, n_samples))
        single_event = (n_samples == 1)

        # MEJORA #17: asignacion por centroides guardados (nearest-centroid
        # en el espacio escalado con el scaler persistido) -> el etiquetado
        # se mantiene entre mediciones. Si algo falla, se cae al fit normal.
        saved_ok = bool(saved_model) and self._model_compatible(saved_model)
        model = None
        if saved_ok:
            try:
                _mean = np.asarray(saved_model['scaler']['mean'], dtype=float)
                _scale = np.asarray(saved_model['scaler']['scale'], dtype=float)
                cents = np.asarray(saved_model['centroids'], dtype=float)
                Z = (np.asarray(X_raw, dtype=float) - _mean) / _scale
                dist = ((Z[:, None, :] - cents[None, :, :]) ** 2).sum(axis=2)
                cluster_labels = dist.argmin(axis=1).astype(int)
                self._last_fit = {'mean': _mean.tolist(),
                                  'scale': _scale.tolist(),
                                  'centroids': cents.tolist()}
            except Exception:
                saved_ok = False
                cluster_labels = None
        if not saved_ok and single_event:
            cluster_labels = np.zeros(n_samples, dtype=int)
        elif not saved_ok and algorithm.lower() == 'gmm':
            model = GaussianMixture(n_components=effective_k, random_state=42, max_iter=200)
            cluster_labels = model.fit_predict(X_scaled)
        elif not saved_ok and algorithm.lower() == 'dbscan':
            model = DBSCAN(eps=0.75, min_samples=4)
            cluster_labels = model.fit_predict(X_scaled)
            unique_labels = sorted(list(set(cluster_labels)))
            label_map = {l: i for i, l in enumerate(unique_labels)}
            cluster_labels = np.array([label_map[l] for l in cluster_labels])
        elif not saved_ok: # Default KMeans
            if effective_k >= n_samples:
                # Tantos clusters como eventos: asignacion 1:1 sin KMeans
                # (KMeans con k==n_samples da clusters triviales de 1 punto).
                cluster_labels = np.arange(n_samples, dtype=int)
            else:
                model = KMeans(n_clusters=effective_k, random_state=42, n_init=10)
                cluster_labels = model.fit_predict(X_scaled)

        if saved_ok:
            pass  # _last_fit ya apunta al modelo guardado (se re-persiste)
        elif model is not None:
            # MEJORA #17: guarda scaler + centroides del fit para la proxima
            # medicion (KMeans: cluster_centers_; GMM: means_; DBSCAN: nada).
            cents_fit = getattr(model, 'cluster_centers_', None)
            if cents_fit is None:
                cents_fit = getattr(model, 'means_', None)
            if cents_fit is not None:
                self._last_fit = {'mean': scaler.mean_.tolist(),
                                  'scale': scaler.scale_.tolist(),
                                  'centroids': np.asarray(cents_fit,
                                                          dtype=float).tolist()}

        events['cluster'] = cluster_labels

        colors = [
            "#3B82F6", "#10B981", "#F59E0B", "#EF4444", 
            "#8B5CF6", "#EC4899", "#06B6D4", "#84CC16"
        ]

        cluster_info = {}
        # Sort clusters by average power descending. Claves int nativas de
        # Python: unique() devuelve np.int32 y contaminaria el JSON de salida
        # ("id"/"machine_id" no serializables por json.dumps del servidor).
        raw_clusters = sorted(int(c) for c in events['cluster'].unique())
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
            # MEJORA #15: potencia aparente del salto (kVA) e intensidad
            # aparente por fase: base del coste de distorsion y del
            # desbalance por equipo. delta_S prefiere la columna ya
            # calculada; si no existe se aproxima con V_nom * |delta_I|.
            if 'delta_S' in sub:
                avg_s = float(sub['delta_S'].abs().mean())
            elif 'delta_I' in sub:
                v_nom = float(sub['V_avg'].mean()) if 'V_avg' in sub else 230.0
                avg_s = float(v_nom * sub['delta_I'].abs().mean() / 1000.0)
            else:
                avg_s = 0.0
            # Desbalance por equipo (extension de phase_concentration a los
            # tres pasos de fase): dispersion relativa de |delta_I L1..L3|
            # en el instante del evento (0 = equilibrado, ->1 = monofasico).
            phase_step_cols = [
                c for c in ('delta_I_L1', 'delta_I_L2', 'delta_I_L3')
                if c in sub.columns
            ]
            if len(phase_step_cols) >= 2:
                steps = sub[phase_step_cols].abs().to_numpy(dtype=float)
                col_mean = np.nanmean(steps, axis=1, keepdims=True)
                with np.errstate(invalid='ignore', divide='ignore'):
                    row_cv = np.nanmean(
                        np.abs(steps - col_mean)
                        / np.where(col_mean > 1e-9, col_mean, np.nan),
                        axis=1,
                    )
                row_cv = np.nan_to_num(row_cv, nan=0.0, posinf=0.0, neginf=0.0)
                avg_phase_imb = float(np.clip(np.nanmean(row_cv), 0.0, 2.0)) \
                    if row_cv.size else 0.0
            elif 'phase_concentration' in sub:
                # Fallback sin columnas de fase: mapea la concentracion
                # (~1/3 trifasico, ~1 monofasico) a un indice 0..1.
                conc = float(sub['phase_concentration'].mean())
                avg_phase_imb = float(np.clip((conc - 1.0 / 3.0)
                                              / (1.0 - 1.0 / 3.0), 0.0, 1.0))
            else:
                avg_phase_imb = 0.0

            # PASO 1: firma armonica transitoria del equipo (ΔH3/ΔH5/ΔH7 y
            # ratio ΔH/ΔI en %). Un VFD/rectificador presenta ΔH alto con ΔP
            # modesto; un motor DOL presenta ΔP/ΔQ alto con ΔH bajo.
            avg_dh3 = float(sub['delta_H3'].abs().mean()) if 'delta_H3' in sub else 0.0
            avg_dh5 = float(sub['delta_H5'].abs().mean()) if 'delta_H5' in sub else 0.0
            avg_dh7 = float(sub['delta_H7'].abs().mean()) if 'delta_H7' in sub else 0.0
            avg_harm_ratio = float(sub['harm_ratio_pct'].mean()) if 'harm_ratio_pct' in sub else 0.0
            harm_sum = avg_dh3 + avg_dh5 + avg_dh7

            # MEJORA #20: firmas extendidas promediadas por cluster —
            # cos(phi) medio, ratio de inrush y tipo de fase (mono/asimétrico/
            # trifásico equilibrado) según la concentración de ΔI por fase.
            avg_cosphi = float(sub['cosphi_avg'].mean()) if 'cosphi_avg' in sub else 0.0
            avg_inrush = float(sub['inrush_ratio'].mean()) if 'inrush_ratio' in sub else 1.0
            avg_phase_conc = (
                float(sub['phase_concentration'].mean())
                if 'phase_concentration' in sub else 1.0 / 3.0
            )
            if avg_phase_conc >= 0.80:
                phase_type = "Monofásico (1 fase)"
            elif avg_phase_conc >= 0.55:
                phase_type = "Asimétrico (2 fases)"
            else:
                phase_type = "Trifásico equilibrado"

            # MEJORA #15: coste de distorsion por equipo. Del THD de
            # corriente: I_dist = I_rms * THD/sqrt(1+THD^2) (IEEE 1459) y
            # la potencia de distorsion D = V * I_dist actua como kVA
            # "fantasma" que dimensiona trafo/cables sin producir kW.
            # El ratio D/S del salto indica que fraccion de la potencia
            # aparente del equipo es distorsion (0..1).
            thd_frac = max(0.0, avg_thd) / 100.0
            dist_frac = thd_frac / np.sqrt(1.0 + thd_frac ** 2)
            dist_kva = float(avg_s * dist_frac)
            dist_ratio = float(np.clip(dist_frac, 0.0, 1.0))

            load_class = self._classify_load_class(
                avg_p, avg_i, avg_thd, avg_harm_ratio, harm_sum,
                avg_cosphi=avg_cosphi, avg_inrush=avg_inrush
            )

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
                # Heuristic machine naming based on electrical signature.
                # PASO 1: la firma armonica se evalua ANTES del tamano para no
                # etiquetar como motor un rectificador con ΔP modesto.
                if avg_harm_ratio >= 40.0 and harm_sum > 0.5 and avg_p < 25.0:
                    name = f"Variador / Rectificador (ΔH {harm_sum:.1f} A)"
                    category = "Variador de Frecuencia"
                elif avg_inrush >= 2.0 and avg_p >= 3.0:
                    # MEJORA #20: transitorio >= 2x identifica arranque DOL
                    name = f"Motor DOL / Compresor (arranque ×{avg_inrush:.1f})"
                    category = "Compresor / Gran Potencia"
                elif avg_p >= 25.0 or avg_i >= 40.0:
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

            # MEJORA #17: etiquetado consistente entre mediciones. Si los
            # eventos se asignaron con los centroides guardados (nearest-
            # centroid), se conserva el nombre/categoria/color del modelo del
            # sitio. La etiqueta manual (Ground Truth) siempre tiene prioridad
            # sobre el modelo; la heuristica solo actua si el modelo no trae
            # ese cluster.
            saved_color = None
            if saved_ok and not is_custom:
                try:
                    _sm = (saved_model.get('machines') or {}).get(str(int(c)))
                except (TypeError, ValueError):
                    _sm = None
                if isinstance(_sm, dict):
                    if str(_sm.get('name', '')).strip():
                        name = str(_sm['name']).strip()
                    if str(_sm.get('category', '')).strip():
                        category = str(_sm['category']).strip()
                    if str(_sm.get('color', '')).strip():
                        saved_color = str(_sm['color']).strip()

            cluster_info[c] = {
                "name": name,
                "category": category,
                # MEJORA #17: el modelo guardado conserva tambien el color.
                "color": saved_color or colors[rank % len(colors)],
                "avg_delta_p": round(avg_p, 2),
                "avg_delta_i": round(avg_i, 2),
                "avg_delta_q": round(avg_q, 2),
                "avg_thd": round(avg_thd, 1),
                "avg_delta_h3": round(avg_dh3, 3),
                "avg_delta_h5": round(avg_dh5, 3),
                "avg_delta_h7": round(avg_dh7, 3),
                "harm_ratio_pct": round(avg_harm_ratio, 1),
                "avg_cosphi": round(avg_cosphi, 3),
                "avg_inrush": round(avg_inrush, 2),
                "phase_type": phase_type,
                "avg_delta_s": round(avg_s, 3),
                "dist_kva": round(dist_kva, 3),
                "dist_ratio": round(dist_ratio, 3),
                "phase_imbalance": round(avg_phase_imb, 3),
                "load_class": load_class,
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

    @staticmethod
    def _hungarian_assign(cost, feasible):
        """MEJORA #8: asignacion optima ON->OFF (algoritmo hungaro).

        Resuelve el problema de asignacion minimizando el coste total de la
        matriz `cost` (filas = arranques ON de una maquina, columnas = eventos
        OFF candidatos). Solo devuelve los pares factibles (`feasible`), de
        modo que las combinaciones prohibidas (OFF anterior al ON, fuera de
        ventana o de magnitud incompatible) nunca entran en el resultado.
        Devuelve {fila: columna} o None si scipy no esta disponible.
        """
        if _linear_sum_assignment is None or cost is None:
            return None
        if cost.size == 0:
            return {}
        try:
            rows, cols = _linear_sum_assignment(cost)
        except Exception:
            return None
        return {int(r): int(c) for r, c in zip(rows, cols) if feasible[r, c]}

    @staticmethod
    def _apply_duration_priors(df_work, disagg_power, cluster_info,
                               timeline_events, min_on_minutes=0.0,
                               min_off_minutes=0.0,
                               state_levels=None):
        """MEJORA #3: estabiliza operating runs antes de construir el Gantt.

        Descarta tramos ON cortos y funde pausas OFF entre dos tramos ON. La
        misma funcion se usa en ON/OFF y FHMM. Valores 0 preservan el
        comportamiento anterior.
        """
        min_on = max(0.0, float(min_on_minutes or 0.0))
        min_off = max(0.0, float(min_off_minutes or 0.0))
        report = {
            'enabled': bool(min_on or min_off),
            'min_on_minutes': round(min_on, 3),
            'min_off_minutes': round(min_off, 3),
            'on_intervals_before': 0, 'on_intervals_after': 0,
            'short_on_intervals_removed': 0,
            'off_gaps_before': 0, 'off_gaps_after': 0,
            'short_off_gaps_bridged': 0,
            'on_minutes_removed': 0.0, 'off_minutes_bridged': 0.0,
            'machines_affected': 0,
        }
        if not report['enabled']:
            return timeline_events, report

        timestamps = pd.to_datetime(df_work['timestamp']).to_numpy(
            dtype='datetime64[ns]')
        n_points = len(timestamps)

        def runs(mask):
            padded = np.concatenate(([False], np.asarray(mask, dtype=bool),
                                     [False]))
            changes = np.flatnonzero(padded[1:] != padded[:-1])
            return list(zip(changes[0::2], changes[1::2]))

        def minutes(start, end):
            # Misma convencion inclusiva que el Gantt historico: start..end-1.
            return max(0.0, float((timestamps[end - 1] - timestamps[start])
                                  / np.timedelta64(1, 'm')))

        rebuilt = []
        for c in sorted(cluster_info.keys()):
            power = np.asarray(disagg_power[c], dtype=float).copy()
            before = runs(power > 0.05)
            original_off_gaps = runs(power <= 0.05)
            report['on_intervals_before'] += len(before)
            report['off_gaps_before'] += sum(
                1 for start, end in original_off_gaps
                if start > 0 and end < n_points
            )
            for start, end in before:
                duration = minutes(start, end)
                if min_on and duration < min_on:
                    power[start:end] = 0.0
                    report['short_on_intervals_removed'] += 1
                    report['on_minutes_removed'] += duration

            for start, end in original_off_gaps:
                if start <= 0 or end >= n_points:
                    continue
                # Si uno de los extremos era un ON corto ya eliminado, este
                # hueco no puede "revivirlo" mediante la fusion OFF.
                if power[start - 1] <= 0.05 or power[end] <= 0.05:
                    continue
                duration = minutes(start, end)
                if min_off and duration <= min_off:
                    power[start:end] = max(
                        0.5, float(cluster_info[c]['avg_delta_p']))
                    report['short_off_gaps_bridged'] += 1
                    report['off_minutes_bridged'] += duration

            active = power > 0.05
            after = runs(active)
            report['on_intervals_after'] += len(after)
            report['off_gaps_after'] += sum(
                1 for start, end in runs(~active)
                if start > 0 and end < n_points
            )
            changed = not np.array_equal(power, np.asarray(
                disagg_power[c], dtype=float))
            if changed:
                report['machines_affected'] += 1
            disagg_power[c] = power.astype(np.float32)

            # Conserva state_level/state de FHMM para reconstruir sus tramos.
            state_at = np.full(n_points, -1, dtype=int)
            source_at = [None] * n_points
            for source in [item for item in timeline_events
                           if item.get('machine_id') == c]:
                try:
                    start_dt = pd.Timestamp(source['start_timestamp'])
                    end_dt = pd.Timestamp(source['end_timestamp'])
                    state = int(source.get('state_level', -1))
                except (KeyError, TypeError, ValueError):
                    continue
                if state < 0:
                    continue
                start = int(np.searchsorted(
                    timestamps, np.datetime64(start_dt.to_datetime64(), 'ns')))
                end = min(n_points, int(np.searchsorted(
                    timestamps, np.datetime64(end_dt.to_datetime64(), 'ns'))) + 1)
                for idx in range(max(0, start), end):
                    if state_at[idx] < 0:
                        state_at[idx], source_at[idx] = state, source

            # En FHMM los puntos creados al unir OFF no tienen estado previo:
            # se etiqueta con el nivel mas cercano a la potencia nominal.
            levels = (state_levels or {}).get(c, [cluster_info[c]['avg_delta_p']])
            for run_start, run_end in after:
                if levels:
                    unknown = np.flatnonzero(state_at[run_start:run_end] < 0)
                    if len(unknown):
                        nominal = max(0.5, float(cluster_info[c]['avg_delta_p']))
                        state = min(range(len(levels)), key=lambda i: abs(
                            float(levels[i]) - nominal))
                        state_at[run_start + unknown] = state
                idx = run_start
                while idx < run_end:
                    state = int(state_at[idx])
                    end = idx + 1
                    if state >= 0:
                        while end < run_end and state_at[end] == state:
                            end += 1
                    else:
                        # Camino ON/OFF: no hay state_level; un run activo es
                        # un unico intervalo y no debe fragmentarse por muestra.
                        while end < run_end and state_at[end] < 0:
                            end += 1
                    start_dt = pd.Timestamp(timestamps[idx])
                    end_dt = pd.Timestamp(timestamps[end - 1])
                    duration = minutes(idx, end)
                    if duration >= 0.1:
                        level = float(np.mean(power[idx:end]))
                        source = source_at[idx] if state >= 0 else None
                        item = dict(source) if source else {
                            'machine_id': c,
                            'machine_name': cluster_info[c]['name'],
                            'category': cluster_info[c]['category'],
                            'color': cluster_info[c]['color'],
                        }
                        item.update({
                            'start_time': start_dt.strftime('%H:%M:%S'),
                            'end_time': end_dt.strftime('%H:%M:%S'),
                            'start_timestamp': str(start_dt),
                            'end_timestamp': str(end_dt),
                            'duration_minutes': round(duration, 1),
                            'avg_power_kw': round(level, 2),
                            'energy_kwh': round(level * duration / 60.0, 3),
                        })
                        if state >= 0:
                            item['state_level'] = state
                        else:
                            item.pop('state_level', None)
                            item.pop('state', None)
                        rebuilt.append(item)
                    idx = end

        rebuilt.sort(key=lambda item: item['start_timestamp'])
        report['on_minutes_removed'] = round(report['on_minutes_removed'], 1)
        report['off_minutes_bridged'] = round(report['off_minutes_bridged'], 1)
        return rebuilt, report

    def disaggregate_load(self, df_work: pd.DataFrame,
                          events: pd.DataFrame,
                          cluster_info: Dict[int, Any],
                          pairing_method: str = 'auto',
                          min_on_minutes: float = 0.0,
                          min_off_minutes: float = 0.0):
        """
        Continuous load disaggregation: Reconstructs the power time-series
        for each detected machine using strict ON-OFF event pairing and operational state timeline (Gantt).

        MEJORA #8: `pairing_method` elige el emparejamiento ON<->OFF por
        maquina: 'sequential' (primer OFF compatible, comportamiento
        historico), 'hungarian' (asignacion optima magnitud + cercania
        temporal) o 'auto' (el de menor coste total con al menos tantos pares;
        nunca peor que el historico). El informe queda en _pairing_report.
        """
        self._pairing_report = {
            'requested': str(pairing_method or 'auto'),
            'method': 'sequential',
            'pairs': 0,
            'cost': 0.0,
            'cost_sequential': 0.0,
            'cost_hungarian': 0.0,
            'machines_hungarian': 0,
            'scipy_available': _linear_sum_assignment is not None,
        }
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

            # OFFs SÍ están clusterizados (el clustering usa magnitudes absolutas,
            # agrupando ON/OFF del mismo equipo), pero NO usamos el OFF por-cluster:
            # emparejamos contra el pool GLOBAL de eventos OFF por orden temporal
            # y magnitud (~nominal_p), lo que aguanta solapamientos de equipos.
            c_events_on = c_events[c_events['event_type'] == 'ON'].reset_index(drop=True)
            nominal_p = max(0.5, info['avg_delta_p'])

            off_pool = events[events['event_type'] == 'OFF'].copy()
            off_pool = off_pool.sort_values('timestamp').reset_index(drop=True)
            used_off_indices = set()
            
            # Edge case: Machine already running at t=0 before first ON event
            # (uses the global OFF pool: first OFF of compatible magnitude).
            if len(off_pool) > 0:
                first_on_time = pd.Timestamp(c_events_on['timestamp'].iloc[0]) if len(c_events_on) > 0 else None
                cand = None
                for _oi, _orow in off_pool.iterrows():
                    _ot = pd.Timestamp(_orow['timestamp'])
                    if first_on_time is not None and _ot >= first_on_time:
                        break
                    if abs(float(_orow.get('delta_P', -nominal_p))) >= 0.5 * nominal_p:
                        cand = (_oi, _ot)
                        break
                if cand is not None:
                    _oi, first_off_time = cand
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
                                    "end_time": end_dt.strftime('%H:%M:%S'),
                                    "start_timestamp": str(start_dt),
                                    "end_timestamp": str(end_dt),
                                    "duration_minutes": round(dur_minutes, 1),
                                    "avg_power_kw": round(nominal_p, 2),
                                    "energy_kwh": round(energy_kwh, 3)
                                })
                            used_off_indices.add(_oi)

            # MEJORA #8: pareo ON<->OFF por ASIGNACION. Se construye la matriz
            # de candidatos factibles (OFF posterior al ON y no mas alla del
            # siguiente ON de la maquina, magnitud en [0.5, 2.5]x nominal) con
            # coste = 0.7*|mag-nominal|/nominal + 0.3*desfase_relativo y se
            # resuelve por asignacion optima (hungaro). 'auto' se queda con el
            # de menor coste total (con al menos tantos pares como el clasico),
            # de modo que el resultado nunca empeora al comportamiento previo.
            on_meta = []
            for pos, (on_i, ev_on) in enumerate(c_events_on.iterrows()):
                ev_on_time = np.datetime64(pd.Timestamp(ev_on['timestamp']).to_datetime64(), 'ns')
                idx_on = int(np.searchsorted(timestamps, ev_on_time))
                if idx_on >= n_points or disagg_power[c][idx_on] > 0:
                    on_meta.append((pos, None, None))
                    continue
                # Determine ceiling: the next ON event for the same machine
                if pos + 1 < len(c_events_on):
                    next_on_time = np.datetime64(pd.Timestamp(c_events_on['timestamp'].iloc[pos + 1]).to_datetime64(), 'ns')
                    idx_next_on = min(n_points, int(np.searchsorted(timestamps, next_on_time)))
                else:
                    idx_next_on = n_points
                on_meta.append((pos, idx_on, idx_next_on))

            # OFFs viven en el pool GLOBAL (todos los eventos OFF de la serie):
            # se conservan sus indices de fila para reutilizar used_off_indices.
            off_cands = []
            for off_i, ev_off in off_pool.iterrows():
                if off_i in used_off_indices:
                    continue
                ev_off_time = np.datetime64(pd.Timestamp(ev_off['timestamp']).to_datetime64(), 'ns')
                off_cands.append((off_i, int(np.searchsorted(timestamps, ev_off_time)),
                                  abs(float(ev_off.get('delta_P', -nominal_p)))))

            n_on, n_cand = len(on_meta), len(off_cands)
            feasible = np.zeros((n_on, n_cand), dtype=bool)
            cost = np.full((n_on, n_cand), 1e6, dtype=float)
            for r, (pos, idx_on, idx_next_on) in enumerate(on_meta):
                if idx_on is None:
                    continue
                span = max(1, idx_next_on - idx_on)
                for k, (_oi, idx_off, mag) in enumerate(off_cands):
                    if idx_off <= idx_on or idx_off > idx_next_on:
                        continue
                    if not (0.5 * nominal_p <= mag <= 2.5 * nominal_p):
                        continue
                    feasible[r, k] = True
                    cost[r, k] = (0.7 * abs(mag - nominal_p) / nominal_p
                                  + 0.3 * (idx_off - idx_on) / span)

            # Secuencial = primer OFF candidato libre (comportamiento historico,
            # proxy de "OFF mas cercano" dentro de la ventana del arranque).
            greedy, _taken = {}, set()
            for r in range(n_on):
                if on_meta[r][1] is None:
                    continue
                for k in range(n_cand):
                    if k in _taken or not feasible[r, k]:
                        continue
                    greedy[r] = k
                    _taken.add(k)
                    break

            hung = self._hungarian_assign(cost, feasible) if n_cand else None
            tot_g = float(sum(cost[r, k] for r, k in greedy.items()))
            tot_h = float(sum(cost[r, k] for r, k in hung.items())) \
                if hung is not None else None
            chosen, used_method = greedy, 'sequential'
            if pairing_method == 'hungarian' and hung is not None:
                chosen, used_method = hung, 'hungarian'
            elif pairing_method == 'auto' and hung is not None:
                # Mas pares primero; a igualdad de pares, menor coste total.
                if (len(hung), -tot_h) > (len(greedy), -tot_g):
                    chosen, used_method = hung, 'hungarian'
            _rep = self._pairing_report
            _rep['pairs'] += len(chosen)
            _rep['cost'] += float(sum(cost[r, k] for r, k in chosen.items()))
            _rep['cost_sequential'] += tot_g
            _rep['cost_hungarian'] += tot_h if tot_h is not None else 0.0
            if used_method == 'hungarian':
                _rep['machines_hungarian'] += 1

            # Pair each ON event with its corresponding OFF transition
            # NOTE: c_events_on was reset_index(drop=True) -> on_i is 0..N-1
            # positional, so use pos (enumerate) for next-ON ceiling.
            for pos, (on_i, ev_on) in enumerate(c_events_on.iterrows()):
                ev_on_time = np.datetime64(pd.Timestamp(ev_on['timestamp']).to_datetime64(), 'ns')
                idx_on = np.searchsorted(timestamps, ev_on_time)
                if idx_on >= n_points:
                    continue

                # If this ON event falls inside an already active window for this machine, skip duplicate
                if disagg_power[c][idx_on] > 0:
                    continue

                # MEJORA #8: el OFF emparejado lo decide la asignacion (optima
                # o secuencial) calculada antes del bucle.
                matched_off_idx = None
                best_off_row_idx = None
                _sel = chosen.get(pos)
                if _sel is not None:
                    best_off_row_idx, matched_off_idx = off_cands[_sel][0], off_cands[_sel][1]

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
                        "end_time": end_dt.strftime('%H:%M:%S'),
                        "start_timestamp": str(start_dt),
                        "end_timestamp": str(end_dt),
                        "duration_minutes": round(dur_minutes, 1),
                        "avg_power_kw": round(nominal_p, 2),
                        "energy_kwh": round(energy_kwh, 3)
                    })

        # MEJORA #3: estabilizar operating runs antes de baseline, Gantt y stats.
        timeline_events, self._duration_prior_report = self._apply_duration_priors(
            df_work, disagg_power, cluster_info, timeline_events,
            min_on_minutes, min_off_minutes)

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
                "custom_label": bool(info.get('custom_label', False)),
                "avg_delta_h3": round(info.get('avg_delta_h3', 0.0), 3),
                "avg_delta_h5": round(info.get('avg_delta_h5', 0.0), 3),
                "avg_delta_h7": round(info.get('avg_delta_h7', 0.0), 3),
                "harm_ratio_pct": round(info.get('harm_ratio_pct', 0.0), 1),
                "avg_cosphi": round(float(info.get('avg_cosphi', 0.0)), 3),
                "avg_inrush": round(float(info.get('avg_inrush', 1.0)), 2),
                "phase_type": info.get('phase_type', 'Trifásico equilibrado'),
                "load_class": info.get('load_class', 'Desconocido'),
                # MEJORA #15: kVA del salto, distorsion y desbalance.
                "avg_delta_s": round(float(info.get('avg_delta_s', 0.0)), 3),
                "dist_kva": round(float(info.get('dist_kva', 0.0)), 3),
                "dist_ratio": round(float(info.get('dist_ratio', 0.0)), 3),
                "phase_imbalance": round(float(info.get('phase_imbalance', 0.0)), 3)
            })

        # MEJORA #8: metodo efectivo del pareo (coherente tambien si se llama
        # a disaggregate_load directamente, sin pasar por analyze_dataset).
        _rep = self._pairing_report
        if _rep:
            _mh = int(_rep.get('machines_hungarian', 0))
            _rep['method'] = ('hungarian' if _mh and _mh == len(clusters)
                              else 'mixed' if _mh else 'sequential')
            _rep['machines_total'] = len(clusters)
            _cs = float(_rep.get('cost_sequential', 0.0))
            _rep['improved_pct'] = (
                round((_cs - float(_rep.get('cost', 0.0))) / _cs * 100.0, 2)
                if _cs > 1e-12 else 0.0
            )

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

    def disaggregate_load_fhmm(self, df_work, events, cluster_info,
                               machine_states, min_on_minutes=0.0,
                               min_off_minutes=0.0):
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
                    "avg_delta_h3": 0.0, "avg_delta_h5": 0.0, "avg_delta_h7": 0.0,
                    "harm_ratio_pct": 0.0,
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
                # int nativo: assigned_states es un array numpy y un np.int64
                # llegaria tal cual al campo "state_level" del JSON.
                segment_states.append(int(assigned_states[i]))
            
            self._build_fhmm_segments(df_work, segments_start=segment_starts, segments_end=segment_ends, seg_states=segment_states, state_levels=state_levels, disagg_power=disagg_power, c=c, timeline_events=timeline_events, info=info)
            self._build_fhmm_stats(df_work, c=c, info=info, disagg_power=disagg_power, state_levels=state_levels, timeline_events=timeline_events, machine_stats=machine_stats)

        # MEJORA #3: el helper preserva los state_level originales de FHMM.
        timeline_events, self._duration_prior_report = self._apply_duration_priors(
            df_work, disagg_power, cluster_info, timeline_events,
            min_on_minutes, min_off_minutes, state_levels=machine_states)
        if self._duration_prior_report.get('enabled'):
            machine_stats = []
            for c in clusters:
                states = sorted(machine_states.get(
                    c, [cluster_info[c]['avg_delta_p']]))
                self._build_fhmm_stats(
                    df_work, c, cluster_info[c], disagg_power, states,
                    timeline_events, machine_stats)

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
                    "end_time": end_dt.strftime('%H:%M:%S'),
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

        # El load_class ya se calculo en cluster_appliances con la firma
        # extendida (MEJORA #20). Solo se recalcula si falta, pasando TODOS
        # los rasgos: sin cos(phi) ni el amortiguamiento del arranque se
        # perderian las reglas de arranque DOL y de carga resistiva.
        load_class = info.get('load_class') or self._classify_load_class(
            avg_p, delta_i, avg_thd,
            float(info.get('harm_ratio_pct', 0.0)),
            float(info.get('avg_delta_h3', 0.0)) + float(info.get('avg_delta_h5', 0.0))
            + float(info.get('avg_delta_h7', 0.0)),
            avg_cosphi=float(info.get('avg_cosphi', 0.0)),
            avg_inrush=float(info.get('avg_inrush', 1.0))
        )
        
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
            "avg_delta_h3": round(info.get('avg_delta_h3', 0.0), 3),
            "avg_delta_h5": round(info.get('avg_delta_h5', 0.0), 3),
            "avg_delta_h7": round(info.get('avg_delta_h7', 0.0), 3),
            "harm_ratio_pct": round(info.get('harm_ratio_pct', 0.0), 1),
            "avg_cosphi": round(float(info.get('avg_cosphi', 0.0)), 3),
            "avg_inrush": round(float(info.get('avg_inrush', 1.0)), 2),
            "phase_type": info.get('phase_type', 'Trifásico equilibrado'),
            # MEJORA #15: kVA del salto, distorsion y desbalance (FHMM).
            "avg_delta_s": round(float(info.get('avg_delta_s', 0.0)), 3),
            "dist_kva": round(float(info.get('dist_kva', 0.0)), 3),
            "dist_ratio": round(float(info.get('dist_ratio', 0.0)), 3),
            "phase_imbalance": round(float(info.get('phase_imbalance', 0.0)), 3),
            "custom_label": bool(info.get('custom_label', False))
        })

    def _fhmm_exact_viterbi(self, df_work: pd.DataFrame,
                            machine_states: Dict[int, List[float]],
                            cluster_info: Dict[int, Any],
                            max_comb_states: int = 400,
                            max_points: int = 1500,
                            events: Optional[pd.DataFrame] = None) -> Optional[Dict[str, Any]]:
        """
        PASO 2: FHMM exacto bivariado [P, Q] (MEJORA #1) con priors horarios
        en la transicion (MEJORA #2).

        Se construye un HMM sobre el producto cartesiano de los estados de cada
        equipo: la media de cada estado combinado es (carga base + suma de los
        niveles activos, con componente Q proporcional al ratio Q/P del
        equipo) y la matriz de transicion es el producto de Kronecker
        de las cadenas individuales. Los parametros se fijan analiticamente (sin
        EM) y la secuencia MAP se obtiene con el algoritmo de Viterbi.

        MEJORA #2: cuando se reciben eventos, la probabilidad de transicion
        OFF->ON de cada equipo se modula segun la hora del dia (perfil de
        arranques observado con suavizado de Laplace). La secuencia se decodifica
        por bloques horarios con su matriz de transicion propia; esto reduce los
        falsos positivos nocturnos del Viterbi (ej. compresor a las 3 AM).
        Se devuelven ademas las curvas de minutos ON por hora antes/despues y el
        log-prob sin priors para comparar.

        Devuelve None cuando hmmlearn no esta disponible, cuando el producto de
        estados supera `max_comb_states` (poda -> degrada al descenso por
        eventos) o cuando no hay datos/estados suficientes para modelar.
        """
        if not hmmlearn_available or _GaussianHMM is None:
            return None

        clusters = sorted(cluster_info.keys())
        if not clusters:
            return None

        # Estados por equipo = {Apagado (0 kW)} U niveles de potencia detectados.
        dims: List[int] = []
        levels: List[List[float]] = []
        for c in clusters:
            c_levels = sorted(float(v) for v in machine_states.get(c, []) if float(v) > 0.05)
            if not c_levels:
                c_levels = [float(cluster_info[c].get('avg_delta_p', 0.0))]
            levels.append(c_levels)
            dims.append(len(c_levels) + 1)

        n_comb = int(np.prod(dims))
        if n_comb < 2 or n_comb > max_comb_states:
            return None

        n_points = len(df_work)
        if n_points < 3:
            return None

        # Saneo: NaN/Inf rompen la emision gaussiana y pueden producir un
        # log-prob NaN/-Inf, que es JSON invalido y rompe el JSON.parse del
        # frontend. Se sustituyen por 0 (ausencia de lectura).
        p_total = np.nan_to_num(df_work['P_total'].to_numpy(dtype=float),
                                nan=0.0, posinf=0.0, neginf=0.0)
        # MEJORA #1: Q_total como segunda dimension de la emision.
        if 'Q_total' in df_work.columns:
            q_total = np.abs(np.nan_to_num(
                df_work['Q_total'].to_numpy(dtype=float),
                nan=0.0, posinf=0.0, neginf=0.0))
        else:
            q_total = np.zeros_like(p_total)
        if not np.all(np.isfinite(p_total)) or not np.all(np.isfinite(q_total)):
            return None

        # Submuestreo uniforme para acotar el coste de Viterbi O(T * N^2).
        step = max(1, int(np.ceil(n_points / float(max_points))))
        obs_ds = np.column_stack([p_total[::step], q_total[::step]])
        if len(obs_ds) < 3:
            return None

        # Carga base (percentil 5) y media de cada estado combinado.
        base_p = float(np.percentile(p_total, 5))
        base_q = float(np.percentile(q_total, 5))
        # MEJORA #1: ratio Q/P por equipo (de los deltas del clustering) para
        # construir la componente Q de cada estado combinado.
        q_p_ratios: List[float] = []
        for c in clusters:
            info_c = cluster_info[c]
            nominal = max(0.3, float(info_c.get('avg_delta_p', 0.0)))
            qpr = float(info_c.get('avg_delta_q', 0.0)) / nominal
            q_p_ratios.append(float(np.clip(qpr, 0.0, 5.0)))
        combos = list(_cartesian_product(*[range(d) for d in dims]))
        comb_means = np.array([
            [base_p + sum(levels[i][s - 1] for i, s in enumerate(combo) if s > 0),
             base_q + sum(levels[i][s - 1] * q_p_ratios[i]
                          for i, s in enumerate(combo) if s > 0)]
            for combo in combos
        ], dtype=float)

        # Transicion combinada = producto de Kronecker de las cadenas por equipo.
        stay_p = 0.98
        transmat = np.ones((1, 1), dtype=float)
        for d in dims:
            t_i = np.full((d, d), (1.0 - stay_p) / (d - 1), dtype=float)
            np.fill_diagonal(t_i, stay_p)
            transmat = np.kron(transmat, t_i)

        # Desviacion robusta por dimension (MAD + suelo relativo).
        def _sigma_robust(col: np.ndarray) -> float:
            diffs_c = np.abs(np.diff(col))
            sig_med = float(np.median(diffs_c)) if len(diffs_c) else 0.0
            ptp_c = float(np.max(col) - np.min(col))
            return max(sig_med, 0.02 * max(ptp_c, 1.0), 1e-3)

        sigma_p = _sigma_robust(obs_ds[:, 0])
        # La dimension Q usa su MAD propio con suelo ligado a sigma_p para no
        # sobre-discriminar cuando Q es casi constante.
        sigma_q = max(_sigma_robust(obs_ds[:, 1]), 0.05 * sigma_p)

        try:
            model = _GaussianHMM(n_components=n_comb, covariance_type='diag',
                                 n_iter=0, init_params='', params='')
            model.startprob_ = np.full(n_comb, 1.0 / n_comb, dtype=float)
            model.transmat_ = transmat
            model.means_ = comb_means.reshape(n_comb, 2)
            model.covars_ = np.tile(
                np.array([[sigma_p ** 2, sigma_q ** 2]], dtype=float), (n_comb, 1)
            )
            model.n_features = 2
            logprob, seq = model.decode(obs_ds, algorithm='viterbi')
        except Exception as exc:
            print(f"FHMM exacto no aplicable ({n_comb} estados combinados): {exc}")
            return None

        logprob_val = float(logprob)
        if not np.isfinite(logprob_val):
            # Decodificacion degenerada: se prefiere el fallback por eventos
            # antes que emitir un log-prob no serializable.
            return None

        seq_list = [int(s) for s in np.asarray(seq).flatten()]
        result = {
            "method": "fhmm_exact_viterbi_hmmlearn",
            "features": ["P", "Q"],
            "logprob": round(logprob_val, 2),
            "logprob_no_priors": round(logprob_val, 2),
            "priors_used": False,
            "night_minutes_reduced": 0.0,
            "n_comb_states": n_comb,
            "dims": dims,
            "n_points_decoded": int(len(obs_ds)),
            "n_points_full": int(n_points),
            "downsample_step": int(step),
            "combined_seq_ds": seq_list,
            # Medias de la emision por estado combinado: columna 0 = P (kW),
            # columna 1 = Q (kvar) de la emision bivariada [P, Q].
            "state_means_kw": [round(float(m[0]), 3) for m in comb_means],
            "state_means_q_kw": [round(float(m[1]), 3) for m in comb_means],
        }

        # --- MEJORA #2: priors horarios en la transicion OFF->ON -----------
        # Perfil de arranques por hora y equipo (suavizado de Laplace,
        # media ~1). La secuencia MAP se re-decodifica por bloques horarios
        # con un Viterbi propio de transicion dependiente del tiempo (que
        # hmmlearn no soporta), reduciendo los falsos positivos nocturnos.
        on_mask = np.array([[combo[i] > 0 for i in range(len(dims))] for combo in combos])
        ts = pd.to_datetime(df_work['timestamp'])
        med_dt_min = float(pd.Series(ts).diff().dt.total_seconds().median() or 60.0) / 60.0
        min_per_point = max(med_dt_min * step, 1e-6)
        hours_ds = ts.dt.hour.to_numpy(dtype=int)[::step]

        def _minutes_on_by_hour(sequence: List[int]) -> List[float]:
            on_count = on_mask[np.asarray(sequence, dtype=int)].sum(axis=1)
            by_hour = np.zeros(24, dtype=float)
            np.add.at(by_hour, hours_ds, on_count)
            return [round(float(v), 1) for v in by_hour * min_per_point]

        result["on_minutes_total_before"] = _minutes_on_by_hour(seq_list)
        result["on_minutes_total_after"] = list(result["on_minutes_total_before"])

        if (events is not None and len(events) > 0
                and 'timestamp' in events and 'event_type' in events
                and 'cluster' in events and 'P_total' in df_work.columns
                and len(obs_ds) > 2):
            try:
                alpha = 1.0
                ev_hours = pd.to_datetime(events['timestamp']).dt.hour.to_numpy(dtype=int)
                ev_on = (events['event_type'].astype(str) == 'ON').to_numpy()
                ev_cl = events['cluster'].astype(int).to_numpy()
                hourly_priors: Dict[str, List[float]] = {}
                rates: List[List[float]] = []
                for c in clusters:
                    on_c = ev_on & (ev_cl == c)
                    counts = np.bincount(ev_hours[on_c], minlength=24).astype(float)
                    total_on = float(counts.sum())
                    # Propension relativa por hora (media ~1) con Laplace.
                    rate = (counts + alpha) / (total_on + 24.0 * alpha) * 24.0
                    rate = [round(float(v), 3) for v in np.clip(rate, 0.05, 5.0)]
                    rates.append(rate)
                    hourly_priors[str(c)] = rate

                # Matrices de transicion moduladas por hora: se escala la masa
                # OFF->ON de cada equipo por su rate horario y se renormaliza
                # la fila de salida del estado apagado.
                trans_by_hour: List[np.ndarray] = []
                for h in range(24):
                    mat_h = np.ones((1, 1), dtype=float)
                    for i, d in enumerate(dims):
                        t_i = np.full((d, d), (1.0 - stay_p) / (d - 1), dtype=float)
                        np.fill_diagonal(t_i, stay_p)
                        scale_h = float(rates[i][h])
                        if scale_h != 1.0:
                            t_i[0, 1:] *= scale_h
                            t_i[0] /= t_i[0].sum()
                        mat_h = np.kron(mat_h, t_i)
                    trans_by_hour.append(mat_h)

                # Log-verosimilitudes de emision bivariada [P, Q] (gaussiana
                # diagonal identica a la del modelo hmmlearn).
                covars = np.tile(
                    np.array([[sigma_p ** 2, sigma_q ** 2]], dtype=float), (n_comb, 1)
                )
                diff_e = obs_ds[:, None, :] - comb_means[None, :, :]
                mahal = (diff_e ** 2 / covars[None, :, :]).sum(axis=2)
                log_det = np.log(covars).sum(axis=1)
                obs_ll = -0.5 * (2.0 * np.log(2.0 * np.pi) + log_det[None, :] + mahal)

                # Viterbi propio con transicion dependiente del tiempo (hmmlearn
                # no soporta matrices de transicion por paso temporal).
                log_T_by_hour = [np.log(m + 1e-300) for m in trans_by_hour]


                def _viterbi_time(o_ll: np.ndarray) -> Tuple[np.ndarray, float]:
                    t_len, n_n = o_ll.shape
                    delta = np.full(n_n, np.log(1.0 / n_n)) + o_ll[0]
                    psi = np.zeros((t_len, n_n), dtype=int)
                    for t in range(1, t_len):
                        cand = delta[:, None] + log_T_by_hour[int(hours_ds[t])]
                        psi[t] = cand.argmax(axis=0)
                        delta = cand.max(axis=0) + o_ll[t]
                    seq_t = np.zeros(t_len, dtype=int)
                    seq_t[-1] = int(delta.argmax())
                    for t in range(t_len - 1, 0, -1):
                        seq_t[t - 1] = int(psi[t, seq_t[t]])
                    return seq_t, float(delta.max())

                seq2, lp2 = _viterbi_time(obs_ll)
                if np.isfinite(lp2):
                    after = _minutes_on_by_hour([int(s) for s in seq2])
                    night_hours = (22, 23, 0, 1, 2, 3, 4, 5)
                    night_b = float(sum(result["on_minutes_total_before"][h] for h in night_hours))
                    night_a = float(sum(after[h] for h in night_hours))
                    result["night_minutes_reduced"] = round(max(0.0, night_b - night_a), 1)
                    result["combined_seq_ds"] = [int(s) for s in seq2]
                    result["on_minutes_total_after"] = after
                    result["logprob"] = round(lp2, 2)
                    result["logprob_priors"] = round(lp2, 2)
                    result["priors_used"] = True
                    result["hourly_priors"] = hourly_priors
                    result["method"] = "fhmm_exact_viterbi_priors_hmmlearn"
            except Exception as exc:
                print(f"Priors horarios no aplicables: {exc}")

        return result

    # ------------------------------------------------------------------
    # MEJORA #13: informe de fugas / standby a partir del residuo.
    # El baseline tras desagregar cuantifica el consumo fantasma: kW
    # minimos nocturnos x tarifa = ahorro potencial anual. Analisis de
    # negocio directo sin dependencias nuevas (numpy/pandas).
    # ------------------------------------------------------------------
    @staticmethod
    def _standby_report(df_work, p_total, baseline_curve):
        """Cuantifica el consumo fantasma (residuo no atribuido).

        Devuelve KPIs JSON-safe: percentiles globales y nocturnos
        (ventana 00:00-05:00), cuota sobre el total, energia del periodo
        y proyeccion anual, curva de duracion de carga (decimada a 200
        puntos) e histograma (40 bines). Dict vacio si <10 muestras.
        """
        try:
            n = int(len(p_total))
            if n < 10 or len(baseline_curve) != n:
                return {}
            base = np.clip(np.nan_to_num(np.asarray(baseline_curve, dtype=float),
                                         nan=0.0, posinf=0.0, neginf=0.0), 0.0, None)
            tot = np.clip(np.nan_to_num(np.asarray(p_total, dtype=float),
                                        nan=0.0, posinf=0.0, neginf=0.0), 0.0, None)
            if not np.any(np.isfinite(base)):
                return {}

            ts = pd.to_datetime(df_work['timestamp'], errors='coerce') \
                if 'timestamp' in df_work.columns else None

            def _pct(a, q):
                try:
                    return float(np.percentile(a, q))
                except Exception:
                    return 0.0

            p = {'p5': _pct(base, 5), 'p10': _pct(base, 10),
                 'p25': _pct(base, 25), 'p50': _pct(base, 50),
                 'mean': float(np.mean(base)), 'max': float(np.max(base))}
            night = {'p10': 0.0, 'p50': 0.0, 'mean': 0.0,
                     'samples': 0, 'window': '00:00-05:00'}
            try:
                if ts is not None and ts.notna().any():
                    hours = ts.dt.hour.to_numpy()
                    mask = (hours >= 0) & (hours < 5)
                    if int(np.sum(mask)) >= 3:
                        nb = base[mask]
                        night = {'p10': _pct(nb, 10), 'p50': _pct(nb, 50),
                                 'mean': float(np.mean(nb)),
                                 'samples': int(np.sum(mask)),
                                 'window': '00:00-05:00'}
            except Exception:
                pass

            mean_tot = float(np.mean(tot)) if n else 0.0
            share = float(np.clip(p['mean'] / mean_tot, 0.0, 1.0)) \
                if mean_tot > 0 else 0.0

            # Energia del periodo por integracion trapezoidal (timestamps).
            energy_kwh, hours_total = 0.0, 0.0
            try:
                if ts is not None and ts.notna().sum() >= 2:
                    t = ts.dropna()
                    dt_h = t.diff().dt.total_seconds().fillna(0).to_numpy() / 3600.0
                    dt_h = np.clip(dt_h, 0, None)
                    if len(dt_h) == n:
                        energy_kwh = float(np.sum(base * dt_h))
                        hours_total = float(np.sum(dt_h))
            except Exception:
                pass
            if hours_total <= 0 and n >= 2:
                try:
                    t = pd.to_datetime(df_work['timestamp'],
                                       errors='coerce').dropna()
                    step_h = float(t.diff().dt.total_seconds().median() / 3600.0)
                    if step_h > 0 and np.isfinite(step_h):
                        hours_total = step_h * n
                        energy_kwh = float(np.mean(base) * hours_total)
                except Exception:
                    pass
            annual_kwh = float(energy_kwh / hours_total * 8760.0) \
                if hours_total > 0 else 0.0

            # Curva de duracion de carga (ordenada desc, decimada a 200 pts).
            m = min(200, n)
            idx = np.linspace(0, n - 1, m).astype(int)
            dur_base = np.sort(base)[::-1][idx]
            dur_tot = np.sort(tot)[::-1][idx]
            pct_axis = np.arange(m) / max(1, m - 1) * 100.0

            try:
                counts, edges = np.histogram(base, bins=40)
                hist = {'counts': [int(c) for c in counts],
                        'edges': [round(float(e), 3) for e in edges]}
            except Exception:
                hist = {'counts': [], 'edges': []}

            return {
                'samples': n,
                'hours_covered': round(hours_total, 2),
                'baseline_kw': {k: round(float(v), 3) for k, v in p.items()},
                'night_kw': {k: (round(float(v), 3)
                                 if isinstance(v, (int, float)) else v)
                             for k, v in night.items()},
                'share_pct': round(share * 100.0, 2),
                'energy_kwh': round(energy_kwh, 3),
                'annual_kwh': round(annual_kwh, 1),
                'duration_pct': [round(float(v), 2) for v in pct_axis],
                'duration_baseline_kw': [round(float(v), 3) for v in dur_base],
                'duration_total_kw': [round(float(v), 3) for v in dur_tot],
                'hist': hist,
                'method': 'Residuo tras desagregacion (P_total - S maquinas); '
                          'noche 00:00-05:00; proyeccion anual = media x 8760 h.',
            }
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # MEJORA #14: anomalias sobre el residuo (baseline tras desagregar).
    # MAE movil del residuo vs umbral robusto (mediana + 3*1.4826*MAD):
    # picos sostenidos = degradacion de equipo o carga nueva no
    # catalogada. Mismo estilo JSON-safe que _standby_report.
    # ------------------------------------------------------------------
    @staticmethod
    def _residual_anomalies(df_work, p_total, baseline_curve):
        """Detecta picos sostenidos del residuo (MAE movil + MAD).

        Devuelve dict JSON-safe con los percentiles del MAE movil, el
        umbral robusto (mediana + 3*1.4826*MAD), las series decimadas
        (<=400 pts) para la grafica y los eventos sostenidos (runs de
        >= min_run_samples muestras) con sus marcas de tiempo. Dict
        vacio si hay <30 muestras o longitudes incoherentes.
        """
        try:
            n = int(len(baseline_curve))
            if n < 30 or len(p_total) != n:
                return {}
            base = np.clip(np.nan_to_num(np.asarray(baseline_curve,
                                                     dtype=float),
                                         nan=0.0, posinf=0.0, neginf=0.0),
                           0.0, None)

            ts = pd.to_datetime(df_work['timestamp'], errors='coerce') \
                if 'timestamp' in df_work.columns else None
            dt_min = 10.0 / 60.0
            if ts is not None and int(ts.notna().sum()) >= 2:
                step = float(ts.dropna().diff().dt.total_seconds().median())
                if np.isfinite(step) and step > 0:
                    dt_min = step / 60.0

            # Ventana movil de ~30 min, acotada a [5, n/4] muestras.
            want = max(5, int(round(30.0 / max(dt_min, 1e-9))))
            w = int(np.clip(want, 5, max(5, n // 4)))
            mae = np.convolve(base, np.ones(w) / float(w), mode='valid')
            if int(mae.size) < 10:
                return {}

            def _pct(arr, q):
                try:
                    return float(np.percentile(arr, q))
                except Exception:
                    return 0.0

            center = float(np.median(mae))
            mad = float(np.median(np.abs(mae - center)))
            floor = max(3.0 * 1.4826 * mad, 0.05 * abs(center), 1e-6)
            thr = center + floor
            mask = mae > thr

            # Runs contiguos de anomalia; al menos la mitad de la ventana.
            min_run = max(3, w // 2)
            padded = np.concatenate(([0], mask.astype(np.int8), [0]))
            edges = np.diff(padded)
            starts = np.where(edges == 1)[0]
            ends = np.where(edges == -1)[0]
            sustained = []
            for s0, e0 in zip(starts, ends):
                if int(e0 - s0) >= min_run:
                    sustained.append((int(s0), int(e0)))

            ts_ok = ts is not None and int(ts.notna().sum()) >= n
            tsv = ts.to_numpy() if ts_ok else None
            events = []
            for s0, e0 in sustained[:50]:
                i0 = min(n - 1, s0 + w // 2)
                i1 = min(n - 1, e0 - 1 + w // 2)
                if i1 < i0:
                    i1 = i0
                iso0 = iso1 = ''
                if tsv is not None:
                    try:
                        iso0 = pd.Timestamp(tsv[i0]).isoformat()
                        iso1 = pd.Timestamp(tsv[i1]).isoformat()
                    except Exception:
                        iso0 = iso1 = ''
                events.append({
                    'start_pct': round(i0 / max(1, n - 1) * 100.0, 2),
                    'end_pct': round(i1 / max(1, n - 1) * 100.0, 2),
                    'start_iso': iso0,
                    'end_iso': iso1,
                    'duration_min': round((i1 - i0 + 1) * dt_min, 1),
                    'peak_mae_kw': round(float(np.max(mae[s0:e0])), 3),
                })

            # Series decimadas a <=400 puntos (etiqueta en % del eje X).
            k = min(400, int(mae.size))
            idx = np.unique(np.linspace(0, mae.size - 1, k).astype(int))
            mid = np.clip(idx + w // 2, 0, n - 1)
            labels_pct = [round(float(v) / max(1, n - 1) * 100.0, 2)
                          for v in mid]
            mae_series = [round(float(v), 3) for v in mae[idx]]
            thr_series = [round(thr, 3)] * len(mae_series)

            return {
                'samples': n,
                'window_samples': w,
                'window_minutes': round(w * dt_min, 1),
                'min_run_samples': min_run,
                'center_kw': round(center, 3),
                'threshold_kw': round(thr, 3),
                'mae_kw': {'p50': round(_pct(mae, 50), 3),
                           'p95': round(_pct(mae, 95), 3),
                           'max': round(float(np.max(mae)), 3)},
                'n_events': len(sustained),
                'anomalous_pct': round(float(np.mean(mask)) * 100.0, 2),
                'max_mae_kw': round(float(np.max(mae)), 3),
                'labels_pct': labels_pct,
                'mae_series': mae_series,
                'threshold_series': thr_series,
                'events': events,
                'method': 'MAE movil (~30 min) del residuo; umbral = '
                          'mediana + 3*1.4826*MAD; eventos >= min_run '
                          'muestras (max 50); series decimadas <=400 pts.',
            }
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # MEJORA #16: coste economico por equipo (tarifa horaria).
    # Cruza la energia desagregada con una tarifa por periodos
    # (valle/llano/punta del 2.0TD peninsular por defecto, editable via
    # el parametro tariff) y desglosa el gasto por equipo, por periodo
    # y por turno (manana/tarde/noche). Sin dependencias nuevas.
    # ------------------------------------------------------------------
    # Tarifa de ejemplo en EUR/kWh. Reglas 2.0TD peninsular: punta
    # 10:00-14:00 y 18:00-22:00 (laborables); llano 08:00-10:00,
    # 14:00-18:00 y 22:00-24:00 (laborables); valle 00:00-08:00
    # (laborables) y todo el fin de semana.
    DEFAULT_TARIFF = {
        "name": "2.0TD peninsula (ejemplo editable)",
        "currency": "EUR",
        "rates_eur_kwh": {"valle": 0.0769, "llano": 0.1233, "punta": 0.1641},
    }

    @staticmethod
    def _cost_report(df_work, disagg_power, baseline_curve, cluster_info,
                     tariff=None):
        """Coste EUR de la energia desagregada por tarifa horaria.

        Devuelve dict JSON-safe con la tarifa aplicada, horas cubiertas,
        desglose por periodo (valle/llano/punta), por turno (manana/
        tarde/noche), por equipo (con proyeccion mensual), el coste del
        residuo (standby) y el total. Dict vacio si faltan timestamps
        o la serie es demasiado corta.
        """
        try:
            tariff = dict(tariff) if tariff else dict(NILMEngine.DEFAULT_TARIFF)
            rates = dict(tariff.get('rates_eur_kwh') or {})
            for k in ('valle', 'llano', 'punta'):
                rates.setdefault(k, 0.0)
                rates[k] = float(rates[k])

            if 'timestamp' not in df_work.columns:
                return {}
            ts = pd.to_datetime(df_work['timestamp'], errors='coerce')
            n = len(df_work)
            if n < 2 or int(ts.notna().sum()) < 2:
                return {}
            dt_h = ts.diff().dt.total_seconds().fillna(0).to_numpy(dtype=float) \
                / 3600.0
            dt_h = np.clip(dt_h, 0.0, None)
            if float(dt_h.sum()) <= 0:
                step_h = float(ts.dropna().diff().dt.total_seconds().median()
                               / 3600.0)
                if not (step_h > 0 and np.isfinite(step_h)):
                    return {}
                dt_h = np.full(n, step_h)
            hours_covered = float(dt_h.sum())
            if hours_covered <= 0:
                return {}

            def _clean(a):
                return np.clip(np.nan_to_num(np.asarray(a, dtype=float),
                                             nan=0.0, posinf=0.0, neginf=0.0),
                               0.0, None)

            # Las curvas deben alinearse con df_work (misma convencion
            # estricta que _standby_report).
            if len(baseline_curve) != n or \
                    any(len(_clean(a)) != n for a in disagg_power.values()):
                return {}

            # Mascara de periodo tarifario (particion muestr a muestra).
            hours = ts.dt.hour.to_numpy()
            dow = ts.dt.dayofweek.to_numpy()  # 0=lunes ... 6=domingo
            weekend = dow >= 5
            m_valle = weekend | (hours < 8)
            m_punta = (~weekend) & (((hours >= 10) & (hours < 14))
                                    | ((hours >= 18) & (hours < 22)))
            m_llano = (~m_valle) & (~m_punta)

            # Potencia total: P_total si existe, si no la suma de
            # equipos + residuo (misma convencion que el pipeline).
            if 'P_total' in df_work.columns:
                p_total = _clean(df_work['P_total'].to_numpy())
            else:
                p_total = np.zeros(n)
                for arr in disagg_power.values():
                    a = _clean(arr)
                    if len(a) == n:
                        p_total += a
                b = _clean(baseline_curve)
                if len(b) == n:
                    p_total += b

            # Coste por muestra (EUR) = P[kW] x dt[h] x tarifa[hora].
            rate_arr = np.zeros(n)
            rate_arr[m_valle] = rates['valle']
            rate_arr[m_llano] = rates['llano']
            rate_arr[m_punta] = rates['punta']
            cost_arr = p_total * dt_h * rate_arr
            month_factor = 730.0 / hours_covered  # 8760 h / 12 meses

            periods = []
            for pname, mask in (('valle', m_valle), ('llano', m_llano),
                                ('punta', m_punta)):
                e = float(np.sum(p_total[mask] * dt_h[mask]))
                periods.append({
                    'period': pname,
                    'hours': round(float(dt_h[mask].sum()), 2),
                    'energy_kwh': round(e, 3),
                    'cost_eur': round(float(np.sum(cost_arr[mask])), 2),
                })

            # Turnos: manana 06-14, tarde 14-22, noche 22-06.
            m_manana = (hours >= 6) & (hours < 14)
            m_tarde = (hours >= 14) & (hours < 22)
            m_noche = (~m_manana) & (~m_tarde)
            shifts = []
            for sname, mask in (('manana', m_manana), ('tarde', m_tarde),
                                ('noche', m_noche)):
                e = float(np.sum(p_total[mask] * dt_h[mask]))
                shifts.append({
                    'shift': sname,
                    'hours': round(float(dt_h[mask].sum()), 2),
                    'energy_kwh': round(e, 3),
                    'cost_eur': round(float(np.sum(cost_arr[mask])), 2),
                })

            machines = []
            for c in sorted(disagg_power.keys()):
                p = _clean(disagg_power[c])
                if len(p) != n:
                    continue
                e = float(np.sum(p * dt_h))
                ce = float(np.sum(p * dt_h * rate_arr))
                info = (cluster_info or {}).get(c, {})
                machines.append({
                    'id': c,
                    'name': str(info.get('name', f'Equipo {c}')),
                    'color': str(info.get('color', '#888888')),
                    'energy_kwh': round(e, 3),
                    'cost_eur': round(ce, 2),
                    'cost_month_eur': round(ce * month_factor, 2),
                })

            res_e, res_c = 0.0, 0.0
            b = _clean(baseline_curve)
            if len(b) == n:
                res_e = float(np.sum(b * dt_h))
                res_c = float(np.sum(b * dt_h * rate_arr))

            total_e = float(np.sum(p_total * dt_h))
            total_c = float(np.sum(cost_arr))
            for m in machines:
                m['cost_share_pct'] = round(
                    m['cost_eur'] / total_c * 100.0, 1) if total_c > 0 \
                    else 0.0

            return {
                'tariff': {
                    'name': str(tariff.get('name', 'tarifa personalizada')),
                    'currency': str(tariff.get('currency', 'EUR')),
                    'rates_eur_kwh': {k: round(v, 4)
                                      for k, v in rates.items()},
                },
                'hours_covered': round(hours_covered, 2),
                'periods': periods,
                'shifts': shifts,
                'machines': machines,
                'residual': {
                    'energy_kwh': round(res_e, 3),
                    'cost_eur': round(res_c, 2),
                    'cost_month_eur': round(res_c * month_factor, 2),
                },
                'total': {
                    'energy_kwh': round(total_e, 3),
                    'cost_eur': round(total_c, 2),
                    'cost_month_eur': round(total_c * month_factor, 2),
                },
                'method': 'Energia desagregada x tarifa horaria por periodos '
                          '(2.0TD: punta 10-14/18-22, llano 08-10/14-18/22-24, '
                          'valle 00-08 y fines de semana); turnos 06-14/14-22/'
                          '22-06; proyeccion mensual = coste x 730 h / horas.',
            }
        except Exception:
            return {}

    def _validate_reconstruction_error(self, df_work, disagg_power, baseline_curve) -> Dict[str, Any]:
        """PASO 3: error de reconstruccion global (MAE/RMSE/MAPE) y porcentaje
        de energia explicada por baseline + suma de curvas desagregadas."""
        p_total = pd.to_numeric(df_work['P_total'], errors='coerce').fillna(0.0).to_numpy(dtype=float)
        reconstructed = np.asarray(baseline_curve, dtype=float).copy()
        for _c, curve in disagg_power.items():
            reconstructed += np.nan_to_num(np.asarray(curve, dtype=float), nan=0.0)
        err = p_total - reconstructed
        mae = float(np.mean(np.abs(err)))
        rmse = float(np.sqrt(np.mean(err ** 2)))
        mape = float(np.mean(np.abs(err) / np.maximum(np.abs(p_total), 0.05)) * 100.0)
        total_energy_meas = float(p_total.sum())
        energy_rec = float(np.maximum(reconstructed, 0.0).sum())
        explained = energy_rec / total_energy_meas * 100.0 if total_energy_meas > 0 else 0.0
        # RE (Relative Error in Total Energy): error del acumulado final, sin
        # importar el "cuando". NEP (Normalized Error in Power): error absoluto
        # normalizado por la energia real total (comparable entre aparatos).
        re_pct = abs(total_energy_meas - energy_rec) / total_energy_meas * 100.0 if total_energy_meas > 0 else 0.0
        nep = float(np.sum(np.abs(err)) / total_energy_meas) if total_energy_meas > 0 else 0.0
        return {
            "mae_kw": round(mae, 3),
            "rmse_kw": round(rmse, 3),
            "mape_pct": round(mape, 1),
            "energy_explained_pct": round(explained, 1),
            "re_pct": round(re_pct, 1),
            "nep": round(nep, 3),
        }

    @staticmethod
    def _build_active_mask(timestamps: np.ndarray, on_times: np.ndarray,
                           off_times: np.ndarray, n_points: int) -> np.ndarray:
        """Referencia ON/OFF: cada evento ON activa el equipo hasta su proximo
        OFF (o hasta el final si el OFF no fue detectado)."""
        active = np.zeros(n_points, dtype=bool)
        paired = sorted([(t, 1) for t in on_times] + [(t, 0) for t in off_times])
        start = None
        for t, kind in paired:
            idx = int(np.searchsorted(timestamps, t))
            idx = min(max(idx, 0), n_points)
            if kind == 1 and start is None:
                start = idx
            elif kind == 0 and start is not None and idx > start:
                active[start:idx] = True
                start = None
        if start is not None and start < n_points:
            active[start:] = True
        return active

    @staticmethod
    def _match_transitions(detected, reference, tol_s):
        """MEJORA #11: pareo greedy de transiciones (arranques) para el Gantt.

        Empareja cada borde OFF->ON detectado en la curva desagregada con el
        evento ON de referencia mas cercano dentro de una tolerancia temporal
        (una referencia solo puede emparejarse una vez). Devuelve TP/FP/FN,
        precision/recall/F1 y el desfase temporal (s) de los aciertos.
        """
        det = np.sort(np.asarray(detected, dtype='datetime64[ns]'))
        ref = np.sort(np.asarray(reference, dtype='datetime64[ns]'))
        tol = np.timedelta64(int(round(float(tol_s) * 1000)), 'ms')
        used = np.zeros(len(ref), dtype=bool)
        delays: List[float] = []
        tp = 0
        j = 0
        for d in det:
            # Referencias anteriores a d-tol no pueden emparejarse jamas.
            while j < len(ref) and ref[j] < d - tol:
                j += 1
            best, best_gap = -1, None
            k = j
            while k < len(ref) and ref[k] <= d + tol:
                if not used[k]:
                    gap = abs(int(d - ref[k]))
                    if best < 0 or gap < best_gap:
                        best, best_gap = k, gap
                k += 1
            if best >= 0:
                used[best] = True
                tp += 1
                delays.append(best_gap / 1e9)
        fp = int(len(det)) - tp
        fn = int(len(ref)) - tp
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) \
            if (precision + recall) > 0 else 0.0
        return {
            "tp": int(tp), "fp": int(fp), "fn": int(fn),
            "detected": int(len(det)), "reference": int(len(ref)),
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "dt_median_s": round(float(np.median(delays)), 2) if delays else 0.0,
            "dt_max_s": round(float(np.max(delays)), 2) if delays else 0.0,
            "tolerance_s": round(float(tol_s), 2),
        }

    @staticmethod
    def _bootstrap_ci(cells, metrics, n_boot=1000, seed=42, ci_pct=95):
        """MEJORA #12: intervalos de confianza (bootstrap) de F1/P/R.

        Remuestrea los pares (referencia, prediccion) como una multinomial
        sobre las cuatro celdas de la matriz de confusion — equivalente al
        remuestreo no parametrico de las observaciones — y recalcula las
        metricas en cada iteracion. Semilla fija: resultado reproducible.
        Devuelve {metrica: {lo, hi, mean, half}} con los percentiles del IC.
        """
        try:
            tp = max(0, int(cells.get("tp", 0)))
            fp = max(0, int(cells.get("fp", 0)))
            fn = max(0, int(cells.get("fn", 0)))
            tn = max(0, int(cells.get("tn", 0)))
            total = tp + fp + fn + tn
            if total <= 0 or n_boot < 20:
                return {}
            probs = np.array([tp, fp, fn, tn], dtype=float) / float(total)
            rng = np.random.default_rng(int(seed))
            d = rng.multinomial(total, probs, size=int(n_boot))
            p_tp = d[:, 0].astype(float)
            p_fp = d[:, 1].astype(float)
            p_fn = d[:, 2].astype(float)
            prec = np.divide(p_tp, p_tp + p_fp, out=np.zeros_like(p_tp),
                             where=(p_tp + p_fp) > 0)
            rec = np.divide(p_tp, p_tp + p_fn, out=np.zeros_like(p_tp),
                            where=(p_tp + p_fn) > 0)
            f1 = np.divide(2.0 * prec * rec, prec + rec,
                           out=np.zeros_like(prec), where=(prec + rec) > 0)
            series = {"precision": prec, "recall": rec, "f1": f1}
            alpha = (100.0 - float(ci_pct)) / 2.0
            out = {}
            for name in metrics:
                v = series.get(name)
                if v is None:
                    continue
                lo, hi = np.percentile(v, [alpha, 100.0 - alpha])
                out[name] = {
                    "lo": round(float(lo), 3), "hi": round(float(hi), 3),
                    "mean": round(float(np.mean(v)), 3),
                    "half": round(float((hi - lo) / 2.0), 3),
                }
            return out
        except Exception:
            return {}

    def _validate_machine(self, df_work, events, cluster_info, disagg_power,
                          c, timestamps) -> Dict[str, Any]:
        """PASO 3: validacion de un equipo (consistencia de saltos ON y
        matriz de confusion ON/OFF contra la referencia de eventos)."""
        info = cluster_info[c]
        n_points = len(df_work)
        c_events = events[events['cluster'] == c].sort_values('timestamp') if len(events) else events
        c_curve = (np.nan_to_num(np.asarray(disagg_power[c], dtype=float), nan=0.0)
                   if c in disagg_power else np.zeros(n_points, dtype=float))

        nominal = max(0.05, float(info.get('avg_delta_p', 0.0)))
        jump_errors: List[float] = []
        on_times = np.array([], dtype='datetime64[ns]')
        off_times = np.array([], dtype='datetime64[ns]')
        if len(c_events) > 0:
            on_mask = (c_events['event_type'] == 'ON').to_numpy()
            ev_times = pd.to_datetime(c_events['timestamp']).to_numpy(dtype='datetime64[ns]')
            ev_deltas = np.abs(pd.to_numeric(c_events['delta_P'], errors='coerce').fillna(0.0).to_numpy())
            on_times = ev_times[on_mask]
            off_times = ev_times[~on_mask]
            for i in np.nonzero(on_mask)[0]:
                idx = int(np.searchsorted(timestamps, ev_times[i]))
                if idx < 2 or idx >= n_points - 2:
                    continue
                pre = float(np.mean(c_curve[max(0, idx - 2):idx]))
                post = float(np.mean(c_curve[idx:min(n_points, idx + 3)]))
                jump = post - pre
                if jump > 0:
                    jump_errors.append(abs(jump - float(ev_deltas[i])))

        threshold = max(0.05 * nominal, 0.02)
        pred_on = c_curve > threshold
        active = self._build_active_mask(timestamps, on_times, off_times, n_points)
        tp = int(np.sum(active & pred_on))
        fp = int(np.sum(~active & pred_on))
        fn = int(np.sum(active & ~pred_on))
        tn = int(np.sum(~active & ~pred_on))
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        accuracy = (tp + tn) / max(1, tp + fp + fn + tn)

        # MEJORA #11: metrica de transiciones (arranques) para el Gantt:
        # bordes OFF->ON de la curva desagregada vs eventos ON de referencia.
        det_idx = np.nonzero(pred_on[1:] & ~pred_on[:-1])[0] + 1 \
            if n_points > 1 else np.array([], dtype=int)
        det_times = timestamps[det_idx]
        dt_med_s = float(np.median(np.diff(timestamps)) / np.timedelta64(1, 's')) \
            if n_points > 1 else 10.0
        if not np.isfinite(dt_med_s) or dt_med_s <= 0:
            dt_med_s = 10.0
        transitions = self._match_transitions(det_times, on_times,
                                              max(60.0, 2.0 * dt_med_s))

        # Metricas de regresion (energia) contra la referencia por eventos:
        # la senal de referencia vale el nivel nominal del equipo mientras esta
        # activo y 0 kW cuando no. MAE/RMSE en kW; RE = error relativo de la
        # energia total acumulada; NEP = error de potencia normalizado.
        ref_signal = np.where(active, nominal, 0.0)
        reg_err = c_curve - ref_signal
        reg_mae = float(np.mean(np.abs(reg_err)))
        reg_rmse = float(np.sqrt(np.mean(reg_err ** 2)))
        e_ref = float(ref_signal.sum())
        e_pred = float(np.maximum(c_curve, 0.0).sum())
        re_pct = abs(e_ref - e_pred) / e_ref * 100.0 if e_ref > 0 else 0.0
        nep = float(np.sum(np.abs(reg_err)) / e_ref) if e_ref > 0 else 0.0
        return {
            "id": int(c),
            "name": info['name'],
            "color": info['color'],
            "n_on_events": int(len(on_times)),
            "jump_mae_kw": round(float(np.mean(jump_errors)), 3) if jump_errors else 0.0,
            "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "accuracy": round(accuracy, 3),
            "transitions": transitions,
            "reg_mae_kw": round(reg_mae, 3),
            "reg_rmse_kw": round(reg_rmse, 3),
            "re_pct": round(re_pct, 1),
            "nep": round(nep, 3),
        }

    def _validate_disaggregation(self, df_work, events, cluster_info,
                                 disagg_power, baseline_curve) -> Dict[str, Any]:
        """PASO 3: valida la desagregacion (error de reconstruccion global +
        confusion ON/OFF por equipo y global)."""
        if len(df_work) < 3:
            return {}
        timestamps = pd.to_datetime(df_work['timestamp']).to_numpy(dtype='datetime64[ns]')
        machines = []
        cm = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
        for c in sorted(cluster_info.keys()):
            m = self._validate_machine(df_work, events, cluster_info, disagg_power, c, timestamps)
            machines.append(m)
            for k in cm:
                cm[k] += m["confusion"][k]
        precision = cm["tp"] / (cm["tp"] + cm["fp"]) if (cm["tp"] + cm["fp"]) > 0 else 0.0
        recall = cm["tp"] / (cm["tp"] + cm["fn"]) if (cm["tp"] + cm["fn"]) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        accuracy = (cm["tp"] + cm["tn"]) / max(1, sum(cm.values()))
        # MEJORA #11: agregado global de transiciones (sumas de conteos).
        tr = {"tp": 0, "fp": 0, "fn": 0, "detected": 0, "reference": 0}
        for m in machines:
            t = m.get("transitions") or {}
            for k in tr:
                tr[k] += int(t.get(k, 0))
        p_t = tr["tp"] / (tr["tp"] + tr["fp"]) if (tr["tp"] + tr["fp"]) > 0 else 0.0
        r_t = tr["tp"] / (tr["tp"] + tr["fn"]) if (tr["tp"] + tr["fn"]) > 0 else 0.0
        f1_t = 2 * p_t * r_t / (p_t + r_t) if (p_t + r_t) > 0 else 0.0
        med_ms = [m["transitions"]["dt_median_s"] for m in machines
                  if m.get("transitions") and m["transitions"]["tp"] > 0]
        tr_global = {**tr,
                     "precision": round(p_t, 3), "recall": round(r_t, 3),
                     "f1": round(f1_t, 3),
                     "dt_median_s": round(float(np.median(med_ms)), 2) if med_ms else 0.0,
                     "dt_max_s": round(max((m["transitions"]["dt_max_s"]
                                            for m in machines if m.get("transitions")),
                                           default=0.0), 2)}
        # MEJORA #12: intervalos de confianza (bootstrap) de las metricas
        # (remuestreo multinomial de las celdas, semilla fija -> reproducible).
        conf_ci = self._bootstrap_ci(cm, ("precision", "recall", "f1"))
        tr_ci = self._bootstrap_ci(tr, ("precision", "recall", "f1"))
        confidence = {
            "n_boot": 1000, "ci_pct": 95, "seed": 42,
            "method": "Bootstrap multinomial sobre las celdas de la matriz "
                      "(remuestreo de observaciones); IC por percentiles "
                      "2.5/97.5 con semilla fija (reproducible).",
            "confusion_global": conf_ci,
            "transitions_global": tr_ci,
        } if conf_ci else {}
        return {
            "reconstruction": self._validate_reconstruction_error(df_work, disagg_power, baseline_curve),
            "confusion_global": {**cm, "precision": round(precision, 3),
                                 "recall": round(recall, 3), "f1": round(f1, 3),
                                 "accuracy": round(accuracy, 3)},
            "transitions_global": tr_global,
            "confidence": confidence,
            "machines": machines,
        }

    def analyze_dataset(self, dataset_id: str,
                        n_clusters: int = 4,
                        algorithm: str = "kmeans",
                        current_threshold: float = 2.0,
                        power_threshold: float = 1.0,
                        use_fhmm: bool = False,
                        max_states: int = 3,
                        labels: dict = None,
                        auto_k: bool = False,
                        reuse_model: bool = False,
                        pairing_method: str = "auto",
                        detection_method: str = "threshold",
                        min_on_minutes: float = 0.0,
                        min_off_minutes: float = 0.0) -> Dict[str, Any]:
        """
        Executes full NILM pipeline and returns structured JSON-ready results.
        """
        if labels is None:
            labels = self.dm.get_labels(dataset_id)

        df = self.dm.load_dataset(dataset_id)
        df_work, events = self.detect_events(df, current_threshold,
                                            power_threshold,
                                            detection_method=detection_method)
        # MEJORA #7: informe del detector de cambios (umbral/CUSUM/hibrido).
        change_points = dict(getattr(self, '_change_points_report', {}) or {})

        nilmtk_states = self.estimate_nilmtk_power_states(df_work)
        
        # MEJORA #6: seleccion automatica de K (Silhouette/Davies-Bouldin)
        # antes de agrupar; requested_k conserva el valor pedido por el usuario.
        requested_k = int(n_clusters)
        k_selection: Dict[str, Any] = {}
        if auto_k and len(events) >= 4:
            try:
                k_selection = self._auto_select_k(self._feature_frame(events))
                if int(k_selection.get('k') or 0) >= 1:
                    n_clusters = int(k_selection['k'])
            except Exception:
                k_selection = {}
        # MEJORA #17: reutilizar el modelo persistido del sitio (centroides,
        # scaler y etiquetas) para etiquetado consistente entre mediciones.
        saved_model = self.load_model(dataset_id) if reuse_model else {}
        events_clustered, cluster_info = self.cluster_appliances(
            events, n_clusters=n_clusters, algorithm=algorithm,
            custom_labels=labels, saved_model=saved_model or None
        )
        n_clusters = len(cluster_info)
        if reuse_model:
            _k_saved = int(saved_model.get('k') or 0)
            model_reuse = {
                'requested': True,
                'reused': bool(saved_model) and _k_saved == n_clusters,
                'k': _k_saved,
                'saved_at': str(saved_model.get('saved_at', '')),
            }
        else:
            model_reuse = {'requested': False, 'reused': False,
                           'k': 0, 'saved_at': ''}
        # Persistir tras el fit para la proxima medicion (MEJORA #17).
        self.save_model(dataset_id, cluster_info)
        n_on_total = int((events['event_type'] == 'ON').sum()) if len(events) else 0
        if n_on_total == 0:
            warning = "Sin arranques detectados con el umbral actual: baja el umbral de corriente y re-ejecuta el analisis."
        elif n_clusters < requested_k:
            warning = f"Solo {n_on_total} arranques detectados: equipos reducidos a {n_clusters} (pedidos {requested_k})."
        else:
            warning = ""
        
        fhmm_exact = None
        if use_fhmm and len(events_clustered) > 0:
            machine_states = self.estimate_machine_states(df_work, cluster_info, events_clustered, max_states)
            # PASO 2: decodificacion MAP sobre el producto cartesiano de estados.
            fhmm_exact = self._fhmm_exact_viterbi(
                df_work, machine_states, cluster_info, events=events_clustered
            )
            disagg_power, baseline_curve, timeline, machine_stats = self.disaggregate_load_fhmm(
                df_work, events_clustered, cluster_info, machine_states,
                min_on_minutes=min_on_minutes,
                min_off_minutes=min_off_minutes
            )
        else:
            disagg_power, baseline_curve, timeline, machine_stats = self.disaggregate_load(
                df_work, events_clustered, cluster_info,
                pairing_method=pairing_method,
                min_on_minutes=min_on_minutes,
                min_off_minutes=min_off_minutes
            )

        duration_prior = dict(getattr(self, '_duration_prior_report', {}) or {})

        # MEJORA #8: informe del pareo ON/OFF (asignacion optima vs secuencial).
        pairing = dict(getattr(self, '_pairing_report', {}) or {})
        if pairing:
            _mach_h = int(pairing.get('machines_hungarian', 0))
            _n_mach = len(cluster_info)
            pairing['method'] = ('hungarian' if _mach_h and _mach_h == _n_mach
                                 else 'mixed' if _mach_h else 'sequential')
            pairing['machines_total'] = _n_mach
            _cs = float(pairing.get('cost_sequential', 0.0))
            pairing['improved_pct'] = (round((_cs - float(pairing.get('cost', 0.0)))
                                             / _cs * 100.0, 2)
                                       if _cs > 1e-12 else 0.0)

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
                "delta_h3": round(float(r['delta_H3']), 3) if 'delta_H3' in r else 0.0,
                "delta_h5": round(float(r['delta_H5']), 3) if 'delta_H5' in r else 0.0,
                "delta_h7": round(float(r['delta_H7']), 3) if 'delta_H7' in r else 0.0,
                "harm_ratio_pct": round(float(r['harm_ratio_pct']), 1) if 'harm_ratio_pct' in r else 0.0,
                "cluster": int(r['cluster']),
                "machine_name": r['machine_name'],
                "color": r['color']
            })

        total_energy_kwh = round(float(df_work['P_total'].sum() * (10.0 / 3600.0)), 2)

        # PASO 3: validacion de la desagregacion (error de reconstruccion +
        # matriz de confusion ON/OFF por equipo y global).
        validation = self._validate_disaggregation(
            df_work, events_clustered, cluster_info, disagg_power, baseline_curve
        )

        # PASO 1: firma armonica transitoria agregada por equipo (ΔH3/ΔH5/ΔH7 y
        # ratio ΔH/ΔI). Alimenta las barras agrupadas y el scatter ΔH5 vs ΔP.
        harmonic_signatures = [
            {
                "id": int(c),
                "name": cluster_info[c]['name'],
                "color": cluster_info[c]['color'],
                "avg_delta_h3": float(cluster_info[c].get('avg_delta_h3', 0.0)),
                "avg_delta_h5": float(cluster_info[c].get('avg_delta_h5', 0.0)),
                "avg_delta_h7": float(cluster_info[c].get('avg_delta_h7', 0.0)),
                "harm_ratio_pct": float(cluster_info[c].get('harm_ratio_pct', 0.0)),
                "avg_thd": float(cluster_info[c].get('avg_thd', 0.0)),
                "avg_delta_p": float(cluster_info[c].get('avg_delta_p', 0.0)),
                "avg_cosphi": round(float(cluster_info[c].get('avg_cosphi', 0.0)), 3),
                "avg_inrush": round(float(cluster_info[c].get('avg_inrush', 1.0)), 2),
                "phase_type": str(cluster_info[c].get('phase_type', '')),
                "load_class": str(cluster_info[c].get('load_class', '')),
                "count": int(cluster_info[c].get('count', 0))
            }
            for c in sorted(cluster_info.keys())
        ]

        # MEJORA #13: informe de fugas / standby a partir del residuo
        # (baseline tras desagregar). Sin dependencias nuevas.
        p_full = df_work['P_total'].to_numpy(dtype=float) \
            if 'P_total' in df_work.columns else np.zeros(n)
        standby = self._standby_report(df_work, p_full, baseline_curve)

        # MEJORA #14: anomalias sobre el residuo — reutiliza el mismo
        # baseline que la #13 (MAE movil + umbral MAD robusto).
        residual_anomalies = self._residual_anomalies(
            df_work, p_full, baseline_curve)

        # MEJORA #16: coste economico por equipo con tarifa horaria
        # (periodos 2.0TD + turnos). Se enriquece cada machine_stat con
        # su coste para que la tabla/ficha no tenga que recalcularlo.
        cost_report = self._cost_report(df_work, disagg_power,
                                        baseline_curve, cluster_info)
        if cost_report:
            cost_by_id = {m['id']: m for m in cost_report.get('machines', [])}
            for stat in machine_stats:
                mc = cost_by_id.get(stat.get('id'))
                if mc:
                    stat['cost_eur'] = mc['cost_eur']
                    stat['cost_month_eur'] = mc['cost_month_eur']

        return {
            "dataset_id": dataset_id,
            "algorithm": algorithm,
            "total_energy_kwh": total_energy_kwh,
            "nilmtk_available": self.nilmtk_available,
            "nilmtk_power_states_kw": [round(state, 2) for state in nilmtk_states],
            "n_clusters": n_clusters,
            "k_selection": k_selection,
            "model_reuse": model_reuse,
            "total_events_detected": len(events_clustered),
            "warning": warning,
            "timestamps": timestamps_sampled,
            "p_total": p_total_sampled,
            "baseline": baseline_sampled,
            "disaggregated_machines": disagg_series,
            "machine_statistics": machine_stats,
            "timeline_intervals": timeline[:300],
            "hourly_activity": hourly_distribution,
            "scatter_events": events_data,
            "harmonic_signatures": harmonic_signatures,
            "hmmlearn_available": hmmlearn_available,
            "fhmm_exact": fhmm_exact,
            "validation": validation,
            "standby": standby,
            "residual_anomalies": residual_anomalies,
            "cost": cost_report,
            "pairing": pairing,
            "duration_prior": duration_prior,
            "change_points": change_points,
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
