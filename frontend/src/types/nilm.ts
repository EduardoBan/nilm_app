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
  cluster: number;
  machine_name: string;
  color: string;
}

export interface HourlyActivity {
  hour: string;
  total: number;
  [key: string]: string | number;
}

export interface NILMAnalysisResult {
  dataset_id: string;
  algorithm: string;
  n_clusters: number;
  total_events_detected: number;
  timestamps: string[];
  p_total: number[];
  baseline: number[];
  disaggregated_machines: DisaggregatedSeries[];
  machine_statistics: MachineStat[];
  timeline_intervals: TimelineInterval[];
  hourly_activity: HourlyActivity[];
  scatter_events: ScatterEvent[];
}

export interface AnalysisParams {
  dataset_id: string;
  n_clusters: number;
  algorithm: 'kmeans' | 'gmm' | 'dbscan';
  current_threshold: number;
  power_threshold: number;
}

export type ActiveTab = 'overview' | 'machines' | 'timeline' | 'features3d' | 'features2d' | 'hourly' | 'quality';
