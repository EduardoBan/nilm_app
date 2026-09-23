/**
 * TypeScript definitions for NILM (Non-Intrusive Load Monitoring) Client
 */

export interface DatasetInfo {
  id: string;
  filename: string;
  label: string;
  cached: boolean;
  size_mb: number;
}

export interface SummaryStats {
  dataset_id: string;
  start_time: string;
  end_time: string;
  duration_hours: number;
  samples: number;
  total_energy_kwh: number;
  peak_power_kw: number;
  min_power_kw: number;
  avg_power_kw: number;
  avg_power_factor: number;
  max_current_a: number;
}

export interface TimeseriesData {
  timestamps: string[];
  timestamps_full: string[];
  p_total: number[];
  p_l1: number[];
  p_l2: number[];
  p_l3: number[];
  pf_total: number[];
  i_l1: number[];
  i_l2: number[];
  i_l3: number[];
  i_total: number[];
  v_l1: number[];
  v_l2: number[];
  v_l3: number[];
  thd_i_l1: number[];
  thd_i_l2: number[];
  thd_i_l3: number[];
}

export interface HarmonicsData {
  harmonic_orders: string[];
  voltage_harmonics_v: number[];
  current_harmonics_a: number[];
}

export interface MachineStat {
  id: number;
  name: string;
  category: string;
  color: string;
  nominal_power_kw: number;
  peak_current_a: number;
  thd_pct: number;
  event_count: number;
  active_minutes: number;
  energy_kwh: number;
  energy_share_pct: number;
  status: 'Activo' | 'Inactivo';
  /* Opción A: clasificación por armónicos transitorios */
  load_class?: string;
  load_icon?: string;
  load_family?: 'no_lineal' | 'inductiva' | 'resistiva' | string;
  harmonic_signature_pct?: number;
  q_p_ratio?: number;
  /* Opción A: Ground-Truth manual */
  custom_label?: boolean;
  /* Opción A: modelado multi-estado FHMM */
  n_states?: number;
  states?: MachineStateInfo[];
  /* PASO 1: firma armónica transitoria (fallback si falta harmonic_signatures) */
  avg_delta_h3?: number;
  avg_delta_h5?: number;
  avg_delta_h7?: number;
  harm_ratio_pct?: number;
  /* MEJORA #20: firmas extendidas (inrush / cos φ / balance de fases) */
  avg_cosphi?: number;
  avg_inrush?: number;
  phase_type?: string;
  /* MEJORA #16: coste economico (tarifa horaria) */
  cost_eur?: number;
  cost_month_eur?: number;
  /* MEJORA #15: calidad de energia por equipo (kVA/distorsion/desbalance) */
  avg_delta_s?: number;
  dist_kva?: number;
  dist_ratio?: number;
  phase_imbalance?: number;
}

export interface MachineStateInfo {
  level: number;
  name: string;
  kw: number;
  minutes: number;
  energy_kwh: number;
  share_pct: number;
}

export interface MultiStateModel {
  levels_kw: number[];
  n_states: number;
  states: MachineStateInfo[];
}

export interface TimelineInterval {
  machine_id: number;
  machine_name: string;
  category: string;
  color: string;
  start_time: string;
  end_time: string;
  start_timestamp: string;
  end_timestamp: string;
  duration_minutes: number;
  avg_power_kw: number;
  energy_kwh: number;
  /* Opción A: estado FHMM del intervalo */
  state_level?: number;
  state_name?: string;
  state?: string;
}

export interface DisaggregatedSeries {
  id: number;
  name: string;
  color: string;
  data: number[];
}

export interface ScatterEvent {
  timestamp: string;
  time_minutes: number;
  current: number;
  voltage: number;
  delta_p: number;
  delta_q: number;
  delta_i: number;
  thd: number;
  delta_h3?: number;
  delta_h5?: number;
  delta_h7?: number;
  harm_ratio_pct?: number;
  cluster: number;
  machine_name: string;
  color: string;
}

export interface HarmonicSignature {
  id: number;
  name: string;
  color: string;
  avg_delta_h3: number;
  avg_delta_h5: number;
  avg_delta_h7: number;
  harm_ratio_pct: number;
  avg_thd: number;
  avg_delta_p: number;
  /* MEJORA #20: firmas extendidas (inrush / cos φ / balance de fases) */
  avg_cosphi?: number;
  avg_inrush?: number;
  phase_type?: string;
  load_class?: string;
  count: number;
}

export interface FhmmExactInfo {
  method: string;
  logprob: number | null;
  n_comb_states: number;
  dims: number[];
  n_points_decoded: number;
  n_points_full: number;
  downsample_step: number;
  combined_seq_ds: number[];
  state_means_kw?: number[];
  /* MEJORA #1: emisión bivariada [P, Q] */
  features?: string[];
  state_means_q_kw?: number[];
  /* MEJORA #2: priors horarios en la transición OFF→ON */
  priors_used?: boolean;
  hourly_priors?: Record<string, number[]>;
  on_minutes_total_before?: number[];
  on_minutes_total_after?: number[];
  night_minutes_reduced?: number;
  logprob_no_priors?: number | null;
  logprob_priors?: number | null;
}

export interface HourlyActivity {
  hour: string;
  total: number;
  [key: string]: string | number;
}

/* PASO 3: validación de la desagregación */
export interface ReconstructionError {
  mae_kw: number;
  rmse_kw: number;
  mape_pct: number;
  energy_explained_pct: number;
  /* Métricas estándar NILMTK (regresión/energía) */
  re_pct?: number;
  nep?: number;
}

export interface ConfusionCounts {
  tp: number;
  fp: number;
  fn: number;
  tn: number;
}

/* MEJORA #13: fugas / standby a partir del residuo (baseline) */
export interface StandbyReport {
  samples: number;
  hours_covered: number;
  baseline_kw: { p5: number; p10: number; p25: number; p50: number; mean: number; max: number };
  night_kw: { p10: number; p50: number; mean: number; samples: number; window: string };
  share_pct: number;
  energy_kwh: number;
  annual_kwh: number;
  duration_pct: number[];
  duration_baseline_kw: number[];
  duration_total_kw: number[];
  hist: { counts: number[]; edges: number[] };
  method: string;
}

/* MEJORA #14: anomalias sobre el residuo (MAE movil + umbral MAD) */
export interface ResidualAnomalyEvent {
  start_pct: number;
  end_pct: number;
  start_iso: string;
  end_iso: string;
  duration_min: number;
  peak_mae_kw: number;
}

export interface ResidualAnomalyReport {
  samples: number;
  window_samples: number;
  window_minutes: number;
  min_run_samples: number;
  center_kw: number;
  threshold_kw: number;
  mae_kw: { p50: number; p95: number; max: number };
  n_events: number;
  anomalous_pct: number;
  max_mae_kw: number;
  labels_pct: number[];
  mae_series: number[];
  threshold_series: number[];
  events: ResidualAnomalyEvent[];
  method: string;
}

export interface ConfusionGlobal extends ConfusionCounts {
  precision: number;
  recall: number;
  f1: number;
  accuracy?: number;
}

/* MEJORA #11: métrica de transiciones (arranques detectados vs reales) */
export interface TransitionMetrics {
  tp: number;
  fp: number;
  fn: number;
  detected: number;
  reference: number;
  precision: number;
  recall: number;
  f1: number;
  dt_median_s: number;
  dt_max_s: number;
  tolerance_s?: number;
}

export interface MachineValidation {
  id: number;
  name: string;
  color: string;
  n_on_events: number;
  jump_mae_kw: number;
  confusion: ConfusionCounts;
  precision: number;
  recall: number;
  f1: number;
  accuracy?: number;
  /* Métricas de regresión (energía) estándar NILMTK */
  reg_mae_kw?: number;
  reg_rmse_kw?: number;
  re_pct?: number;
  nep?: number;
  /* MEJORA #11: métrica de transiciones (arranques) por equipo */
  transitions?: TransitionMetrics;
}

export interface ValidationReport {
  reconstruction: ReconstructionError;
  confusion_global: ConfusionGlobal;
  machines: MachineValidation[];
  /* MEJORA #11: agregado global de transiciones */
  transitions_global?: TransitionMetrics;
}

export interface NILMAnalysisResult {
  dataset_id: string;
  algorithm: string;
  total_energy_kwh?: number;
  n_clusters: number;
  total_events_detected: number;
  warning?: string;
  timestamps: string[];
  p_total: number[];
  baseline: number[];
  disaggregated_machines: DisaggregatedSeries[];
  machine_statistics: MachineStat[];
  timeline_intervals: TimelineInterval[];
  hourly_activity: HourlyActivity[];
  scatter_events: ScatterEvent[];
  /* PASO 1: firma armónica transitoria agregada por equipo */
  harmonic_signatures?: HarmonicSignature[];
  /* PASO 2: FHMM exacto (Viterbi) y disponibilidad de hmmlearn */
  hmmlearn_available?: boolean;
  fhmm_exact?: FhmmExactInfo | null;
  /* PASO 3: validación de la desagregación */
  validation?: ValidationReport | null;
  /* MEJORA #13: fugas / standby a partir del residuo (baseline) */
  standby?: StandbyReport | null;
  /* MEJORA #14: anomalias sobre el residuo (MAE movil + umbral MAD) */
  residual_anomalies?: ResidualAnomalyReport | null;
  /* MEJORA #16: coste economico por equipo (tarifa horaria) */
  cost?: CostReport | null;
  /* Opción A: modelado multi-estado FHMM */
  fhmm_enabled?: boolean;
  max_states?: number;
  multi_state_models?: Record<string, MultiStateModel>;
}

export interface AnalysisParams {
  dataset_id: string;
  n_clusters: number;
  algorithm: 'kmeans' | 'gmm' | 'dbscan';
  current_threshold: number;
  power_threshold: number;
  /* Opción A: modelado multi-estado FHMM */
  use_fhmm: boolean;
  max_states: number;
}

/* MEJORA #9/#10: benchmark de algoritmos + estabilidad de umbrales (frontend-only) */
export interface BenchmarkRow {
  config: string;
  kind: 'algoritmo' | 'estabilidad';
  algorithm: string;
  current_threshold: number;
  power_threshold: number;
  use_fhmm: boolean;
  n_clusters: number;
  mae_kw: number;
  rmse_kw: number;
  re_pct: number;
  f1: number;
  accuracy: number;
  total_events: number;
  elapsed_s: number;
  ok: boolean;
  error?: string;
}

export interface BenchmarkResult {
  rows: BenchmarkRow[];
  f1_mean_stab: number;
  f1_std_stab: number;
  re_mean_stab: number;
  re_std_stab: number;
  best: BenchmarkRow | null;
}

/* MEJORA #16: coste economico por equipo (tarifa horaria por periodos + turnos) */
export interface CostPeriod {
  period: string;
  hours: number;
  energy_kwh: number;
  cost_eur: number;
}

export interface CostShift {
  shift: string;
  hours: number;
  energy_kwh: number;
  cost_eur: number;
}

export interface CostMachine {
  id: number;
  name: string;
  color: string;
  energy_kwh: number;
  cost_eur: number;
  cost_month_eur: number;
  cost_share_pct: number;
}

export interface CostReport {
  tariff: { name: string; currency: string; rates_eur_kwh: Record<string, number> };
  hours_covered: number;
  periods: CostPeriod[];
  shifts: CostShift[];
  machines: CostMachine[];
  residual: { energy_kwh: number; cost_eur: number; cost_month_eur: number };
  total: { energy_kwh: number; cost_eur: number; cost_month_eur: number };
  method: string;
}

export type ActiveTab = 'overview' | 'machines' | 'timeline' | 'features3d' | 'features2d' | 'hourly' | 'quality' | 'pq' | 'harmonic' | 'fhmm' | 'validation' | 'benchmark' | 'standby';

/* MEJORA #21: diagnóstico de calidad energética */
export interface PQCheck {
  id: string;
  label: string;
  value: string;
  limit: string;
  status: 'ok' | 'warn' | 'bad';
  note: string;
}

export interface PQEvent {
  start: string;
  end: string;
  duration_min: number;
  extreme_v: number;
  depth_pct: number;
  phase: string | null;
}

export interface PQPhaseStats {
  mean: number;
  min: number;
  max: number;
}

export interface PowerQualityReport {
  vnom: number;
  samples: number;
  voltage: { l1: PQPhaseStats; l2: PQPhaseStats; l3: PQPhaseStats };
  unbalance: { mean: number; max: number; source: string };
  thd_u: { mean: number; max: number };
  thd_i: { mean: number; max: number };
  neutral: { mean_a: number; max_a: number; pct_of_phase: number };
  k_factor: { mean: number; max: number };
  crest: { u: number; i: number };
  frequency: { mean: number; min: number; max: number };
  checks: PQCheck[];
  sags: PQEvent[];
  swells: PQEvent[];
  timeseries: {
    timestamps: string[];
    v_l1: number[];
    v_l2: number[];
    v_l3: number[];
    thd_u: number[];
    i_n: number[];
    u2u1: number[];
    i_l1: number[];
    i_l2: number[];
    i_l3: number[];
  };
}
