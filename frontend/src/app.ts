/**
 * NILM Industrial Energy Analytics Dashboard Application
 * Main TypeScript Controller
 */

import { api } from './services/api';
import { ChartEngine } from './components/ChartEngine';
import { 
  DatasetInfo, 
  SummaryStats, 
  TimeseriesData, 
  HarmonicsData, 
  NILMAnalysisResult, 
  ActiveTab 
} from './types/nilm';

class NILMApp {
  private currentDatasetId: string = 'coop_gouge_v2_10_abril';
  private datasets: DatasetInfo[] = [];
  private summary: SummaryStats | null = null;
  private timeseries: TimeseriesData | null = null;
  private harmonics: HarmonicsData | null = null;
  private analysis: NILMAnalysisResult | null = null;
  private activeTab: ActiveTab = 'overview';

  private chartCleanups: Array<() => void> = [];

  async init() {
    this.setupTheme();
    this.setupEventListeners();
    await this.loadInitialData();
  }

  private setupTheme() {
    const themeSelect = document.getElementById('theme-select') as HTMLSelectElement;
    const savedTheme = localStorage.getItem('nilm-theme') === 'light' ? 'light' : 'dark';
    document.documentElement.dataset.theme = savedTheme;
    if (themeSelect) themeSelect.value = savedTheme;

    themeSelect?.addEventListener('change', () => {
      const theme = themeSelect.value === 'light' ? 'light' : 'dark';
      document.documentElement.dataset.theme = theme;
      localStorage.setItem('nilm-theme', theme);
      this.renderCurrentTabCharts();
    });
  }

  private setupEventListeners() {
    // Dataset select
    const dsSelect = document.getElementById('dataset-select') as HTMLSelectElement;
    dsSelect?.addEventListener('change', (e) => {
      this.currentDatasetId = (e.target as HTMLSelectElement).value;
      this.refreshData();
    });

    // Run Analysis Button
    const btnRun = document.getElementById('btn-run-analysis');
    btnRun?.addEventListener('click', () => {
      this.runNILMAnalysis();
    });

    // Sliders
    const clusterSlider = document.getElementById('slider-clusters') as HTMLInputElement;
    const clusterVal = document.getElementById('val-clusters');
    clusterSlider?.addEventListener('input', () => {
      if (clusterVal) clusterVal.textContent = clusterSlider.value;
    });

    const thresholdSlider = document.getElementById('slider-threshold') as HTMLInputElement;
    const thresholdVal = document.getElementById('val-threshold');
    thresholdSlider?.addEventListener('input', () => {
      if (thresholdVal) thresholdVal.textContent = `${thresholdSlider.value} A`;
    });

    // Tabs
    const tabButtons = document.querySelectorAll('.nav-tab');
    tabButtons.forEach(btn => {
      btn.addEventListener('click', (e) => {
        const target = (e.currentTarget as HTMLElement).dataset.tab as ActiveTab;
        this.switchTab(target);
      });
    });

    // Window resize handler
    window.addEventListener('resize', () => {
      this.renderCurrentTabCharts();
    });
  }

  private switchTab(tab: ActiveTab) {
    this.activeTab = tab;
    document.querySelectorAll('.nav-tab').forEach(b => {
      if ((b as HTMLElement).dataset.tab === tab) b.classList.add('active');
      else b.classList.remove('active');
    });

    document.querySelectorAll('.tab-content').forEach(c => {
      if (c.id === `tab-${tab}`) c.classList.add('active');
      else c.classList.remove('active');
    });

    this.renderCurrentTabCharts();

    if (tab === 'features3d') {
      requestAnimationFrame(() => {
        const section = document.getElementById('tab-features3d');
        if (section) {
          window.scrollTo({
            top: Math.max(0, section.getBoundingClientRect().top + window.scrollY - 76),
            behavior: 'smooth'
          });
        }
      });
    }
  }

  private async loadInitialData() {
    this.showLoading(true);
    try {
      this.datasets = await api.getDatasets();
      this.populateDatasetSelector();

      if (this.datasets.length > 0) {
        this.currentDatasetId = this.datasets[0].id;
      }

      await this.refreshData();
    } catch (err: any) {
      console.error(err);
      this.showToast(`Error al cargar datos iniciales: ${err.message}`, 'error');
    } finally {
      this.showLoading(false);
    }
  }

  private populateDatasetSelector() {
    const dsSelect = document.getElementById('dataset-select') as HTMLSelectElement;
    if (!dsSelect) return;
    dsSelect.innerHTML = '';

    this.datasets.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.id;
      opt.textContent = `${d.label} (${d.filename})`;
      if (d.id === this.currentDatasetId) opt.selected = true;
      dsSelect.appendChild(opt);
    });
  }

  private async refreshData() {
    this.showLoading(true);
    try {
      // Parallel loading of Summary, Timeseries, Harmonics
      const [sum, ts, harm] = await Promise.all([
        api.getSummary(this.currentDatasetId),
        api.getTimeseries(this.currentDatasetId, 1200),
        api.getHarmonics(this.currentDatasetId)
      ]);

      this.summary = sum;
      this.timeseries = ts;
      this.harmonics = harm;

      this.updateKPIs();
      await this.runNILMAnalysis();
    } catch (err: any) {
      console.error(err);
      this.showToast(`Error cargando dataset: ${err.message}`, 'error');
    } finally {
      this.showLoading(false);
    }
  }

  private async runNILMAnalysis() {
    const clusterSlider = document.getElementById('slider-clusters') as HTMLInputElement;
    const thresholdSlider = document.getElementById('slider-threshold') as HTMLInputElement;
    const algoSelect = document.getElementById('select-algo') as HTMLSelectElement;

    const n_clusters = clusterSlider ? parseInt(clusterSlider.value, 10) : 4;
    const current_threshold = thresholdSlider ? parseFloat(thresholdSlider.value) : 2.0;
    const algorithm = (algoSelect ? algoSelect.value : 'kmeans') as any;

    this.showLoading(true);
    try {
      this.analysis = await api.runAnalysis({
        dataset_id: this.currentDatasetId,
        n_clusters,
        algorithm,
        current_threshold,
        power_threshold: 1.0
      });

      this.updateApplianceTable();
      this.renderCurrentTabCharts();
      this.showToast(`Análisis NILM completado (${this.analysis.total_events_detected} eventos clasificados)`, 'success');
    } catch (err: any) {
      console.error(err);
      this.showToast(`Error ejecutando análisis NILM: ${err.message}`, 'error');
    } finally {
      this.showLoading(false);
    }
  }

  private updateKPIs() {
    if (!this.summary) return;

    const elEnergy = document.getElementById('kpi-energy');
    const elPeak = document.getElementById('kpi-peak');
    const elAvgP = document.getElementById('kpi-avg-p');
    const elPF = document.getElementById('kpi-pf');
    const elSamples = document.getElementById('kpi-samples');
    const elDuration = document.getElementById('kpi-duration');

    if (elEnergy) elEnergy.textContent = `${this.summary.total_energy_kwh.toFixed(1)} kWh`;
    if (elPeak) elPeak.textContent = `${this.summary.peak_power_kw.toFixed(1)} kW`;
    if (elAvgP) elAvgP.textContent = `${this.summary.avg_power_kw.toFixed(1)} kW`;
    if (elPF) elPF.textContent = `${this.summary.avg_power_factor.toFixed(3)}`;
    if (elSamples) elSamples.textContent = `${this.summary.samples.toLocaleString()}`;
    if (elDuration) elDuration.textContent = `${this.summary.duration_hours.toFixed(1)} hs`;
  }

  private updateApplianceTable() {
    if (!this.analysis) return;

    const tbody = document.getElementById('appliances-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    this.analysis.machine_statistics.forEach(m => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><span class="badge-color" style="background:${m.color}"></span> <strong>${m.name}</strong></td>
        <td><span class="badge-cat">${m.category}</span></td>
        <td><strong>${m.nominal_power_kw.toFixed(1)} kW</strong></td>
        <td>${m.peak_current_a.toFixed(1)} A</td>
        <td>${m.thd_pct.toFixed(1)} %</td>
        <td>${m.event_count} arranques</td>
        <td>${m.active_minutes.toFixed(0)} min</td>
        <td><strong>${m.energy_kwh.toFixed(2)} kWh</strong></td>
        <td>
          <div class="progress-bar-wrap">
            <div class="progress-bar-fill" style="width:${Math.min(100, m.energy_share_pct)}%; background:${m.color}"></div>
            <span class="progress-text">${m.energy_share_pct.toFixed(1)}%</span>
          </div>
        </td>
        <td><span class="badge-status status-active">${m.status}</span></td>
      `;
      tbody.appendChild(tr);
    });

    const kpiMachines = document.getElementById('kpi-machines');
    if (kpiMachines) kpiMachines.textContent = `${this.analysis.machine_statistics.length} Cargas`;

    const kpiEvents = document.getElementById('kpi-events');
    if (kpiEvents) kpiEvents.textContent = `${this.analysis.total_events_detected}`;
  }

  private clearChartCleanups() {
    this.chartCleanups.forEach(fn => fn());
    this.chartCleanups = [];
  }

  private renderCurrentTabCharts() {
    this.clearChartCleanups();

    if (this.activeTab === 'overview') {
      this.renderOverviewCharts();
    } else if (this.activeTab === 'machines') {
      this.renderMachinesTab();
    } else if (this.activeTab === 'timeline') {
      this.renderTimelineTab();
    } else if (this.activeTab === 'features3d') {
      this.renderFeatures3DTab();
    } else if (this.activeTab === 'features2d') {
      this.renderFeatures2DTab();
    } else if (this.activeTab === 'hourly') {
      this.renderHourlyTab();
    } else if (this.activeTab === 'quality') {
      this.renderQualityTab();
    }
  }

  private renderOverviewCharts() {
    if (!this.analysis || !this.timeseries) return;

    // 1. Total & Disaggregated Curves Chart
    const canvasMain = document.getElementById('chart-main-power') as HTMLCanvasElement;
    if (canvasMain) {
      const seriesList = [
        { name: 'Potencia Total Medida', data: this.analysis.p_total, color: '#00B5E2', fill: true },
        { name: 'Carga Base / Standby', data: this.analysis.baseline, color: '#A0A0A0', dash: [4, 4] }
      ];

      this.analysis.disaggregated_machines.forEach(m => {
        seriesList.push({
          name: m.name,
          data: m.data,
          color: m.color
        });
      });

      const res = ChartEngine.renderTimeSeries(
        canvasMain,
        this.analysis.timestamps,
        seriesList,
        'kW',
        'Curva de Potencia Total y Desagregación por Equipo (NILM)'
      );
      this.chartCleanups.push(res.destroy);
    }

    // 2. Donut Energy Share
    const canvasDonut = document.getElementById('chart-energy-donut') as HTMLCanvasElement;
    if (canvasDonut) {
      const slices = this.analysis.machine_statistics.map(m => ({
        name: m.name,
        value: m.energy_kwh,
        color: m.color
      }));
      ChartEngine.renderDonut(canvasDonut, slices);
    }
  }

  private renderMachinesTab() {
    if (!this.analysis) return;
    const container = document.getElementById('machines-cards-container');
    if (!container) return;
    container.innerHTML = '';

    this.analysis.machine_statistics.forEach(m => {
      const card = document.createElement('div');
      card.className = 'machine-card';
      card.style.borderLeft = `5px solid ${m.color}`;
      card.innerHTML = `
        <div class="mc-header">
          <div>
            <h3 style="color:${m.color}">${m.name}</h3>
            <span class="mc-category">${m.category}</span>
          </div>
          <span class="mc-status badge-status status-active">${m.status}</span>
        </div>
        <div class="mc-grid">
          <div class="mc-stat">
            <span class="mc-stat-label">Potencia Nominal</span>
            <span class="mc-stat-val">${m.nominal_power_kw.toFixed(1)} kW</span>
          </div>
          <div class="mc-stat">
            <span class="mc-stat-label">Salto de Corriente</span>
            <span class="mc-stat-val">${m.peak_current_a.toFixed(1)} A</span>
          </div>
          <div class="mc-stat">
            <span class="mc-stat-label">Distorsión THD</span>
            <span class="mc-stat-val">${m.thd_pct.toFixed(1)} %</span>
          </div>
          <div class="mc-stat">
            <span class="mc-stat-label">Total Arranques</span>
            <span class="mc-stat-val">${m.event_count}</span>
          </div>
          <div class="mc-stat">
            <span class="mc-stat-label">Tiempo de Operación</span>
            <span class="mc-stat-val">${m.active_minutes.toFixed(0)} min</span>
          </div>
          <div class="mc-stat">
            <span class="mc-stat-label">Consumo Total</span>
            <span class="mc-stat-val">${m.energy_kwh.toFixed(2)} kWh (${m.energy_share_pct.toFixed(1)}%)</span>
          </div>
        </div>
      `;
      container.appendChild(card);
    });
  }

  private renderTimelineTab() {
    if (!this.analysis) return;
    const container = document.getElementById('gantt-container');
    if (!container) return;

    const machines = this.analysis.machine_statistics.map(m => ({
      id: m.id,
      name: m.name,
      color: m.color
    }));

    ChartEngine.renderGanttTimeline(container, machines, this.analysis.timeline_intervals);
  }

  private renderFeatures3DTab() {
    if (!this.analysis) return;

    const canvas3D = document.getElementById('chart-activity-3d') as HTMLCanvasElement;
    if (canvas3D) {
      const events3D = this.analysis.scatter_events.map(e => ({
        x: e.current,
        y: e.voltage,
        z: e.time_minutes,
        color: e.color,
        label: e.machine_name,
        cluster: e.cluster,
        time: e.timestamp
      }));
      const res = ChartEngine.renderActivity3D(
        canvas3D,
        events3D,
        'Corriente [A]',
        'Tensión [V]',
        'Tiempo [min]'
      );
      this.chartCleanups.push(res.destroy);

      document.querySelectorAll<HTMLButtonElement>('[data-3d-view]').forEach(button => {
        const onViewClick = () => {
          document.querySelectorAll('[data-3d-view]').forEach(item => item.classList.remove('active'));
          button.classList.add('active');
          res.setView(button.dataset['3dView'] as 'xy' | 'yz' | 'zx');
        };
        button.addEventListener('click', onViewClick);
        this.chartCleanups.push(() => button.removeEventListener('click', onViewClick));
      });
    }
  }

  private renderFeatures2DTab() {
    if (!this.analysis) return;

    const canvasP_Q = document.getElementById('chart-scatter-pq') as HTMLCanvasElement;
    if (canvasP_Q) {
      const eventsPQ = this.analysis.scatter_events.map(e => ({
        x: e.delta_p,
        y: e.delta_q,
        color: e.color,
        label: e.machine_name,
        cluster: e.cluster,
        time: e.timestamp
      }));
      const res = ChartEngine.renderScatter(
        canvasP_Q,
        eventsPQ,
        'Salto de Potencia Activa ΔP [kW]',
        'Salto de Potencia Reactiva ΔQ [kvar]'
      );
      this.chartCleanups.push(res.destroy);
    }

    const canvasI_THD = document.getElementById('chart-scatter-ithd') as HTMLCanvasElement;
    if (canvasI_THD) {
      const eventsITHD = this.analysis.scatter_events.map(e => ({
        x: e.delta_i,
        y: e.thd,
        color: e.color,
        label: e.machine_name,
        cluster: e.cluster,
        time: e.timestamp
      }));
      const res = ChartEngine.renderScatter(
        canvasI_THD,
        eventsITHD,
        'Salto de Corriente ΔI [A]',
        'Distorsión Armónica THD Corriente [%]'
      );
      this.chartCleanups.push(res.destroy);
    }
  }

  private renderHourlyTab() {
    if (!this.analysis) return;
    const canvas = document.getElementById('chart-hourly-activity') as HTMLCanvasElement;
    if (!canvas) return;

    const labels = this.analysis.hourly_activity.map(h => h.hour);
    const data = this.analysis.hourly_activity.map(h => Number(h.total));

    ChartEngine.renderBarChart(
      canvas,
      labels,
      data,
      '#FCB04C',
      'arr.',
      'Frecuencia de Arranques de Equipos por Hora del Día (00:00 - 23:00)'
    );
  }

  private renderQualityTab() {
    if (!this.timeseries || !this.harmonics) return;

    // 1. 3-Phase Currents
    const canvasCurrent = document.getElementById('chart-phase-currents') as HTMLCanvasElement;
    if (canvasCurrent) {
      const res = ChartEngine.renderTimeSeries(
        canvasCurrent,
        this.timeseries.timestamps,
        [
          { name: 'Fase L1', data: this.timeseries.i_l1, color: '#FF6C75' },
          { name: 'Fase L2', data: this.timeseries.i_l2, color: '#44D2C8' },
          { name: 'Fase L3', data: this.timeseries.i_l3, color: '#3B82F6' },
          { name: 'Corriente Total', data: this.timeseries.i_total, color: '#FFFFFF', dash: [3, 3] }
        ],
        'A',
        'Corrientes de Línea Trifásicas (L1, L2, L3) [A]'
      );
      this.chartCleanups.push(res.destroy);
    }

    // 2. 3-Phase Voltages
    const canvasVoltage = document.getElementById('chart-phase-voltages') as HTMLCanvasElement;
    if (canvasVoltage) {
      const res = ChartEngine.renderTimeSeries(
        canvasVoltage,
        this.timeseries.timestamps,
        [
          { name: 'Tensión U L1', data: this.timeseries.v_l1, color: '#FF6C75' },
          { name: 'Tensión U L2', data: this.timeseries.v_l2, color: '#44D2C8' },
          { name: 'Tensión U L3', data: this.timeseries.v_l3, color: '#3B82F6' }
        ],
        'V',
        'Tensiones de Fase (U L1, L2, L3) [V]'
      );
      this.chartCleanups.push(res.destroy);
    }

    // 3. Current Harmonics Spectrum
    const canvasHarmonics = document.getElementById('chart-harmonics-spectrum') as HTMLCanvasElement;
    if (canvasHarmonics) {
      ChartEngine.renderBarChart(
        canvasHarmonics,
        this.harmonics.harmonic_orders,
        this.harmonics.current_harmonics_a,
        '#5C46F9',
        'A',
        'Espectro de Armónicos de Corriente (Fundamental hasta H25) [A]'
      );
    }
  }

  private showLoading(show: boolean) {
    const loader = document.getElementById('loading-overlay');
    if (loader) {
      if (show) loader.classList.add('visible');
      else loader.classList.remove('visible');
    }
  }

  private showToast(msg: string, type: 'info' | 'success' | 'error' = 'info') {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = msg;
    toast.className = `toast visible ${type}`;
    setTimeout(() => {
      toast.classList.remove('visible');
    }, 4000);
  }
}

// Instantiate on load
window.addEventListener('DOMContentLoaded', () => {
  const app = new NILMApp();
  app.init();
});
