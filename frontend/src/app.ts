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
  ActiveTab,
  BenchmarkRow,
  BenchmarkResult,
  PowerQualityReport
} from './types/nilm';

/** Escapa HTML para evitar XSS via nombres Ground-Truth personalizados. */
function escapeHtml(s: string): string {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** Formatea un número opcionalmente NaN/undefined para tablas del benchmark. */
function fmtNum(v: number, digits: number): string {
  return Number.isFinite(v) ? v.toFixed(digits) : '--';
}

class NILMApp {
  private currentDatasetId: string = '';
  private datasets: DatasetInfo[] = [];
  private summary: SummaryStats | null = null;
  private timeseries: TimeseriesData | null = null;
  private harmonics: HarmonicsData | null = null;
  private analysis: NILMAnalysisResult | null = null;
  private activeTab: ActiveTab = 'overview';
  /* Opción A: modelado multi-estado FHMM (persistido entre sesiones) */
  private useFhmm: boolean = (localStorage.getItem('nilm-fhmm') ?? 'on') !== 'off';

  /* MEJORA #9/#10: benchmark de algoritmos + estabilidad de umbrales */
  private benchmark: BenchmarkResult | null = null;

  /* MEJORA #21: diagnóstico de calidad energética */
  private powerQuality: PowerQualityReport | null = null;

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
    // Dataset dropdown selector
    const selectDs = document.getElementById('select-dataset') as HTMLSelectElement;
    selectDs?.addEventListener('change', async () => {
      if (selectDs.value && selectDs.value !== this.currentDatasetId) {
        this.currentDatasetId = selectDs.value;
        const found = this.datasets.find(d => d.id === this.currentDatasetId);
        if (found) this.updateFileLabel(found.filename);
        await this.refreshData();
      }
    });

    // File picker (upload a measurement file)
    const fileInput = document.getElementById('dataset-file') as HTMLInputElement;
    fileInput?.addEventListener('change', () => {
      this.handleFileSelected(fileInput);
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

    // Opción A: Multi-state FHMM modeling toggle
    const fhmmCheck = document.getElementById('chk-fhmm') as HTMLInputElement;
    if (fhmmCheck) {
      fhmmCheck.checked = this.useFhmm;
      fhmmCheck.addEventListener('change', () => {
        this.useFhmm = fhmmCheck.checked;
        localStorage.setItem('nilm-fhmm', this.useFhmm ? 'on' : 'off');
        this.runNILMAnalysis();
      });
    }

    // Reset Ground Truth custom labels (Punto B)
    const btnResetLabels = document.getElementById('btn-reset-labels');
    btnResetLabels?.addEventListener('click', async () => {
      if (!this.currentDatasetId) return;
      if (confirm('¿Deseas restablecer los nombres de las cargas a sus valores automáticos? Se borrarán las etiquetas personalizadas para esta medición.')) {
        try {
          this.showLoading(true);
          await api.clearLabels(this.currentDatasetId);
          this.showToast('Etiquetas personalizadas restablecidas', 'success');
          await this.runNILMAnalysis();
        } catch (err: any) {
          console.error(err);
          this.showToast(`Error al restablecer etiquetas: ${err.message}`, 'error');
        } finally {
          this.showLoading(false);
        }
      }
    });

    // MEJORA #9/#10: benchmark de algoritmos y estabilidad de umbrales
    const btnBenchmark = document.getElementById('btn-run-benchmark');
    btnBenchmark?.addEventListener('click', () => {
      this.runBenchmark();
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

      if (this.datasets.length > 0) {
        // Conserva el dataset guardado si aún existe; si no, usa el primero
        // disponible (antes se forzaba siempre datasets[0] + hardcode).
        const stillThere = this.currentDatasetId
          && this.datasets.some(d => d.id === this.currentDatasetId);
        if (!stillThere) this.currentDatasetId = this.datasets[0].id;
        const found = this.datasets.find(d => d.id === this.currentDatasetId);
        this.updateFileLabel(found ? found.filename : this.datasets[0].filename);
      } else {
        this.currentDatasetId = '';
        this.updateFileLabel(null);
        this.updateDatasetSelect();
        this.showToast('No hay mediciones en la carpeta Data. Sube un .xlsx/.xls/.csv.', 'error');
        return;
      }
      this.updateDatasetSelect();

      await this.refreshData();
    } catch (err: any) {
      console.error(err);
      this.updateFileLabel(null);
      this.showToast(`Error al cargar datos iniciales: ${err.message}`, 'error');
    } finally {
      this.showLoading(false);
    }
  }

  private updateDatasetSelect() {
    const selectDs = document.getElementById('select-dataset') as HTMLSelectElement;
    if (!selectDs) return;
    selectDs.innerHTML = '';
    this.datasets.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.id;
      opt.textContent = d.label || d.filename;
      if (d.id === this.currentDatasetId) opt.selected = true;
      selectDs.appendChild(opt);
    });
  }

  private async handleFileSelected(input: HTMLInputElement) {
    const file = input.files && input.files[0];
    if (!file) return;

    this.updateFileLabel(file.name);
    this.showLoading(true);
    try {
      const ds = await api.uploadDataset(file);
      this.currentDatasetId = ds.id;
      const existingIdx = this.datasets.findIndex(d => d.id === ds.id);
      if (existingIdx >= 0) {
        this.datasets[existingIdx] = ds;
      } else {
        this.datasets.unshift(ds);
      }
      this.updateDatasetSelect();
      this.updateFileLabel(ds.filename);
      await this.refreshData();
    } catch (err: any) {
      console.error(err);
      this.updateFileLabel(null);
      this.showToast(`Error al cargar archivo: ${err.message}`, 'error');
    } finally {
      this.showLoading(false);
      input.value = '';
    }
  }

  private updateFileLabel(name: string | null, uploading: boolean = false) {
    const labelEl = document.getElementById('dataset-file-name');
    if (!labelEl) return;
    if (uploading) {
      labelEl.textContent = 'Procesando archivo…';
    } else if (name) {
      labelEl.textContent = name;
    } else {
      labelEl.textContent = 'Sin archivo seleccionado';
    }
  }

  private async refreshData() {
    this.showLoading(true);
    try {
      // Parallel loading of Summary, Timeseries, Harmonics, Power Quality
      const [sum, ts, harm, pq] = await Promise.all([
        api.getSummary(this.currentDatasetId),
        api.getTimeseries(this.currentDatasetId, 1200),
        api.getHarmonics(this.currentDatasetId),
        api.getPowerQuality(this.currentDatasetId, 600).catch((err) => {
          console.error('Calidad energética no disponible:', err);
          return null;
        })
      ]);

      this.summary = sum;
      this.timeseries = ts;
      this.harmonics = harm;
      this.powerQuality = pq;

      this.updateKPIs();

      // Update PDF report link with current dataset
      const reportLink = document.getElementById('report-link-btn') as HTMLAnchorElement;
      if (reportLink && this.currentDatasetId) {
        reportLink.href = `/api/report?dataset_id=${encodeURIComponent(this.currentDatasetId)}`;
      }

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
        power_threshold: 1.0,
        use_fhmm: this.useFhmm,
        max_states: 3
      });

      this.updateApplianceTable();
      this.renderCurrentTabCharts();
      const mode = this.analysis.fhmm_enabled ? 'FHMM multi-estado' : 'ON/OFF binario';
      const warn = (this.analysis as any).warning;
      if (warn) this.showToast(warn, 'info');
      this.showToast(`Análisis NILM completado (${this.analysis.total_events_detected} eventos · ${this.analysis.timeline_intervals.length} intervalos Gantt · modo ${mode})`, 'success');
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
      const safeName = escapeHtml(m.name);
      const safeCategory = escapeHtml(m.category);
      const safeLoadClass = m.load_class ? escapeHtml(m.load_class) : '';
      const loadBadge = m.load_class
        ? `<span class="load-badge load-${m.load_family || 'inductiva'}'">${m.load_icon || 'x'} ${safeLoadClass}</span>`
        : `<span class="badge-cat">${safeCategory}</span>`;
      
      // Opción A: modelado multi-estado FHMM — chips por cada nivel de estado
      let statesHtml = '';
      if (m.states && m.states.length > 1) {
        statesHtml = `<div class="machine-states">` +
          m.states.filter(s => s.kw > 0).map(s =>
            `<span class="state-chip" style="border-color:${m.color}">
               <span class="state-chip-name">${escapeHtml(s.name)}</span>
               <span class="state-chip-kw">${s.kw.toFixed(2)} kW</span>
               <span class="state-chip-min">${s.minutes.toFixed(0)} min</span>
             </span>`
          ).join('') +
          `</div>`;
      }
      
      tr.innerHTML = `
        <td>
          <span class="badge-color" style="background:${m.color}"></span>
          <strong class="editable-name" data-machine="${m.id}" title="Click en renombrar (Ground Truth)">${safeName}</strong>
          <button class="edit-btn" data-edit="${m.id}" title="Renombrar equipo (Ground Truth)">E</button>
          ${m.custom_label ? ' <span class="gt-flag" title="Etiqueta personalizada guardada">GT</span>' : ''}
          ${(m.states && m.states.length > 1) ? `<span class="state-count-badge" title="Modo multi-estado FHMM"><span class="flag">🧠</span> ${m.states.length} estados</span>` : ''}
          ${statesHtml}
        </td>
        <td>${loadBadge}</td>
        <td><strong>${m.nominal_power_kw.toFixed(1)} kW</strong></td>
        <td>${m.peak_current_a.toFixed(1)} A</td>
        <td>${m.avg_inrush != null ? '×' + m.avg_inrush.toFixed(1) : '--'}</td>
        <td>${m.thd_pct.toFixed(1)} %</td>
        <td>${m.dist_kva != null ? m.dist_kva.toFixed(2) + ' kVA' : '--'}${m.dist_ratio != null ? `<br><small title="Fracción D/S del salto">${(m.dist_ratio * 100).toFixed(0)}% D/S</small>` : ''}</td>
        <td>${m.avg_cosphi != null && m.avg_cosphi > 0 ? m.avg_cosphi.toFixed(3) : '--'}</td>
        <td>${m.phase_type ? escapeHtml(m.phase_type) : '--'}</td>
        <td>${m.phase_imbalance != null ? (m.phase_imbalance * 100).toFixed(0) + ' %' : '--'}</td>
        <td>${m.event_count} arranques</td>
        <td>${m.active_minutes.toFixed(0)} min</td>
        <td><strong>${m.energy_kwh.toFixed(2)} kWh</strong></td>
        <td><strong>${m.cost_eur != null ? m.cost_eur.toFixed(2) + ' €' : '--'}</strong>${m.cost_month_eur != null ? `<br><small title="Proyección mensual">${m.cost_month_eur.toFixed(2)} €/mes</small>` : ''}</td>
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

    // Bind Ground-Truth rename buttons (Opción A - Punto 2)
    tbody.querySelectorAll<HTMLButtonElement>('button.edit-btn').forEach(btn => {
      btn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        const id = parseInt(btn.dataset['edit'] || '0', 10);
        const nameSpan = tbody.querySelector<HTMLElement>(`.editable-name[data-machine="${id}"]`);
        if (nameSpan) this.startRename(id, nameSpan);
      });
    });

    const kpiMachines = document.getElementById('kpi-machines');
    if (kpiMachines) kpiMachines.textContent = `${this.analysis.machine_statistics.length} Cargas`;

    const kpiEvents = document.getElementById('kpi-events');
    if (kpiEvents) kpiEvents.textContent = `${this.analysis.total_events_detected}`;
  }

  /**
   * Opción A - Punto 2: inline Ground-Truth renaming.
   * Replaces the machine name with an input; Enter/blur saves the custom
   * label (persisted server-side), Escape cancels.
   */
  private startRename(machineId: number, host: HTMLElement) {
    if (!this.analysis) return;
    const stat = this.analysis.machine_statistics.find(m => m.id === machineId);
    if (!stat) return;
    const original = stat.name;

    host.innerHTML = '';
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'rename-input';
    input.maxLength = 80;
    input.value = original;
    input.title = 'Enter: guardar · Esc: cancelar';
    host.appendChild(input);
    input.focus();
    input.select();

    let done = false;
    const finish = (commit: boolean) => {
      if (done) return;
      done = true;
      const newName = input.value.trim().slice(0, 80);
      if (!commit || !newName || newName === original) {
        this.updateApplianceTable();
        this.renderMachinesTab();
        this.renderCurrentTabCharts();
        return;
      }
      api.saveLabel(this.currentDatasetId, machineId, newName)
        .then(() => {
          this.applyNameOverride(machineId, newName);
          this.showToast(`Etiqueta guardada: "${newName}" (Ground Truth persistido)`, 'success');
        })
        .catch((err: any) => {
          console.error(err);
          this.showToast(`Error guardando etiqueta: ${err.message}`, 'error');
          this.updateApplianceTable();
          this.renderMachinesTab();
          this.renderCurrentTabCharts();
        });
    };

    input.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') { ev.preventDefault(); finish(true); }
      else if (ev.key === 'Escape') { ev.preventDefault(); finish(false); }
    });
    input.addEventListener('blur', () => finish(true));
  }

  /** Applies a custom name to every structure that references the machine */
  private applyNameOverride(machineId: number, newName: string) {
    if (!this.analysis) return;
    this.analysis.machine_statistics.forEach(m => {
      if (m.id === machineId) { m.name = newName; m.custom_label = true; }
    });
    this.analysis.disaggregated_machines.forEach(d => {
      if (d.id === machineId) d.name = newName;
    });
    this.analysis.timeline_intervals.forEach(t => {
      if (t.machine_id === machineId) t.machine_name = newName;
    });
    this.analysis.scatter_events.forEach(e => {
      if (e.cluster === machineId) e.machine_name = newName;
    });
    this.updateApplianceTable();
    this.renderMachinesTab();
    this.renderCurrentTabCharts();
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
    } else if (this.activeTab === 'pq') {
      this.renderPowerQualityTab();
    } else if (this.activeTab === 'harmonic') {
      this.renderHarmonicTab();
    } else if (this.activeTab === 'fhmm') {
      this.renderFhmmTab();
    } else if (this.activeTab === 'validation') {
      this.renderValidationTab();
    } else if (this.activeTab === 'standby') {
      this.renderStandbyTab();
    } else if (this.activeTab === 'benchmark') {
      this.renderBenchmarkTab();
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
      const machineSlices = this.analysis.machine_statistics.map(m => ({
        name: m.name,
        value: m.energy_kwh,
        color: m.color
      }));
      const machineEnergy = machineSlices.reduce((a, s) => a + s.value, 0);

      // Energia total de la red (campo del backend) o derivada de los shares
      let totalEnergy = (this.analysis as any).total_energy_kwh as number | undefined;
      if (!totalEnergy || totalEnergy < machineEnergy) {
        const ests = this.analysis.machine_statistics
          .filter(m => m.energy_share_pct > 0)
          .map(m => m.energy_kwh * 100 / m.energy_share_pct);
        totalEnergy = ests.length ? ests.reduce((a, b) => a + b, 0) / ests.length : machineEnergy;
      }

      // Sector de carga base (Standby) = consumo no atribuido a ninguna maquina
      const baseline = Math.max(0, totalEnergy - machineEnergy);
      const slices = [...machineSlices];
      if (baseline > totalEnergy * 0.005) {
        slices.push({ name: 'Carga base (Standby)', value: baseline, color: '#64748B' });
      }

      const res = ChartEngine.renderDonut(canvasDonut, slices);
      this.chartCleanups.push(res.destroy);
    }
  }

  private renderMachinesTab() {
    if (!this.analysis) return;
    this.renderCostSummary();
    const container = document.getElementById('machines-cards-container');
    if (!container) return;
    container.innerHTML = '';

    this.analysis.machine_statistics.forEach(m => {
      const card = document.createElement('div');
      card.className = 'machine-card';
      card.style.borderLeft = `5px solid ${m.color}`;
      const safeName = escapeHtml(m.name);
      const safeCategory = escapeHtml(m.category);
      card.innerHTML = `
        <div class="mc-header">
          <div>
            <h3 style="color:${m.color}">
              <span class="editable-name" data-machine="${m.id}" title="Renombrar (Ground Truth)">${safeName}</span>
              <button class="edit-btn" data-edit="${m.id}" title="Renombrar equipo (Ground Truth)">E</button>
              ${m.custom_label ? ' <span class="gt-flag" title="Etiqueta personalizada guardada (Ground Truth)">GT</span>' : ''}
            </h3>
            <span class="mc-category">${safeCategory}</span>
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
            <span class="mc-stat-label">Potencia de distorsión</span>
            <span class="mc-stat-val">${m.dist_kva != null ? m.dist_kva.toFixed(2) + ' kVA' : '--'}${m.dist_ratio != null ? ` (${(m.dist_ratio * 100).toFixed(0)}% D/S)` : ''}</span>
          </div>
          <div class="mc-stat">
            <span class="mc-stat-label">Ratio de Inrush</span>
            <span class="mc-stat-val">${m.avg_inrush != null ? '×' + m.avg_inrush.toFixed(1) : '--'}</span>
          </div>
          <div class="mc-stat">
            <span class="mc-stat-label">cos φ (media)</span>
            <span class="mc-stat-val">${m.avg_cosphi != null && m.avg_cosphi > 0 ? m.avg_cosphi.toFixed(3) : '--'}</span>
          </div>
          <div class="mc-stat">
            <span class="mc-stat-label">Tipo de Fase</span>
            <span class="mc-stat-val">${m.phase_type ? escapeHtml(m.phase_type) : '--'}</span>
          </div>
          <div class="mc-stat">
            <span class="mc-stat-label">Desbalance de fases</span>
            <span class="mc-stat-val">${m.phase_imbalance != null ? (m.phase_imbalance * 100).toFixed(0) + ' %' : '--'}</span>
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
          <div class="mc-stat">
            <span class="mc-stat-label">Coste (tarifa)</span>
            <span class="mc-stat-val">${m.cost_eur != null ? m.cost_eur.toFixed(2) + ' €' : '--'}${m.cost_month_eur != null ? ` (${m.cost_month_eur.toFixed(2)} €/mes)` : ''}</span>
          </div>
        </div>
        ${this.renderMachineStatesBlock(m)}
      `;
      container.appendChild(card);
    });

    // Bind Ground-Truth rename buttons in cards
    container.querySelectorAll<HTMLButtonElement>('button.edit-btn').forEach(btn => {
      btn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        const id = parseInt(btn.dataset['edit'] || '0', 10);
        const nameSpan = container.querySelector<HTMLElement>(`.editable-name[data-machine="${id}"]`);
        if (nameSpan) this.startRename(id, nameSpan);
      });
    });
  }

  /** MEJORA #16: resumen del coste energetico (tarifa, totales, periodos, turnos) */
  private renderCostSummary() {
    const el = document.getElementById('cost-summary');
    if (!el) return;
    const c = this.analysis?.cost;
    if (!c || !c.total) {
      el.style.display = 'none';
      el.innerHTML = '';
      return;
    }
    el.style.display = '';
    const rates = (c.tariff && c.tariff.rates_eur_kwh) || {};
    const rateLbl = ['valle', 'llano', 'punta']
      .filter(k => rates[k] != null)
      .map(k => `${k} ${Number(rates[k]).toFixed(4)}`)
      .join(' · ');
    const periodChips = (c.periods || []).map(p => `
      <div class="mc-stat">
        <span class="mc-stat-label">Periodo ${escapeHtml(p.period)}</span>
        <span class="mc-stat-val">${p.cost_eur.toFixed(2)} € <small>(${p.hours.toFixed(1)} h)</small></span>
      </div>`).join('');
    const shiftChips = (c.shifts || []).map(s => `
      <div class="mc-stat">
        <span class="mc-stat-label">Turno ${escapeHtml(s.shift)}</span>
        <span class="mc-stat-val">${s.cost_eur.toFixed(2)} € <small>(${s.hours.toFixed(1)} h)</small></span>
      </div>`).join('');
    el.innerHTML = `
      <div class="mc-grid">
        <div class="mc-stat">
          <span class="mc-stat-label">💶 Coste total · ${escapeHtml(c.tariff?.name || 'tarifa')}</span>
          <span class="mc-stat-val">${c.total.cost_eur.toFixed(2)} €</span>
        </div>
        <div class="mc-stat">
          <span class="mc-stat-label">Proyección mensual</span>
          <span class="mc-stat-val">${c.total.cost_month_eur.toFixed(2)} €/mes</span>
        </div>
        <div class="mc-stat">
          <span class="mc-stat-label">Residuo / standby</span>
          <span class="mc-stat-val">${c.residual ? c.residual.cost_eur.toFixed(2) + ' €' : '--'}</span>
        </div>
        ${periodChips}
        ${shiftChips}
      </div>
      <p class="cost-tariff-note">Tarifa (${rateLbl} €/kWh) · Cobertura ${c.hours_covered.toFixed(1)} h</p>
    `;
  }

  /** Opción A: desglose de estados multi-nivel FHMM en las fichas técnicas */
  private renderMachineStatesBlock(m: any): string {
    if (!m.states || m.states.length <= 1) return '';
    const maxMin = Math.max(1, ...m.states.map((s: any) => s.minutes || 0));
    const rows = m.states
      .filter((s: any) => s.kw > 0)
      .map((s: any) => `
        <div class="state-row">
          <span class="state-name">${escapeHtml(s.name)}</span>
          <div class="state-bar">
            <span style="width:${Math.max(2, Math.round((s.minutes || 0) / maxMin * 100))}%; background:${m.color}"></span>
          </div>
          <span class="state-val">${s.kw.toFixed(2)} kW · ${s.minutes.toFixed(0)} min (${s.share_pct.toFixed(1)}%)</span>
        </div>
      `).join('');
    if (!rows) return '';
    return `
      <div class="mc-states">
        <span class="mc-states-title">🧠 Estados de Operación (FHMM Multi-Nivel)</span>
        ${rows}
      </div>
    `;
  }

  private renderTimelineTab() {
    if (!this.analysis) return;
    const container = document.getElementById('gantt-container');
    if (!container) return;

    // machine_id llega como number desde NumpyEncoder; normalizar por si
    // algun backend lo serializa como string ("0" !== 0 y el filtro del
    // Gantt dejaba todas las filas vacias).
    const machines = this.analysis.machine_statistics.map(m => ({
      id: Number(m.id),
      name: escapeHtml(m.name),
      color: m.color
    }));

    const intervals = (this.analysis.timeline_intervals || []).map(iv => ({
      ...iv,
      machine_id: Number((iv as any).machine_id),
      machine_name: escapeHtml(iv.machine_name || ''),
      // El backend FHMM envia `state`; el normal no tiene estado.
      state_name: iv.state_name || (iv as any).state || undefined
    }));

    if (intervals.length === 0) {
      const warn = (this.analysis as any).warning;
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">📭</div>
          <p><strong>Sin intervalos de operación para mostrar.</strong></p>
          <p>${escapeHtml(warn || 'Solo se detectaron ' + this.analysis.total_events_detected + ' eventos. Baja el umbral de corriente (p. ej. 0.5 A) o reduce el N° de equipos y re-ejecuta el análisis.')}</p>
        </div>`;
      const levelsContainer = document.getElementById('operation-levels-container');
      if (levelsContainer) levelsContainer.innerHTML = '';
      return;
    }

    ChartEngine.renderGanttTimeline(container, machines, intervals as any);

    const levelsContainer = document.getElementById('operation-levels-container');
    if (levelsContainer) {
      ChartEngine.renderOperationLevelLines(levelsContainer, machines, intervals as any);
    }
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

  /** STEP 1: Harmonic Signature tab — bars ΔH3/ΔH5/ΔH7 + scatter ΔH5 vs ΔP */
  private renderHarmonicTab() {
    if (!this.analysis) return;

    const sigs = (this.analysis.harmonic_signatures && this.analysis.harmonic_signatures.length)
      ? this.analysis.harmonic_signatures
      : this.analysis.machine_statistics.map(m => ({
          id: m.id, name: m.name, color: m.color,
          avg_delta_h3: m.avg_delta_h3 || 0,
          avg_delta_h5: m.avg_delta_h5 || 0,
          avg_delta_h7: m.avg_delta_h7 || 0,
          harm_ratio_pct: m.harm_ratio_pct || m.harmonic_signature_pct || 0,
          avg_thd: m.thd_pct, avg_delta_p: m.nominal_power_kw, count: m.event_count,
          /* MEJORA #20: firmas extendidas disponibles también en el fallback */
          avg_cosphi: m.avg_cosphi || 0,
          avg_inrush: m.avg_inrush || 1,
          phase_type: m.phase_type || '',
          load_class: m.load_class || ''
        }));

    const canvasSig = document.getElementById('chart-harmonic-signature') as HTMLCanvasElement;
    if (canvasSig) {
      const labels = sigs.map(s => s.name);
      const res = ChartEngine.renderGroupedBars(
        canvasSig,
        labels,
        [
          { name: 'ΔH3 [A]', color: '#3B82F6', data: sigs.map(s => Number(s.avg_delta_h3) || 0) },
          { name: 'ΔH5 [A]', color: '#EC4899', data: sigs.map(s => Number(s.avg_delta_h5) || 0) },
          { name: 'ΔH7 [A]', color: '#F59E0B', data: sigs.map(s => Number(s.avg_delta_h7) || 0) }
        ],
        'Firma armónica transitoria por equipo — salto medio ΔH en arranque [A]'
      );
      this.chartCleanups.push(res.destroy);
    }

    const canvasHarm = document.getElementById('chart-scatter-harm') as HTMLCanvasElement;
    if (canvasHarm) {
      const pts = this.analysis.scatter_events.map(e => ({
        x: Math.abs(e.delta_p),
        y: Math.abs(e.delta_h5 ?? 0),
        color: e.color,
        label: e.machine_name,
        cluster: e.cluster,
        time: e.timestamp
      }));
      const res = ChartEngine.renderScatter(
        canvasHarm,
        pts,
        '|ΔP| arranque [kW]',
        '|ΔH5| transitorio [A]'
      );
      this.chartCleanups.push(res.destroy);
    }
  }

  /** PASO 2: pestaña FHMM-Viterbi — secuencia combinada + curvas desagregadas */
  private renderFhmmTab() {
    if (!this.analysis) return;
    const meta = document.getElementById('fhmm-exact-info');
    const fx = this.analysis.fhmm_exact;
    if (meta) {
      if (!this.analysis.fhmm_enabled) {
        meta.innerHTML = '<div class="empty-state"><p>Activa <strong>🧠 Multi-Estado (FHMM)</strong> y re-ejecuta el análisis para ver la decodificación Viterbi.</p></div>';
      } else if (!fx) {
        meta.innerHTML = '<div class="empty-state"><p>Sin bloque FHMM en esta respuesta (backend anterior).</p></div>';
      } else if (!fx.method.startsWith('fhmm_exact_viterbi')) {
        meta.innerHTML = `<div class="fhmm-meta-grid">
          <div><span>Método</span><strong>Descenso por eventos (fallback)</strong></div>
          <div><span>Motivo</span><strong>${this.analysis.hmmlearn_available ? 'producto de estados > 400 (podado)' : 'hmmlearn no instalado'}</strong></div>
        </div>`;
      } else {
        const dimsTxt = fx.dims.map((d, i) => `M${i}:${d}`).join(' × ');
        meta.innerHTML = `<div class="fhmm-meta-grid">
          <div><span>Método</span><strong>FHMM exacto · Viterbi (hmmlearn)</strong></div>
          <div><span>Emisión</span><strong>${escapeHtml((fx.features ?? ['P']).join(' + '))}</strong></div>
          <div><span>Priors horarios</span><strong>${fx.priors_used ? 'activos' : 'inactivos'}</strong></div>
          <div><span>Log-prob</span><strong>${fx.logprob !== null ? fx.logprob.toFixed(1) : '--'}</strong></div>
          <div><span>Estados combinados</span><strong>${fx.n_comb_states} (${escapeHtml(dimsTxt)})</strong></div>
          <div><span>Muestras decodificadas</span><strong>${fx.n_points_decoded} / ${fx.n_points_full} (paso ${fx.downsample_step})</strong></div>
        </div>`;
      }
    }

    this.renderFhmmHourlyCharts();

    const canvas = document.getElementById('chart-fhmm-viterbi') as HTMLCanvasElement;
    if (!canvas || !this.analysis.fhmm_enabled) return;
    const fx2 = this.analysis.fhmm_exact;
    if (fx2 && fx2.method.startsWith('fhmm_exact_viterbi') && fx2.combined_seq_ds.length > 1) {
      // Secuencia de estado combinado (downsampleada) como serie temporal.
      const seq = fx2.combined_seq_ds;
      const labels = seq.map((_, i) => `${i}`);
      const res = ChartEngine.renderTimeSeries(
        canvas, labels,
        [{ name: 'Estado combinado (Viterbi)', data: seq, color: '#8B5CF6' }],
        'estado', 'Secuencia Viterbi combinada (índice de estado conjunto)'
      );
      this.chartCleanups.push(res.destroy);
    } else {
      // Fallback: curvas desagregadas multi-estado.
      const seriesList = [
        { name: 'Potencia Total Medida', data: this.analysis.p_total, color: '#00B5E2', fill: true }
      ];
      this.analysis.disaggregated_machines.forEach(m => {
        seriesList.push({ name: m.name, data: m.data, color: m.color });
      });
      const res = ChartEngine.renderTimeSeries(
        canvas, this.analysis.timestamps, seriesList as any, 'kW',
        'Desagregación FHMM (descenso por eventos — hmmlearn no disponible o podado)'
      );
      this.chartCleanups.push(res.destroy);
    }
  }

  /** MEJORA #2: priors horarios — perfil de arranque por equipo y comparativa minutos ON sin/con priors */
  private renderFhmmHourlyCharts(): void {
    const fx = this.analysis?.fhmm_exact;
    if (!fx) return;
    const palette = ["#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899", "#06B6D4", "#84CC16"];

    // Grafico 1: perfil horario del prior de arranque por equipo (mejora #2)
    const c1 = document.getElementById("chart-fhmm-priors") as HTMLCanvasElement | null;
    if (c1 && fx.priors_used && fx.hourly_priors) {
      const ctx = c1.getContext("2d");
      if (ctx) {
        const W = c1.width, H = c1.height;
        ctx.clearRect(0, 0, W, H);
        const padL = 46, padR = 12, padT = 16, padB = 24;
        const keys = Object.keys(fx.hourly_priors);
        const vals = keys.map(k => fx.hourly_priors![k]);
        const maxV = Math.max(1.2, ...vals.map(a => Math.max(...a)));
        const plotH = H - padT - padB;
        const xw = (W - padL - padR) / 23;
        ctx.strokeStyle = "#e5e7eb";
        ctx.beginPath();
        for (let g = 0; g <= 4; g++) {
          const y = padT + plotH * g / 4;
          ctx.moveTo(padL, y);
          ctx.lineTo(W - padR, y);
        }
        ctx.stroke();
        ctx.fillStyle = "#6b7280";
        ctx.font = "10px sans-serif";
        ctx.textAlign = "right";
        for (let g = 0; g <= 4; g++) {
          ctx.fillText((maxV * (4 - g) / 4).toFixed(2), padL - 6, padT + plotH * g / 4 + 3);
        }
        ctx.textAlign = "center";
        for (let h = 0; h <= 23; h += 3) {
          ctx.fillText(String(h).padStart(2, "0") + "h", padL + h * xw, H - 8);
        }
        keys.forEach((k, i) => {
          const arr = fx.hourly_priors![k];
          ctx.strokeStyle = palette[i % palette.length];
          ctx.lineWidth = 2;
          ctx.beginPath();
          arr.forEach((v, h) => {
            const x = padL + h * xw;
            const y = H - padB - v * (plotH / maxV);
            if (h === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
          });
          ctx.stroke();
        });
        ctx.textAlign = "left";
        ctx.font = "11px sans-serif";
        keys.forEach((k, i) => {
          const m = this.analysis?.machine_statistics?.find(s => String(s.id) === k);
          ctx.fillStyle = palette[i % palette.length];
          const label = m ? m.name.slice(0, 26) : "Equipo " + k;
          ctx.fillText(label, padL + 4 + (i % 4) * 130, padT + 10 + Math.floor(i / 4) * 12);
        });
      }
    }

    // Grafico 2: minutos ON por hora, sin priors (gris) vs con priors (azul)
    const c2 = document.getElementById("chart-fhmm-compare") as HTMLCanvasElement | null;
    if (c2 && fx.on_minutes_total_before && fx.on_minutes_total_after) {
      const ctx2 = c2.getContext("2d");
      if (ctx2) {
        const W = c2.width, H = c2.height;
        ctx2.clearRect(0, 0, W, H);
        const padL = 46, padR = 12, padT = 16, padB = 24;
        const B = fx.on_minutes_total_before, A = fx.on_minutes_total_after;
        const maxV = Math.max(1, ...B, ...A);
        const plotH = H - padT - padB;
        const bw = (W - padL - padR) / 24;
        ctx2.strokeStyle = "#e5e7eb";
        ctx2.beginPath();
        for (let g = 0; g <= 4; g++) {
          const y = padT + plotH * g / 4;
          ctx2.moveTo(padL, y);
          ctx2.lineTo(W - padR, y);
        }
        ctx2.stroke();
        ctx2.fillStyle = "#6b7280";
        ctx2.font = "10px sans-serif";
        ctx2.textAlign = "right";
        for (let g = 0; g <= 4; g++) {
          ctx2.fillText(String(Math.round(maxV * (4 - g) / 4)), padL - 6, padT + plotH * g / 4 + 3);
        }
        B.forEach((v, h) => {
          ctx2.fillStyle = "#9ca3af";
          ctx2.fillRect(padL + h * bw + 1, H - padB - v * (plotH / maxV), Math.max(2, bw / 2 - 2), v * (plotH / maxV));
        });
        A.forEach((v, h) => {
          ctx2.fillStyle = "#3B82F6";
          ctx2.fillRect(padL + h * bw + bw / 2 + 1, H - padB - v * (plotH / maxV), Math.max(2, bw / 2 - 2), v * (plotH / maxV));
        });
        ctx2.fillStyle = "#6b7280";
        ctx2.textAlign = "center";
        for (let h = 0; h <= 23; h += 3) {
          ctx2.fillText(String(h).padStart(2, "0") + "h", padL + h * bw + bw / 2, H - 8);
        }
        ctx2.textAlign = "left";
        ctx2.font = "11px sans-serif";
        ctx2.fillStyle = "#9ca3af";
        ctx2.fillText("Sin priors", padL + 4, padT + 10);
        ctx2.fillStyle = "#3B82F6";
        ctx2.fillText("Con priors", padL + 74, padT + 10);
      }
    }

    // Nota resumen en el bloque de metadatos FHMM
    const info = document.getElementById("fhmm-exact-info");
    if (info && fx.priors_used) {
      const red = fx.night_minutes_reduced ?? 0;
      const div = document.createElement("div");
      div.className = "fhmm-priors-note";
      div.textContent = "Priors horarios activos: minutos ON nocturnos (22h-06h) " +
        (red > 0 ? "reducidos en " + red.toFixed(1) + " min" : "sin cambios") +
        " - logprob " + fx.logprob + " con priors vs " + fx.logprob_no_priors + " sin priors.";
      info.appendChild(div);
    }
  }

  private renderValidationTab() {
    if (!this.analysis) return;
    const v = this.analysis.validation;

    const summary = document.getElementById('validation-summary');
    if (summary) {
      if (!v || !v.reconstruction) {
        summary.innerHTML = '<div class="empty-state"><p>Sin datos de validación en esta respuesta (backend anterior). Re-ejecuta el análisis.</p></div>';
      } else {
        const r = v.reconstruction;
        const cg = v.confusion_global;
        const tg = v.transitions_global;
        const bc = v.confidence;
        summary.innerHTML = `
          <div class="val-card"><span>MAE reconstrucción</span><strong>${r.mae_kw.toFixed(3)} kW</strong></div>
          <div class="val-card"><span>RMSE</span><strong>${r.rmse_kw.toFixed(3)} kW</strong></div>
          <div class="val-card"><span>MAPE</span><strong>${r.mape_pct.toFixed(1)} %</strong></div>
          <div class="val-card"><span>Energía explicada</span><strong>${r.energy_explained_pct.toFixed(1)} %</strong></div>
          <div class="val-card"><span>RE (error energía total)</span><strong>${(r.re_pct ?? 0).toFixed(1)} %</strong></div>
          <div class="val-card"><span>NEP global</span><strong>${(r.nep ?? 0).toFixed(3)}</strong></div>
          <div class="val-card"><span>F1 global ON/OFF</span><strong>${cg.f1.toFixed(3)}</strong></div>
          <div class="val-card"><span>Accuracy global</span><strong>${(cg.accuracy ?? 0).toFixed(3)}</strong></div>
          <div class="val-card"><span>Precision / Recall</span><strong>${cg.precision.toFixed(3)} / ${cg.recall.toFixed(3)}</strong></div>
          <div class="val-card"><span>Matriz global</span><strong>TP ${cg.tp} · FP ${cg.fp} · FN ${cg.fn} · TN ${cg.tn}</strong></div>${tg ? `
          <div class="val-card"><span>F1 arranques (Gantt)</span><strong>${tg.f1.toFixed(3)}</strong></div>
          <div class="val-card"><span>Arranques TP / FP / FN</span><strong>${tg.tp} · ${tg.fp} · ${tg.fn}</strong></div>
          <div class="val-card"><span>Desfase arranques (med / máx)</span><strong>${tg.dt_median_s.toFixed(1)} / ${tg.dt_max_s.toFixed(1)} s</strong></div>` : ''}${bc && bc.confusion_global ? `
          <div class="val-card"><span>F1 global ON/OFF (IC ${bc.ci_pct} %, n=${bc.n_boot})</span><strong>${bc.confusion_global.f1.mean.toFixed(3)} ± ${bc.confusion_global.f1.half.toFixed(3)}</strong></div>
          <div class="val-card"><span>Rango F1 ON/OFF</span><strong>[${bc.confusion_global.f1.lo.toFixed(3)}, ${bc.confusion_global.f1.hi.toFixed(3)}]</strong></div>
          <div class="val-card"><span>F1 arranques (IC ${bc.ci_pct} %)</span><strong>${bc.transitions_global.f1.mean.toFixed(3)} ± ${bc.transitions_global.f1.half.toFixed(3)}</strong></div>` : ''}`;
      }
    }

    const machinesEl = document.getElementById('validation-machines');
    if (machinesEl) {
      if (!v || !v.machines || v.machines.length === 0) {
        machinesEl.innerHTML = '<div class="empty-state"><p>Sin validación por equipo disponible.</p></div>';
      } else {
        machinesEl.innerHTML = v.machines.map(m => `
          <div class="machine-val" style="border-left-color: ${m.color}">
            <div class="machine-val-head">
              <span class="machine-id">M${m.id}</span>
              <strong>${escapeHtml(m.name)}</strong>
              <span class="machine-f1">F1 ${m.f1.toFixed(3)}</span>
            </div>
            <div class="machine-val-row"><span>Arranques ref.</span><strong>${m.n_on_events}</strong></div>
            ${m.transitions ? `<div class="machine-val-row"><span>Arranques det. TP / FP / FN</span><strong>${m.transitions.tp} · ${m.transitions.fp} · ${m.transitions.fn} — F1 ${m.transitions.f1.toFixed(3)}</strong></div>
            <div class="machine-val-row"><span>Desfase arranques (med / máx)</span><strong>${m.transitions.dt_median_s.toFixed(1)} / ${m.transitions.dt_max_s.toFixed(1)} s (tol ${m.transitions.tolerance_s?.toFixed(0) ?? '60'} s)</strong></div>` : ''}
            <div class="machine-val-row"><span>MAE salto ON</span><strong>${m.jump_mae_kw.toFixed(3)} kW</strong></div>
            <div class="machine-val-row"><span>P / R / Acc</span><strong>${m.precision.toFixed(3)} / ${m.recall.toFixed(3)} / ${(m.accuracy ?? 0).toFixed(3)}</strong></div>
            <div class="machine-val-row"><span>MAE energía</span><strong>${(m.reg_mae_kw ?? 0).toFixed(3)} kW</strong></div>
            <div class="machine-val-row"><span>RMSE energía</span><strong>${(m.reg_rmse_kw ?? 0).toFixed(3)} kW</strong></div>
            <div class="machine-val-row"><span>RE / NEP</span><strong>${(m.re_pct ?? 0).toFixed(1)} % / ${(m.nep ?? 0).toFixed(3)}</strong></div>
            <table class="conf-table">
              <tr><th></th><th>Pred ON</th><th>Pred OFF</th></tr>
              <tr><th>Ref ON</th><td class="tp">${m.confusion.tp}</td><td class="fn">${m.confusion.fn}</td></tr>
              <tr><th>Ref OFF</th><td class="fp">${m.confusion.fp}</td><td class="tn">${m.confusion.tn}</td></tr>
            </table>
          </div>`).join('');
      }
    }

    const canvas = document.getElementById('chart-validation-f1') as HTMLCanvasElement;
    if (!canvas) return;
    if (!v || !v.machines || v.machines.length === 0) {
      const ctx = canvas.getContext('2d');
      if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
      return;
    }
    ChartEngine.renderBarChart(
      canvas,
      v.machines.map(m => `M${m.id}`),
      v.machines.map(m => m.f1),
      '#10B981',
      'F1',
      'F1-score de detección ON/OFF por equipo (1.0 = desagregación perfecta)'
    );
  }

  /* ================= MEJORA #9/#10: Benchmark ================= */

  /** MEJORA #13: fugas / standby — KPIs del residuo + curva de duración. */
  private renderStandbyTab(): void {
    const sb = this.analysis?.standby ?? null;
    // MEJORA #14: el bloque de anomalias vive en la misma pestana.
    this.renderAnomalyBlock();
    const kpiBox = document.getElementById('standby-kpis');
    const methodBox = document.getElementById('standby-method');
    const empty = '<div class="empty-state"><p>Ejecuta el análisis NILM para cuantificar el consumo fantasma (residuo no atribuido).</p></div>';
    if (!sb || !sb.duration_baseline_kw || sb.duration_baseline_kw.length < 2) {
      if (kpiBox) kpiBox.innerHTML = empty;
      if (methodBox) methodBox.innerHTML = '';
      const c1 = document.getElementById('chart-standby-duration') as HTMLCanvasElement | null;
      const c2 = document.getElementById('chart-standby-hist') as HTMLCanvasElement | null;
      if (c1) { const g = c1.getContext('2d'); if (g) g.clearRect(0, 0, c1.width, c1.height); }
      if (c2) { const g = c2.getContext('2d'); if (g) g.clearRect(0, 0, c2.width, c2.height); }
      return;
    }
    const b = sb.baseline_kw;
    const n = sb.night_kw;
    const cards = [
      { label: 'Standby medio (P50)', value: `${b.p50.toFixed(2)} kW`, note: `media ${b.mean.toFixed(2)} · P10 ${b.p10.toFixed(2)} · máx ${b.max.toFixed(2)} kW` },
      { label: `Mínimo nocturno (${n.window})`, value: `${n.p10.toFixed(2)} kW`, note: `P50 noche ${n.p50.toFixed(2)} kW · ${n.samples} muestras` },
      { label: 'Cuota del total', value: `${sb.share_pct.toFixed(1)} %`, note: `energía periodo ${sb.energy_kwh.toFixed(1)} kWh en ${sb.hours_covered.toFixed(1)} h` },
      { label: 'Proyección anual', value: `${sb.annual_kwh.toFixed(0)} kWh/año`, note: 'media × 8760 h — multiplica por tu tarifa para el ahorro potencial' },
    ];
    if (kpiBox) {
      kpiBox.innerHTML = cards.map(c => `
        <div class="val-card">
          <h4>${escapeHtml(c.label)}</h4>
          <div class="val-main">${escapeHtml(c.value)}</div>
          <small>${escapeHtml(c.note)}</small>
        </div>`).join('');
    }
    if (methodBox) methodBox.innerHTML = `<small>${escapeHtml(sb.method)}</small>`;

    const cDur = document.getElementById('chart-standby-duration') as HTMLCanvasElement | null;
    if (cDur) {
      const labels = sb.duration_pct.map(p => `${p.toFixed(0)}%`);
      const res = ChartEngine.renderTimeSeries(
        cDur, labels,
        [
          { name: 'Standby (residuo)', data: sb.duration_baseline_kw, color: '#F59E0B', fill: true },
          { name: 'Total medido', data: sb.duration_total_kw, color: '#00B5E2' }
        ],
        'kW', 'Curva de duración: potencia superada el X% del tiempo'
      );
      this.chartCleanups.push(res.destroy);
    }
    const cHist = document.getElementById('chart-standby-hist') as HTMLCanvasElement | null;
    if (cHist && sb.hist.counts.length > 0) {
      const labels = sb.hist.edges.slice(0, -1).map(e => e.toFixed(1));
      const res = ChartEngine.renderBarChart(cHist, labels, sb.hist.counts, '#8B5CF6', '', 'Distribución del standby (kW)');
      this.chartCleanups.push(res.destroy);
    }
  }

  /** MEJORA #14: anomalías sobre el residuo — MAE móvil vs umbral MAD. */
  private renderAnomalyBlock(): void {
    const ra = this.analysis?.residual_anomalies ?? null;
    const kpiBox = document.getElementById('anomaly-kpis');
    const eventsBox = document.getElementById('anomaly-events');
    const methodBox = document.getElementById('anomaly-method');
    const canvas = document.getElementById('chart-anomaly-mae') as HTMLCanvasElement | null;
    const empty = '<div class="empty-state"><p>Ejecuta el análisis NILM para detectar anomalías en el residuo.</p></div>';
    if (!ra || !ra.mae_series || ra.mae_series.length < 2) {
      if (kpiBox) kpiBox.innerHTML = empty;
      if (eventsBox) eventsBox.innerHTML = '';
      if (methodBox) methodBox.innerHTML = '';
      if (canvas) { const g = canvas.getContext('2d'); if (g) g.clearRect(0, 0, canvas.width, canvas.height); }
      return;
    }
    const cards = [
      { label: 'Umbral (mediana + 3·MAD)', value: `${ra.threshold_kw.toFixed(3)} kW`, note: `centro ${ra.center_kw.toFixed(3)} kW · ventana ${ra.window_minutes.toFixed(0)} min (${ra.window_samples} muestras)` },
      { label: 'MAE máximo del residuo', value: `${ra.max_mae_kw.toFixed(3)} kW`, note: `P50 ${ra.mae_kw.p50.toFixed(3)} · P95 ${ra.mae_kw.p95.toFixed(3)} kW` },
      { label: 'Eventos sostenidos', value: `${ra.n_events}`, note: `≥ ${ra.min_run_samples} muestras contiguas` },
      { label: 'Muestras anómalas', value: `${ra.anomalous_pct.toFixed(1)} %`, note: `${ra.samples} muestras analizadas` },
    ];
    if (kpiBox) {
      kpiBox.innerHTML = cards.map(c => `
        <div class="val-card">
          <h4>${escapeHtml(c.label)}</h4>
          <div class="val-main">${escapeHtml(c.value)}</div>
          <small>${escapeHtml(c.note)}</small>
        </div>`).join('');
    }
    if (methodBox) methodBox.innerHTML = `<small>${escapeHtml(ra.method)}</small>`;

    if (canvas) {
      const labels = ra.labels_pct.map(p => `${p.toFixed(0)}%`);
      const res = ChartEngine.renderTimeSeries(canvas, labels, [
        { name: 'MAE del residuo', data: ra.mae_series, color: '#EF4444', fill: true },
        { name: 'Umbral (mediana + 3·MAD)', data: ra.threshold_series, color: '#F59E0B', dash: [6, 4] },
      ], 'kW', 'MAE móvil del residuo vs umbral robusto');
      this.chartCleanups.push(res.destroy);
    }

    if (eventsBox) {
      if (!ra.events || ra.events.length === 0) {
        eventsBox.innerHTML = '<p class="card-subtitle">Sin picos sostenidos por encima del umbral.</p>';
      } else {
        const shown = ra.events.slice(0, 12);
        eventsBox.innerHTML = `<div class="validation-grid">` + shown.map((e, i) => `
          <div class="val-card">
            <h4>Evento ${i + 1} · ${e.duration_min.toFixed(0)} min</h4>
            <div class="val-main">${e.peak_mae_kw.toFixed(3)} kW</div>
            <small>${escapeHtml(e.start_iso || `${e.start_pct.toFixed(0)}%`)} → ${escapeHtml(e.end_iso || `${e.end_pct.toFixed(0)}%`)}</small>
          </div>`).join('') + `</div>` +
          (ra.events.length > shown.length
            ? `<p class="card-subtitle">+${ra.events.length - shown.length} eventos adicionales en el JSON del análisis.</p>`
            : '');
      }
    }
  }

  private async runBenchmark() {
    if (!this.currentDatasetId) {
      this.showToast('Carga primero una medición para ejecutar el benchmark.', 'error');
      return;
    }

    const clusterSlider = document.getElementById('slider-clusters') as HTMLInputElement;
    const thresholdSlider = document.getElementById('slider-threshold') as HTMLInputElement;
    const nClusters = clusterSlider ? parseInt(clusterSlider.value, 10) : 4;
    const currentThr = thresholdSlider ? parseFloat(thresholdSlider.value) : 2.0;
    const powerThr = 1.0;

    const configs: Array<{ label: string; kind: 'algoritmo' | 'estabilidad'; algorithm: string; cur: number; pow: number; fhmm: boolean }> = [
      { label: `K-Means (nominal)`, kind: 'algoritmo', algorithm: 'kmeans', cur: currentThr, pow: powerThr, fhmm: false },
      { label: `GMM (nominal)`, kind: 'algoritmo', algorithm: 'gmm', cur: currentThr, pow: powerThr, fhmm: false },
      { label: `DBSCAN (nominal)`, kind: 'algoritmo', algorithm: 'dbscan', cur: currentThr, pow: powerThr, fhmm: false },
      { label: `FHMM (K-Means + FHMM)`, kind: 'algoritmo', algorithm: 'kmeans', cur: currentThr, pow: powerThr, fhmm: this.useFhmm },
      { label: `Umbral −20% (${(currentThr * 0.8).toFixed(2)} A)`, kind: 'estabilidad', algorithm: 'kmeans', cur: currentThr * 0.8, pow: powerThr * 0.8, fhmm: false },
      { label: `Umbral +20% (${(currentThr * 1.2).toFixed(2)} A)`, kind: 'estabilidad', algorithm: 'kmeans', cur: currentThr * 1.2, pow: powerThr * 1.2, fhmm: false }
    ];

    const progress = document.getElementById('benchmark-progress');
    const btn = document.getElementById('btn-run-benchmark') as HTMLButtonElement | null;
    if (btn) btn.disabled = true;
    if (progress) progress.innerHTML = '<p>⏳ Ejecutando benchmark… 0 / ' + configs.length + '</p>';

    try {
    const rows: BenchmarkRow[] = [];
    for (let i = 0; i < configs.length; i++) {
      const c = configs[i];
      if (progress) progress.innerHTML = `<p>⏳ Ejecutando benchmark… ${i + 1} / ${configs.length} — <strong>${escapeHtml(c.label)}</strong></p>`;
      const t0 = performance.now();
      try {
        const res = await api.runAnalysis({
          dataset_id: this.currentDatasetId,
          n_clusters: nClusters,
          algorithm: c.algorithm as any,
          current_threshold: c.cur,
          power_threshold: c.pow,
          use_fhmm: c.fhmm,
          max_states: 3
        });
        const elapsed = (performance.now() - t0) / 1000;
        const rec = res.validation?.reconstruction;
        const cg = res.validation?.confusion_global;
        rows.push({
          config: c.label,
          kind: c.kind,
          algorithm: c.algorithm,
          current_threshold: c.cur,
          power_threshold: c.pow,
          use_fhmm: c.fhmm,
          n_clusters: res.n_clusters,
          mae_kw: rec ? rec.mae_kw : NaN,
          rmse_kw: rec ? rec.rmse_kw : NaN,
          re_pct: rec ? (rec.re_pct ?? NaN) : NaN,
          f1: cg ? cg.f1 : NaN,
          accuracy: cg ? (cg.accuracy ?? NaN) : NaN,
          total_events: res.total_events_detected,
          elapsed_s: elapsed,
          ok: !!(rec && cg)
        });
      } catch (err: any) {
        console.error(err);
        rows.push({
          config: c.label, kind: c.kind, algorithm: c.algorithm,
          current_threshold: c.cur, power_threshold: c.pow, use_fhmm: c.fhmm,
          n_clusters: nClusters, mae_kw: NaN, rmse_kw: NaN, re_pct: NaN,
          f1: NaN, accuracy: NaN, total_events: 0,
          elapsed_s: (performance.now() - t0) / 1000, ok: false, error: err.message
        });
      }
    }

    // Estabilidad: media ± desviación típica de F1 / RE sobre las 3 variantes de umbral
    const stab = rows.filter(r => r.kind === 'estabilidad' && r.ok);
    const center = rows.find(r => r.kind === 'algoritmo' && r.algorithm === 'kmeans' && !r.use_fhmm && r.ok);
    const stabAll = center ? [center, ...stab] : stab;
    const mean = (a: number[]) => a.length ? a.reduce((s, v) => s + v, 0) / a.length : NaN;
    const std = (a: number[]) => a.length > 1 ? Math.sqrt(mean(a.map(v => (v - mean(a)) ** 2))) : 0;

    const f1s = stabAll.map(r => r.f1).filter(Number.isFinite);
    const res_ = stabAll.map(r => r.re_pct).filter(Number.isFinite);
    const okRows = rows.filter(r => r.ok && Number.isFinite(r.f1));
    const best = okRows.length ? okRows.reduce((b, r) => (r.f1 > b.f1 ? r : b)) : null;

    this.benchmark = {
      rows,
      f1_mean_stab: mean(f1s),
      f1_std_stab: std(f1s),
      re_mean_stab: mean(res_),
      re_std_stab: std(res_),
      best
    };

    if (progress) progress.innerHTML = '<p>✅ Benchmark completado. Resultados ordenados por F1 en la comparativa inferior.</p>';
    if (btn) btn.disabled = false;
    this.showToast('Benchmark completado (6 configuraciones evaluadas)', 'success');
    this.renderBenchmarkTab();
    } catch (err: any) {
      console.error('Error fatal en benchmark:', err);
      if (progress) progress.innerHTML = `<p>❌ Error en el benchmark: ${escapeHtml(String(err?.message ?? err))}</p>`;
      if (btn) btn.disabled = false;
      this.showToast(`Error en el benchmark: ${err?.message ?? err}`, 'error');
    }
  }

  /* ================= MEJORA #21: Calidad Energética ================= */

  private renderPowerQualityTab() {
    const checksEl = document.getElementById('pq-checks');
    const eventsEl = document.getElementById('pq-events-table');
    const canvasV = document.getElementById('chart-pq-voltage') as HTMLCanvasElement | null;
    const canvasTHD = document.getElementById('chart-pq-thdu') as HTMLCanvasElement | null;
    const canvasN = document.getElementById('chart-pq-neutral') as HTMLCanvasElement | null;

    if (!this.powerQuality) {
      if (checksEl) {
        checksEl.innerHTML = '<div class="empty-state"><p>Calidad energética no disponible para esta medición (el export debe incluir columnas de tensión, THD y neutro).</p></div>';
      }
      return;
    }
    const pq = this.powerQuality;

    // Tarjetas de cumplimiento (ok/warn/bad)
    if (checksEl) {
      const icon: Record<string, string> = { ok: '✅', warn: '⚠️', bad: '❌' };
      checksEl.innerHTML = pq.checks.map(c => `
        <div class="val-card pq-check-${c.status}">
          <span>${icon[c.status] || ''} ${escapeHtml(c.label)}</span>
          <strong>${escapeHtml(c.value)}</strong>
          <small>${escapeHtml(c.limit)}</small>
          <em>${escapeHtml(c.note)}</em>
        </div>`).join('');
    }

    // Gráfico 1: tensión por fase (3 series + línea del nominal)
    if (canvasV) {
      const res = ChartEngine.renderTimeSeries(
        canvasV,
        pq.timeseries.timestamps,
        [
          { name: 'U L1', data: pq.timeseries.v_l1, color: '#EF4444' },
          { name: 'U L2', data: pq.timeseries.v_l2, color: '#10B981' },
          { name: 'U L3', data: pq.timeseries.v_l3, color: '#3B82F6' }
        ],
        'V',
        `Tensión por fase (nominal ${pq.vnom.toFixed(0)} V, límites ±10%)`
      );
      if (res && typeof res.destroy === 'function') this.chartCleanups.push(res.destroy);
    }

    // Gráfico 2: THD U + desequilibrio (eje %)
    if (canvasTHD) {
      const series: any[] = [
        { name: 'THD U (%)', data: pq.timeseries.thd_u, color: '#F59E0B' }
      ];
      if (pq.timeseries.u2u1.length > 0) {
        series.push({ name: 'U2/U1 desequilibrio (%)', data: pq.timeseries.u2u1, color: '#8B5CF6' });
      }
      const res = ChartEngine.renderTimeSeries(
        canvasTHD,
        pq.timeseries.timestamps,
        series,
        '%',
        'THD de tensión y desequilibrio (límite EN 50160: THD U < 8%, U2/U1 < 2%)'
      );
      if (res && typeof res.destroy === 'function') this.chartCleanups.push(res.destroy);
    }

    // Gráfico 3: corriente de neutro vs fases
    if (canvasN) {
      const series: any[] = [
        { name: 'I L1', data: pq.timeseries.i_l1, color: '#EF4444' },
        { name: 'I L2', data: pq.timeseries.i_l2, color: '#10B981' },
        { name: 'I L3', data: pq.timeseries.i_l3, color: '#3B82F6' }
      ];
      if (pq.timeseries.i_n.length > 0) {
        series.push({ name: 'I Neutro', data: pq.timeseries.i_n, color: '#F97316', dash: [6, 4] });
      }
      const res = ChartEngine.renderTimeSeries(
        canvasN,
        pq.timeseries.timestamps,
        series,
        'A',
        'Corriente de neutro vs. fases (neutro alto = armónicos triplen de cargas monofásicas)'
      );
      if (res && typeof res.destroy === 'function') this.chartCleanups.push(res.destroy);
    }

    // Tabla de eventos de tensión (sags + swells combinados, ordenados por hora)
    if (eventsEl) {
      const all = [
        ...pq.sags.map(e => ({ ...e, kind: 'Sag (<90%)' })),
        ...pq.swells.map(e => ({ ...e, kind: 'Swell (>110%)' }))
      ].sort((a, b) => a.start.localeCompare(b.start));

      if (all.length === 0) {
        eventsEl.innerHTML = '<div class="empty-state"><p>✅ Sin sags ni swells sostenidos en toda la medición (U siempre entre 90% y 110% del nominal).</p></div>';
      } else {
        eventsEl.innerHTML = `<div class="table-responsive"><table class="data-table">
          <thead><tr><th>Tipo</th><th>Inicio</th><th>Fin</th><th>Duración (min)</th><th>Tensión extrema (V)</th><th>Profundidad (%)</th><th>Fase más afectada</th></tr></thead>
          <tbody>${all.map(e => `
            <tr>
              <td>${e.kind === 'Sag (<90%)' ? '⬇️ Sag' : '⬆️ Swell'}</td>
              <td>${escapeHtml(e.start)}</td>
              <td>${escapeHtml(e.end)}</td>
              <td>${e.duration_min.toFixed(1)}</td>
              <td>${e.extreme_v.toFixed(1)} V</td>
              <td>${e.depth_pct.toFixed(1)} %</td>
              <td>${e.phase ? escapeHtml(e.phase) : '--'}</td>
            </tr>`).join('')}</tbody>
        </table></div>`;
      }
    }
  }

  private renderBenchmarkTab() {
    const progress = document.getElementById('benchmark-progress');
    const summary = document.getElementById('benchmark-summary');
    const tableEl = document.getElementById('benchmark-table');
    const canvas = document.getElementById('chart-benchmark-f1') as HTMLCanvasElement | null;

    if (!this.benchmark) {
      if (progress && !progress.innerHTML.includes('⏳')) {
        progress.innerHTML = '<p>Ejecuta el benchmark para comparar configuraciones. Puede tardar varios segundos (6 ejecuciones del análisis).</p>';
      }
      return;
    }

    const b = this.benchmark;

    if (summary) {
      summary.innerHTML = `
        <div class="val-card"><span>Mejor configuración (F1)</span><strong>${b.best ? escapeHtml(b.best.config) : '—'}</strong></div>
        <div class="val-card"><span>F1 mejor config.</span><strong>${b.best ? b.best.f1.toFixed(3) : '--'}</strong></div>
        <div class="val-card"><span>F1 medio (estabilidad ±20%)</span><strong>${Number.isFinite(b.f1_mean_stab) ? b.f1_mean_stab.toFixed(3) : '--'} ± ${b.f1_std_stab.toFixed(3)}</strong></div>
        <div class="val-card"><span>RE energía (estabilidad ±20%)</span><strong>${Number.isFinite(b.re_mean_stab) ? b.re_mean_stab.toFixed(1) : '--'} % ± ${b.re_std_stab.toFixed(1)}</strong></div>
        <div class="val-card"><span>Coef. variación F1</span><strong>${Number.isFinite(b.f1_mean_stab) && b.f1_mean_stab > 0 ? ((b.f1_std_stab / b.f1_mean_stab) * 100).toFixed(1) : '--'} %</strong></div>
        <div class="val-card"><span>Configuraciones evaluadas</span><strong>${b.rows.filter(r => r.ok).length} / ${b.rows.length}</strong></div>`;
    }

    const ranked = [...b.rows].sort((a, r) => {
      if (a.ok !== r.ok) return a.ok ? -1 : 1;
      return (Number.isFinite(r.f1) ? r.f1 : -1) - (Number.isFinite(a.f1) ? a.f1 : -1);
    });

    if (tableEl) {
      if (!b.rows.some(r => r.ok)) {
        tableEl.innerHTML = '<div class="empty-state"><p>No se pudo completar ninguna configuración. Revisa que el backend esté activo.</p></div>';
      } else {
        tableEl.innerHTML = `<div class="table-responsive"><table class="data-table">
          <thead><tr><th>#</th><th>Configuración</th><th>Tipo</th><th>MAE (kW)</th><th>RMSE (kW)</th><th>RE (%)</th><th>F1</th><th>Accuracy</th><th>Eventos</th><th>Tiempo (s)</th></tr></thead>
          <tbody>${ranked.map((r, i) => `
            <tr style="${r.ok ? '' : 'opacity:0.55;'}">
              <td>${i + 1}</td>
              <td>${escapeHtml(r.config)}${r.use_fhmm ? ' 🧠' : ''}</td>
              <td>${r.kind}</td>
              <td>${fmtNum(r.mae_kw, 3)}</td>
              <td>${fmtNum(r.rmse_kw, 3)}</td>
              <td>${fmtNum(r.re_pct, 1)}</td>
              <td><strong>${fmtNum(r.f1, 3)}</strong></td>
              <td>${fmtNum(r.accuracy, 3)}</td>
              <td>${r.total_events}</td>
              <td>${r.elapsed_s.toFixed(2)}</td>
            </tr>`).join('')}</tbody>
        </table></div>`;
      }
    }

    // Gráfico: F1 por configuración (ordenado por F1)
    if (canvas) {
      const okRowsChart = ranked.filter(r => r.ok && Number.isFinite(r.f1));
      if (okRowsChart.length === 0) {
        const ctx = canvas.getContext('2d');
        if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
      } else {
        const res = ChartEngine.renderBarChart(
          canvas,
          okRowsChart.map(r => r.config),
          okRowsChart.map(r => r.f1),
          '#00B5E2',
          'F1',
          'F1 ON/OFF por configuración (benchmark de algoritmos y estabilidad de umbrales ±20%)'
        );
        if (res && typeof res.destroy === 'function') {
          this.chartCleanups.push(res.destroy);
        }
      }
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