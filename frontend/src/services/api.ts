/**
 * API Service Client for NILM Python Server
 */
import { 
  DatasetInfo, 
  SummaryStats, 
  TimeseriesData, 
  HarmonicsData, 
  NILMAnalysisResult, 
  AnalysisParams 
} from '../types/nilm';

export class NILMApiService {
  private baseUrl: string;

  constructor(baseUrl: string = '') {
    this.baseUrl = baseUrl || window.location.origin;
  }

  async getDatasets(): Promise<DatasetInfo[]> {
    const res = await fetch(`${this.baseUrl}/api/datasets`);
    if (!res.ok) throw new Error(`Error fetching datasets: ${res.statusText}`);
    const json = await res.json();
    return json.data;
  }

  async getSummary(datasetId: string): Promise<SummaryStats> {
    const res = await fetch(`${this.baseUrl}/api/summary?dataset_id=${encodeURIComponent(datasetId)}`);
    if (!res.ok) throw new Error(`Error fetching summary: ${res.statusText}`);
    const json = await res.json();
    return json.data;
  }

  async getTimeseries(datasetId: string, maxPoints: number = 1200): Promise<TimeseriesData> {
    const res = await fetch(`${this.baseUrl}/api/timeseries?dataset_id=${encodeURIComponent(datasetId)}&max_points=${maxPoints}`);
    if (!res.ok) throw new Error(`Error fetching timeseries: ${res.statusText}`);
    const json = await res.json();
    return json.data;
  }

  async getHarmonics(datasetId: string): Promise<HarmonicsData> {
    const res = await fetch(`${this.baseUrl}/api/harmonics?dataset_id=${encodeURIComponent(datasetId)}`);
    if (!res.ok) throw new Error(`Error fetching harmonics: ${res.statusText}`);
    const json = await res.json();
    return json.data;
  }

  async uploadDataset(file: File): Promise<DatasetInfo> {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${this.baseUrl}/api/upload`, {
      method: 'POST',
      body: form
    });
    if (!res.ok) throw new Error(`Error subiendo dataset: ${res.statusText}`);
    const json = await res.json();
    if (json.status !== 'success') throw new Error(json.message || 'Error subiendo dataset');
    return json.data;
  }

  async runAnalysis(params: AnalysisParams): Promise<NILMAnalysisResult> {
    const res = await fetch(`${this.baseUrl}/api/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params)
    });
    if (!res.ok) throw new Error(`Error running NILM analysis: ${res.statusText}`);
    const json = await res.json();
    return json.data;
  }

  /** Manual Ground-Truth labels: {cluster_id: custom_name} for a dataset */
  async getLabels(datasetId: string): Promise<Record<string, string>> {
    const res = await fetch(`${this.baseUrl}/api/labels?dataset_id=${encodeURIComponent(datasetId)}`);
    if (!res.ok) throw new Error(`Error fetching labels: ${res.statusText}`);
    const json = await res.json();
    return json.data.labels || {};
  }

  /** Saves (or clears when name is empty) a custom appliance label */
  async saveLabel(datasetId: string, clusterId: number, name: string): Promise<Record<string, string>> {
    const res = await fetch(`${this.baseUrl}/api/labels`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dataset_id: datasetId, cluster_id: clusterId, name })
    });
    const json = await res.json();
    if (!res.ok || json.status !== 'success') {
      throw new Error(json.message || `Error guardando etiqueta: ${res.statusText}`);
    }
    return json.data.labels || {};
  }

  /** Clears all manual Ground-Truth labels for a dataset */
  async clearLabels(datasetId: string): Promise<Record<string, string>> {
    const res = await fetch(`${this.baseUrl}/api/labels?dataset_id=${encodeURIComponent(datasetId)}`, {
      method: 'DELETE'
    });
    const json = await res.json();
    if (!res.ok || json.status !== 'success') {
      throw new Error(json.message || `Error restableciendo etiquetas: ${res.statusText}`);
    }
    return json.data.labels || {};
  }
}

export const api = new NILMApiService();
