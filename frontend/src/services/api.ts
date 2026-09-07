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
}

export const api = new NILMApiService();
