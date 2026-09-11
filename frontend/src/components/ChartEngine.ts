/**
 * ChartEngine: High Performance Canvas/SVG Charts for NILM Dashboard
 * Zero external dependencies, pure TypeScript implementation.
 */

export interface SeriesConfig {
  name: string;
  data: number[];
  color: string;
  fill?: boolean;
  dash?: number[];
}

function chartColor(variable: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(variable).trim() || fallback;
}

/**
 * Resolves the real available size for a canvas. Falls back to the parent
 * element width (even when the canvas rect reports 0 because the tab was
 * hidden at render time), and finally to the viewport, so charts always
 * stretch to the full width of the page.
 */
function resolveSize(
  canvas: HTMLCanvasElement,
  fallbackW: number,
  fallbackH: number
): { w: number; h: number } {
  const rect = canvas.getBoundingClientRect?.() || { width: 0, height: 0 };
  const parent = canvas.parentElement;
  const parentW = parent ? parent.clientWidth || parent.getBoundingClientRect().width || 0 : 0;
  const parentH = parent ? parent.clientHeight || parent.getBoundingClientRect().height || 0 : 0;
  const w = rect.width || parentW || window.innerWidth || fallbackW;
  const h = rect.height || parentH || fallbackH;
  return { w, h };
}

export class ChartEngine {
  /**
   * Renders interactive multi-line / area time-series chart on HTML5 Canvas
   */
  static renderTimeSeries(
    canvas: HTMLCanvasElement,
    labels: string[],
    seriesList: SeriesConfig[],
    unit: string = 'kW',
    title: string = ''
  ): { destroy: () => void } {
    const ctx = canvas.getContext('2d');
    if (!ctx) return { destroy: () => {} };

    // High-DPI scaling
    const size = resolveSize(canvas, 800, 360);
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size.w * dpr;
    canvas.height = size.h * dpr;
    ctx.scale(dpr, dpr);

    const width = size.w;
    const height = size.h;

    const padLeft = 65;
    const padRight = 25;
    const padTop = 35;
    const padBottom = 45;

    const plotW = width - padLeft - padRight;
    const plotH = height - padTop - padBottom;

    // Find min and max
    let minVal = 0;
    let maxVal = -Infinity;
    seriesList.forEach(s => {
      s.data.forEach(v => {
        if (v > maxVal) maxVal = v;
        if (v < minVal) minVal = v;
      });
    });

    if (maxVal === -Infinity || maxVal === 0) maxVal = 10;
    maxVal = maxVal * 1.1; // 10% head room

    let hoverIdx: number | null = null;

    function draw() {
      if (!ctx) return;
      ctx.clearRect(0, 0, width, height);

      // Background
      ctx.fillStyle = chartColor('--chart-bg', '#121212');
      ctx.fillRect(0, 0, width, height);

      // Title
      if (title) {
        ctx.fillStyle = chartColor('--chart-text', '#FFFFFF');
        ctx.font = 'bold 13px Inter, system-ui, sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText(title, padLeft, 22);
      }

      // Grid lines
      const yTicks = 5;
      ctx.strokeStyle = chartColor('--chart-grid', '#717171');
      ctx.lineWidth = 1;
      ctx.font = '11px Inter, system-ui, sans-serif';
      ctx.fillStyle = chartColor('--chart-text', '#A0A0A0');
      ctx.textAlign = 'right';

      for (let i = 0; i <= yTicks; i++) {
        const val = minVal + (maxVal - minVal) * (1 - i / yTicks);
        const y = padTop + (plotH / yTicks) * i;

        ctx.beginPath();
        ctx.moveTo(padLeft, y);
        ctx.lineTo(padLeft + plotW, y);
        ctx.stroke();

        ctx.fillText(`${val.toFixed(1)} ${unit}`, padLeft - 8, y + 4);
      }

      // X Axis Ticks
      const xTicks = 8;
      ctx.textAlign = 'center';
      const stepIdx = Math.max(1, Math.floor(labels.length / xTicks));
      for (let i = 0; i < labels.length; i += stepIdx) {
        const x = padLeft + (i / (labels.length - 1 || 1)) * plotW;
        ctx.fillText(labels[i] || '', x, height - 15);
      }

      // Draw series
      seriesList.forEach(s => {
        if (s.data.length === 0) return;
        ctx.beginPath();
        ctx.strokeStyle = s.color;
        ctx.lineWidth = s.name.includes('Total') ? 2.5 : 1.8;
        if (s.dash) ctx.setLineDash(s.dash);
        else ctx.setLineDash([]);

        const n = s.data.length;
        for (let i = 0; i < n; i++) {
          const x = padLeft + (i / (n - 1 || 1)) * plotW;
          const y = padTop + plotH - ((s.data[i] - minVal) / (maxVal - minVal || 1)) * plotH;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();

        // Area fill
        if (s.fill) {
          ctx.lineTo(padLeft + plotW, padTop + plotH);
          ctx.lineTo(padLeft, padTop + plotH);
          ctx.closePath();
          ctx.fillStyle = s.color + '22';
          ctx.fill();
        }
      });

      // Hover overlay
      if (hoverIdx !== null && hoverIdx >= 0 && hoverIdx < labels.length) {
        const hx = padLeft + (hoverIdx / (labels.length - 1 || 1)) * plotW;

        // Vertical cursor line
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = chartColor('--chart-text', '#CBD5E1');
        ctx.beginPath();
        ctx.moveTo(hx, padTop);
        ctx.lineTo(hx, padTop + plotH);
        ctx.stroke();
        ctx.setLineDash([]);

        // Tooltip box
        const tooltipX = hx > width - 180 ? hx - 170 : hx + 15;
        const tooltipY = padTop + 10;
        const boxW = 160;
        const boxH = 26 + seriesList.length * 18;

        ctx.fillStyle = 'rgba(15, 23, 42, 0.92)';
        ctx.strokeStyle = chartColor('--chart-grid', '#A0A0A0');
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.roundRect(tooltipX, tooltipY, boxW, boxH, 6);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = '#00B5E2';
        ctx.font = 'bold 11px Inter, system-ui, sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText(`🕒 ${labels[hoverIdx]}`, tooltipX + 8, tooltipY + 16);

        seriesList.forEach((s, idx) => {
          const val = s.data[hoverIdx!] !== undefined ? s.data[hoverIdx!].toFixed(2) : '--';
          ctx.fillStyle = s.color;
          ctx.font = '11px Inter, system-ui, sans-serif';
          ctx.fillText(`● ${s.name}: ${val} ${unit}`, tooltipX + 8, tooltipY + 34 + idx * 18);
        });
      }
    }

    draw();

    // Mouse events (throttled con rAF: evita re-dibujar 100x/seg con 6 series x 1000 pts)
    let hoverQueued = false;
    const onMouseMove = (e: MouseEvent) => {
      const b = canvas.getBoundingClientRect();
      const mx = e.clientX - b.left;
      let next: number | null = null;
      if (mx >= padLeft && mx <= padLeft + plotW) {
        const ratio = (mx - padLeft) / plotW;
        next = Math.round(ratio * (labels.length - 1));
      }
      if (next !== hoverIdx) {
        hoverIdx = next;
        if (!hoverQueued) {
          hoverQueued = true;
          requestAnimationFrame(() => { hoverQueued = false; draw(); });
        }
      }
    };

    const onMouseLeave = () => {
      hoverIdx = null;
      draw();
    };

    canvas.addEventListener('mousemove', onMouseMove);
    canvas.addEventListener('mouseleave', onMouseLeave);

    return {
      destroy: () => {
        canvas.removeEventListener('mousemove', onMouseMove);
        canvas.removeEventListener('mouseleave', onMouseLeave);
      }
    };
  }

  /**
   * Renders a pseudo-3D activity cloud using current, voltage and time as axes.
   * X = current, Y = voltage, Z = time (vertical), with cluster color coding.
   */
  static renderActivity3D(
    canvas: HTMLCanvasElement,
    events: Array<{ x: number; y: number; z: number; color: string; label: string; cluster: number; time: string }> = [],
    xLabel: string = 'Corriente [A]',
    yLabel: string = 'Tensión [V]',
    zLabel: string = 'Tiempo [min]'
  ): { destroy: () => void; setView: (view: 'xy' | 'yz' | 'zx') => void } {
    const ctx = canvas.getContext('2d');
    if (!ctx) return { destroy: () => {}, setView: (_view: 'xy' | 'yz' | 'zx') => {} };

    const size = resolveSize(canvas, 700, 420);
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size.w * dpr;
    canvas.height = size.h * dpr;
    ctx.scale(dpr, dpr);

    const width = size.w;
    const height = size.h;

    const maxX = Math.max(...events.map(e => Math.abs(e.x)), 1) * 1.15;
    const maxZ = Math.max(...events.map(e => e.z), 1) * 1.1;

    // Y axis (Tensión): auto-range fitted to the data min/max ± 20% margin of
    // the voltage span, so the real variation fills the cube instead of the
    // axis starting at 0 V.
    const yValues = events.map(e => e.y).filter(v => Number.isFinite(v));
    let yMin = yValues.length ? Math.min(...yValues) : 0;
    let yMax = yValues.length ? Math.max(...yValues) : 240;
    if (yMax - yMin < 1e-9) {
      // Constant voltage: symmetric margin around the single measured value
      const pad = Math.max(Math.abs(yMax) * 0.1, 5);
      yMin -= pad;
      yMax += pad;
    } else {
      const pad = (yMax - yMin) * 0.2;
      yMin -= pad;
      yMax += pad;
    }
    const ySpan = yMax - yMin;
    const normY = (y: number) => (y - yMin) / ySpan;

    const originX = width * 0.44;
    const originY = height * 0.84;
    const xLen = width * 0.38;
    const yLen = width * 0.22;
    const zLen = height * 0.64;

    const state = {
      hoverIndex: -1,
      hiddenClusters: new Set<number>(),
      yaw: -0.7,
      dragging: false,
      pointerX: 0,
      pointerY: 0
    };

    const clusterLegend = Array.from(new Set(events.map(e => e.cluster))).map(cluster => {
      const event = events.find(e => e.cluster === cluster);
      return {
        cluster,
        color: event?.color || '#00B5E2',
        label: event?.label || `Cluster ${cluster + 1}`
      };
    });

    // All inputs are normalized cube coordinates (0..1):
    //   x01 = corriente / maxX, y01 = normY(tensión), z01 = tiempo / maxZ
    function project3D(x01: number, y01: number, z01: number) {
      const yawCos = Math.cos(state.yaw);
      const yawSin = Math.sin(state.yaw);
      const rotatedX = x01 * yawCos - y01 * yawSin;
      const depth = x01 * yawSin + y01 * yawCos;
      const scale = 1.0 - depth * 0.18;
      const px = originX + (rotatedX * xLen) - (depth * yLen * 0.72);
      const py = originY - (z01 * zLen) - (depth * yLen * 0.38);
      return { x: px, y: py, scale };
    }

    function drawGridLine(x0: number, y0: number, z0: number, x1: number, y1: number, z1: number, color: string) {
      const a = project3D(x0, y0, z0);
      const b = project3D(x1, y1, z1);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    function drawAxisTicks() {
      const axisColor = chartColor('--chart-grid', '#A0A0A0');
      const textColor = chartColor('--chart-text', '#D0D0D0');
      ctx.strokeStyle = axisColor;
      ctx.fillStyle = textColor;
      ctx.lineWidth = 1;
      ctx.font = '10px Inter, system-ui, sans-serif';

      for (let i = 1; i <= 4; i++) {
        const ratio = i / 4;
        const x = project3D(ratio, 0, 0);
        ctx.beginPath();
        ctx.moveTo(x.x, x.y - 4);
        ctx.lineTo(x.x, x.y + 4);
        ctx.stroke();
        ctx.textAlign = 'center';
        ctx.fillText(`${(maxX * ratio).toFixed(1)} A`, x.x, x.y + 18);

        const y = project3D(0, ratio, 0);
        ctx.beginPath();
        ctx.moveTo(y.x - 4, y.y - 2);
        ctx.lineTo(y.x + 4, y.y + 2);
        ctx.stroke();
        ctx.textAlign = 'left';
        ctx.fillText(`${(yMin + ySpan * ratio).toFixed(1)} V`, y.x + 8, y.y + 3);

        const z = project3D(0, 0, ratio);
        ctx.beginPath();
        ctx.moveTo(z.x - 4, z.y);
        ctx.lineTo(z.x + 4, z.y);
        ctx.stroke();
        ctx.textAlign = 'right';
        ctx.fillText(`${(maxZ * ratio).toFixed(0)} min`, z.x - 8, z.y + 4);
      }

      // Voltage minimum label at the origin of the Y axis (auto-ranged)
      const yOrigin = project3D(0, 0, 0);
      ctx.textAlign = 'left';
      ctx.fillText(`${yMin.toFixed(1)} V`, yOrigin.x + 8, yOrigin.y + 3);
    }

    function drawLegend() {
      const legendX = width - 205;
      const legendY = 28;
      const itemHeight = 30;
      const boxW = 170;
      const boxH = Math.max(54, clusterLegend.length * itemHeight + 28);

      ctx.fillStyle = 'rgba(15, 23, 42, 0.88)';
      ctx.strokeStyle = '#717171';
      ctx.beginPath();
      ctx.roundRect(legendX, legendY, boxW, boxH, 10);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = chartColor('--chart-text', '#E2E8F0');
      ctx.font = 'bold 11px Inter, system-ui, sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText('Clústeres · mostrar/ocultar', legendX + 10, legendY + 16);

      clusterLegend.forEach((item, idx) => {
        const y = legendY + 38 + idx * itemHeight;
        const visible = !state.hiddenClusters.has(item.cluster);
        ctx.fillStyle = item.color;
        ctx.beginPath();
        ctx.arc(legendX + 12, y - 3, 4.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = visible ? chartColor('--chart-text', '#D0D0D0') : '#717171';
        ctx.font = '10px Inter, system-ui, sans-serif';
        ctx.fillText(item.label, legendX + 24, y + 1);

        ctx.fillStyle = visible ? '#414141' : '#121212';
        ctx.strokeStyle = visible ? item.color : '#717171';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.roundRect(legendX + boxW - 30, y - 13, 20, 20, 4);
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = visible ? chartColor('--chart-text', '#FFFFFF') : '#717171';
        ctx.font = 'bold 14px Inter, system-ui, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(visible ? '−' : '+', legendX + boxW - 20, y + 2);
        ctx.textAlign = 'left';
      });
    }

    function draw() {
      if (!ctx) return;
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = chartColor('--chart-bg', '#121212');
      ctx.fillRect(0, 0, width, height);

      ctx.fillStyle = chartColor('--chart-text', '#E2E8F0');
      ctx.font = 'bold 13px Inter, system-ui, sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText('Nube 3D de actividad eléctrica', 20, 24);
      drawLegend();

      const root = project3D(0, 0, 0);
      const xAxisEnd = project3D(1, 0, 0);
      const yAxisEnd = project3D(0, 1, 0);
      const zAxisEnd = project3D(0, 0, 1);

      ctx.strokeStyle = chartColor('--chart-grid', '#A0A0A0');
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      ctx.moveTo(root.x, root.y);
      ctx.lineTo(xAxisEnd.x, xAxisEnd.y);
      ctx.moveTo(root.x, root.y);
      ctx.lineTo(yAxisEnd.x, yAxisEnd.y);
      ctx.moveTo(root.x, root.y);
      ctx.lineTo(zAxisEnd.x, zAxisEnd.y);
      ctx.stroke();

      const cube = [
        [0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0],
        [0, 0, 1], [1, 0, 1], [0, 1, 1], [1, 1, 1]
      ];

      const edges = [
        [0,1],[0,2],[1,3],[2,3],[4,5],[4,6],[5,7],[6,7],[0,4],[1,5],[2,6],[3,7]
      ];
      edges.forEach(([a, b]) => {
        drawGridLine(cube[a][0], cube[a][1], cube[a][2], cube[b][0], cube[b][1], cube[b][2], 'rgba(100, 116, 139, 0.45)');
      });

      drawAxisTicks();

      for (let i = 1; i <= 4; i++) {
        const q = i / 4;
        drawGridLine(0, 0, q, 1, 0, q, 'rgba(148, 163, 184, 0.12)');
        drawGridLine(0, q, 0, 0, q, 1, 'rgba(148, 163, 184, 0.12)');
        drawGridLine(q, 0, 0, q, 1, 0, 'rgba(148, 163, 184, 0.12)');
      }

      ctx.fillStyle = chartColor('--chart-text', '#CBD5E1');
      ctx.font = '11px Inter, system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(xLabel, xAxisEnd.x, height - 16);
      ctx.fillText(yLabel, yAxisEnd.x + 10, yAxisEnd.y - 10);
      ctx.save();
      ctx.translate(zAxisEnd.x - 16, zAxisEnd.y - 18);
      ctx.rotate(-Math.PI / 2);
      ctx.fillText(zLabel, 0, 0);
      ctx.restore();

      const projectedPoints = events.map((ev, idx) => {
        const p = project3D(ev.x, ev.y, ev.z);
        return { ...ev, idx, px: p.x, py: p.y, scale: p.scale };
      }).filter(ev => !state.hiddenClusters.has(ev.cluster));

      projectedPoints.forEach(ev => {
        const active = state.hoverIndex === ev.idx;
        ctx.beginPath();
        ctx.arc(ev.px, ev.py, active ? 7.5 : 5.2 * ev.scale, 0, Math.PI * 2);
        ctx.fillStyle = ev.color;
        ctx.fill();
        ctx.strokeStyle = '#FFFFFF';
        ctx.lineWidth = active ? 1.8 : 0.8;
        ctx.stroke();
      });

      if (state.hoverIndex >= 0) {
        const p = projectedPoints.find(point => point.idx === state.hoverIndex);
        if (!p) return;
        const tooltipW = 220;
        const tooltipH = 62;
        const tx = Math.min(width - tooltipW - 12, Math.max(12, p.px + 16));
        const ty = Math.max(18, p.py - tooltipH - 10);

        ctx.fillStyle = 'rgba(15, 23, 42, 0.92)';
        ctx.strokeStyle = p.color;
        ctx.beginPath();
        ctx.roundRect(tx, ty, tooltipW, tooltipH, 8);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = '#FFFFFF';
        ctx.font = 'bold 11px Inter, system-ui, sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText(p.label, tx + 12, ty + 18);
        ctx.fillStyle = '#CBD5E1';
        ctx.font = '10px Inter, system-ui, sans-serif';
        ctx.fillText(`Corriente: ${p.x.toFixed(1)} A`, tx + 12, ty + 34);
        ctx.fillText(`Tensión: ${p.y.toFixed(1)} V • Tiempo: ${p.z.toFixed(0)} min`, tx + 12, ty + 48);
      }
    }

    const onMove = (e: MouseEvent) => {
      const b = canvas.getBoundingClientRect();
      const mx = e.clientX - b.left;
      const my = e.clientY - b.top;

      if (state.dragging) {
        state.yaw += (e.clientX - state.pointerX) * 0.01;
        state.pointerX = e.clientX;
        state.pointerY = e.clientY;
        draw();
        return;
      }

      let bestIndex = -1;
      let bestDist = Infinity;
      events.forEach((ev, idx) => {
        if (state.hiddenClusters.has(ev.cluster)) return;
        const p = project3D(ev.x, ev.y, ev.z);
        const dist = Math.hypot(mx - p.x, my - p.y);
        if (dist < 12 && dist < bestDist) {
          bestDist = dist;
          bestIndex = idx;
        }
      });

      state.hoverIndex = bestIndex;
      draw();
    };

    const onClick = (e: MouseEvent) => {
      const b = canvas.getBoundingClientRect();
      const mx = e.clientX - b.left;
      const my = e.clientY - b.top;
      const legendX = width - 205;
      const legendY = 28;
      const itemHeight = 30;
      const buttonX = legendX + 140;

      if (mx < buttonX || mx > buttonX + 30) return;
      const itemIndex = Math.floor((my - legendY - 25) / itemHeight);
      const item = clusterLegend[itemIndex];
      if (!item || my < legendY + 25 || my > legendY + 38 + clusterLegend.length * itemHeight) return;

      if (state.hiddenClusters.has(item.cluster)) state.hiddenClusters.delete(item.cluster);
      else state.hiddenClusters.add(item.cluster);
      state.hoverIndex = -1;
      draw();
    };

    const onPointerDown = (e: PointerEvent) => {
      state.dragging = true;
      state.pointerX = e.clientX;
      state.pointerY = e.clientY;
      state.hoverIndex = -1;
      canvas.setPointerCapture(e.pointerId);
      canvas.style.cursor = 'grabbing';
    };

    const onPointerUp = (e: PointerEvent) => {
      state.dragging = false;
      if (canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId);
      canvas.style.cursor = 'grab';
    };

    const onLeave = () => {
      state.hoverIndex = -1;
      draw();
    };

    canvas.addEventListener('mousemove', onMove);
    canvas.addEventListener('mouseleave', onLeave);
    canvas.addEventListener('click', onClick);
    canvas.addEventListener('pointerdown', onPointerDown);
    canvas.addEventListener('pointerup', onPointerUp);
    canvas.addEventListener('pointercancel', onPointerUp);
    canvas.style.cursor = 'grab';

    draw();

    const setView = (view: 'xy' | 'yz' | 'zx') => {
      if (view === 'yz') {
        state.yaw = Math.PI / 2;
      } else if (view === 'zx') {
        state.yaw = 0;
      } else {
        state.yaw = -0.7;
      }
      state.hoverIndex = -1;
      draw();
    };

    return {
      setView,
      destroy: () => {
        canvas.removeEventListener('mousemove', onMove);
        canvas.removeEventListener('mouseleave', onLeave);
        canvas.removeEventListener('click', onClick);
        canvas.removeEventListener('pointerdown', onPointerDown);
        canvas.removeEventListener('pointerup', onPointerUp);
        canvas.removeEventListener('pointercancel', onPointerUp);
        canvas.style.cursor = '';
      }
    };
  }

  /**
   * Renders 2D Feature Space Scatter Plot (Delta P vs Delta Q / Delta I vs THD)
   */
  static renderScatter(
    canvas: HTMLCanvasElement,
    events: Array<{ x: number; y: number; color: string; label: string; cluster: number; time: string }>,
    xLabel: string = 'Salto de Potencia Activa ΔP [kW]',
    yLabel: string = 'Distorsión Armónica THD [%]'
  ): { destroy: () => void } {
    const ctx = canvas.getContext('2d');
    if (!ctx) return { destroy: () => {} };

    const size = resolveSize(canvas, 600, 360);
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size.w * dpr;
    canvas.height = size.h * dpr;
    ctx.scale(dpr, dpr);

    const width = size.w;
    const height = size.h;

    const padLeft = 60;
    const padRight = 20;
    const padTop = 30;
    const padBottom = 50;

    const plotW = width - padLeft - padRight;
    const plotH = height - padTop - padBottom;

    let maxX = 5;
    let maxY = 5;
    events.forEach(e => {
      if (e.x > maxX) maxX = e.x;
      if (e.y > maxY) maxY = e.y;
    });
    maxX = maxX * 1.15;
    maxY = maxY * 1.15;

    let hoveredEvent: any = null;

    function draw() {
      if (!ctx) return;
      ctx.clearRect(0, 0, width, height);

      // Background
      ctx.fillStyle = chartColor('--chart-bg', '#121212');
      ctx.fillRect(0, 0, width, height);

      // Grid
      ctx.strokeStyle = '#717171';
      ctx.lineWidth = 1;
      ctx.fillStyle = chartColor('--chart-text', '#A0A0A0');
      ctx.font = '11px Inter, system-ui, sans-serif';

      // Y Ticks
      ctx.textAlign = 'right';
      for (let i = 0; i <= 5; i++) {
        const val = (maxY / 5) * (5 - i);
        const y = padTop + (plotH / 5) * i;
        ctx.beginPath();
        ctx.moveTo(padLeft, y);
        ctx.lineTo(padLeft + plotW, y);
        ctx.stroke();
        ctx.fillText(val.toFixed(1), padLeft - 8, y + 4);
      }

      // X Ticks
      ctx.textAlign = 'center';
      for (let i = 0; i <= 5; i++) {
        const val = (maxX / 5) * i;
        const x = padLeft + (plotW / 5) * i;
        ctx.beginPath();
        ctx.moveTo(x, padTop);
        ctx.lineTo(x, padTop + plotH);
        ctx.stroke();
        ctx.fillText(val.toFixed(1), x, height - padBottom + 18);
      }

      // Axis Labels
      ctx.fillStyle = chartColor('--chart-text', '#CBD5E1');
      ctx.font = 'bold 11px Inter, system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(xLabel, padLeft + plotW / 2, height - 12);

      ctx.save();
      ctx.translate(15, padTop + plotH / 2);
      ctx.rotate(-Math.PI / 2);
      ctx.fillText(yLabel, 0, 0);
      ctx.restore();

      // Render points
      events.forEach(e => {
        const px = padLeft + (e.x / maxX) * plotW;
        const py = padTop + plotH - (e.y / maxY) * plotH;

        ctx.beginPath();
        ctx.arc(px, py, 4.5, 0, Math.PI * 2);
        ctx.fillStyle = e.color + 'CC';
        ctx.fill();
        ctx.strokeStyle = '#FFFFFF';
        ctx.lineWidth = 0.7;
        ctx.stroke();
      });

      // Hover tooltip
      if (hoveredEvent) {
        const px = padLeft + (hoveredEvent.x / maxX) * plotW;
        const py = padTop + plotH - (hoveredEvent.y / maxY) * plotH;

        ctx.beginPath();
        ctx.arc(px, py, 8, 0, Math.PI * 2);
        ctx.strokeStyle = '#FFFFFF';
        ctx.lineWidth = 2.5;
        ctx.stroke();

        const bx = Math.min(width - 180, Math.max(padLeft + 10, px + 10));
        const by = Math.max(padTop + 10, py - 60);

        ctx.fillStyle = 'rgba(15, 23, 42, 0.95)';
        ctx.strokeStyle = hoveredEvent.color;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.roundRect(bx, by, 170, 65, 6);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = chartColor('--chart-text', '#FFFFFF');
        ctx.font = 'bold 11px Inter, system-ui, sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText(hoveredEvent.label, bx + 8, by + 16);

        ctx.fillStyle = chartColor('--chart-text', '#A0A0A0');
        ctx.font = '10px Inter, system-ui, sans-serif';
        ctx.fillText(`Hora: ${hoveredEvent.time}`, bx + 8, by + 32);
        ctx.fillText(`X: ${hoveredEvent.x.toFixed(2)} | Y: ${hoveredEvent.y.toFixed(2)}`, bx + 8, by + 48);
      }
    }

    draw();

    const onMouseMove = (e: MouseEvent) => {
      const b = canvas.getBoundingClientRect();
      const mx = e.clientX - b.left;
      const my = e.clientY - b.top;

      let found = null;
      for (const ev of events) {
        const px = padLeft + (ev.x / maxX) * plotW;
        const py = padTop + plotH - (ev.y / maxY) * plotH;
        const dist = Math.hypot(mx - px, my - py);
        if (dist <= 10) {
          found = ev;
          break;
        }
      }

      if (found !== hoveredEvent) {
        hoveredEvent = found;
        draw();
      }
    };

    const onMouseLeave = () => {
      hoveredEvent = null;
      draw();
    };

    canvas.addEventListener('mousemove', onMouseMove);
    canvas.addEventListener('mouseleave', onMouseLeave);

    return {
      destroy: () => {
        canvas.removeEventListener('mousemove', onMouseMove);
        canvas.removeEventListener('mouseleave', onMouseLeave);
      }
    };
  }

  /**
   * Renders Gantt / Operational Timeline Chart
   */
  static renderGanttTimeline(
    container: HTMLElement,
    machines: Array<{ id: number; name: string; color: string }>,
    intervals: Array<{ machine_id: number; start_time: string; end_time: string; duration_minutes: number; avg_power_kw: number; energy_kwh: number }>
  ) {
    container.innerHTML = '';
    const timelineCard = document.createElement('div');
    timelineCard.className = 'gantt-wrapper';

    // Time header: 00:00 to 24:00
    const header = document.createElement('div');
    header.className = 'gantt-header';
    header.innerHTML = `<div class="gantt-label-col">Equipo / Máquina</div><div class="gantt-track-header">`;
    for (let h = 0; h <= 24; h += 3) {
      header.innerHTML += `<span class="gantt-hour">${h.toString().padStart(2, '0')}:00</span>`;
    }
    header.innerHTML += `</div>`;
    timelineCard.appendChild(header);

    // Rows for each machine
    machines.forEach(m => {
      const row = document.createElement('div');
      row.className = 'gantt-row';

      const label = document.createElement('div');
      label.className = 'gantt-label';
      label.innerHTML = `<span class="gantt-dot" style="background:${m.color}"></span> ${m.name}`;
      row.appendChild(label);

      const track = document.createElement('div');
      track.className = 'gantt-track';

      const mIntervals = intervals.filter(it => Number(it.machine_id) === Number(m.id));
      if (mIntervals.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'gantt-empty';
        empty.textContent = 'Sin operación';
        track.appendChild(empty);
      }
      mIntervals.forEach(it => {
        const startParts = it.start_time.split(':').map(Number);
        const endParts = it.end_time.split(':').map(Number);

        const startSec = (startParts[0] || 0) * 3600 + (startParts[1] || 0) * 60 + (startParts[2] || 0);
        let endSec = (endParts[0] || 0) * 3600 + (endParts[1] || 0) * 60 + (endParts[2] || 0);
        if (endSec <= startSec) endSec = startSec + Math.max(300, it.duration_minutes * 60);

        const leftPct = (startSec / 86400) * 100;
        const widthPct = Math.max(0.4, ((endSec - startSec) / 86400) * 100);

        const block = document.createElement('div');
        block.className = 'gantt-block';
        block.style.left = `${leftPct}%`;
        block.style.width = `${widthPct}%`;
        block.style.backgroundColor = m.color;
        block.title = `${m.name}\nInicio: ${it.start_time}\nFin: ${it.end_time}\nDuración: ${it.duration_minutes} min\nPotencia: ${it.avg_power_kw} kW\nEnergía: ${it.energy_kwh} kWh`;

        track.appendChild(block);
      });

      row.appendChild(track);
      timelineCard.appendChild(row);
    });

    container.appendChild(timelineCard);
  }

  /**
   * Renders Operation Time Level Lines Chart
   * Each machine occupies its own horizontal level (nivel). A thin dashed
   * baseline spans the full 24h day and thick segments mark when the machine
   * was operating, labelling the start and end times of each block.
   */
  static renderOperationLevelLines(
    container: HTMLElement,
    machines: Array<{ id: number; name: string; color: string }>,
    intervals: Array<{ machine_id: number; start_time: string; end_time: string; duration_minutes: number; avg_power_kw: number; energy_kwh: number }>
  ) {
    container.innerHTML = '';
    const wrapper = document.createElement('div');
    wrapper.className = 'levels-wrapper';

    // Time header 00:00 to 24:00
    const header = document.createElement('div');
    header.className = 'levels-header';
    header.innerHTML = '<div class="levels-label-col">Equipo / Máquina</div><div class="levels-track-header">';
    for (let h = 0; h <= 24; h += 3) {
      header.innerHTML += `<span class="levels-hour">${h.toString().padStart(2, '0')}:00</span>`;
    }
    header.innerHTML += '</div>';
    wrapper.appendChild(header);

    const parseSec = (t: string): number => {
      const p = t.split(':').map(Number);
      return (p[0] || 0) * 3600 + (p[1] || 0) * 60 + (p[2] || 0);
    };

    const fmtTime = (sec: number): string => {
      sec = Math.max(0, Math.round(sec));
      const h = Math.floor(sec / 3600) % 24;
      const m = Math.floor((sec % 3600) / 60);
      return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
    };

    // Merge consecutive / overlapping intervals into readable operation blocks
    const buildBlocks = (machineId: number) => {
      const ranges = intervals
        .filter(it => Number(it.machine_id) === Number(machineId))
        .map(it => {
          const s = parseSec(it.start_time);
          let e = parseSec(it.end_time);
          if (e <= s) e = s + Math.max(300, it.duration_minutes * 60);
          return { s, e, raw: it };
        })
        .sort((a, b) => a.s - b.s);

      const blocks = [];
      ranges.forEach(r => {
        const last = blocks.length ? blocks[blocks.length - 1] : null;
        if (last && r.s <= last.e + 300) {
          last.e = Math.max(last.e, r.e);
          last.raw.push(r.raw);
        } else {
          blocks.push({ s: r.s, e: r.e, raw: [r.raw] });
        }
      });
      return blocks;
    };

    machines.forEach(m => {
      const row = document.createElement('div');
      row.className = 'levels-row';

      const label = document.createElement('div');
      label.className = 'levels-label';

      const labelMain = document.createElement('div');
      labelMain.className = 'levels-label-main';
      labelMain.innerHTML = `<span class="levels-dot" style="background:${m.color}"></span> ${m.name}`;
      label.appendChild(labelMain);

      const blocks = buildBlocks(m.id);
      const meta = document.createElement('div');
      meta.className = 'levels-meta';
      if (blocks.length) {
        const totalMin = blocks.reduce((acc, b) => acc + Math.round((b.e - b.s) / 60), 0);
        meta.textContent = `${blocks.length} bloque${blocks.length === 1 ? '' : 's'} · ${totalMin} min totales`;
      } else {
        meta.textContent = 'Sin operación detectada';
      }
      label.appendChild(meta);
      row.appendChild(label);

      const track = document.createElement('div');
      track.className = 'levels-track';

      // Full-day baseline (level line)
      const baseline = document.createElement('div');
      baseline.className = 'levels-baseline';
      track.appendChild(baseline);

      // 3-hour gridlines
      for (let h = 3; h < 24; h += 3) {
        const grid = document.createElement('div');
        grid.className = 'levels-gridline';
        grid.style.left = `${(h / 24) * 100}%`;
        track.appendChild(grid);
      }

      blocks.forEach(b => {
        const leftPct = (b.s / 86400) * 100;
        const widthPct = Math.max(0.4, ((b.e - b.s) / 86400) * 100);

        const seg = document.createElement('div');
        seg.className = 'levels-block';
        seg.style.left = `${leftPct}%`;
        seg.style.width = `${widthPct}%`;
        seg.style.backgroundColor = m.color;
        seg.title = `${m.name}\nInicio: ${fmtTime(b.s)}\nFin: ${fmtTime(b.e)}\nBloque: ${b.raw.length} intervalo(s) · ${Math.round((b.e - b.s) / 60)} min`;
        track.appendChild(seg);

        if (widthPct >= 5) {
          const startLbl = document.createElement('span');
          startLbl.className = 'levels-time-label levels-time-start';
          startLbl.textContent = `Inicio ${fmtTime(b.s)}`;
          startLbl.style.left = `${leftPct}%`;
          track.appendChild(startLbl);

          const endLbl = document.createElement('span');
          endLbl.className = 'levels-time-label levels-time-end';
          endLbl.textContent = `Fin ${fmtTime(b.e)}`;
          endLbl.style.left = `${leftPct + widthPct}%`;
          track.appendChild(endLbl);
        } else if (widthPct >= 2.5) {
          const midLbl = document.createElement('span');
          midLbl.className = 'levels-time-label levels-time-mid';
          midLbl.textContent = `${fmtTime(b.s)} → ${fmtTime(b.e)}`;
          midLbl.style.left = `${leftPct + widthPct / 2}%`;
          track.appendChild(midLbl);
        }
      });

      row.appendChild(track);
      wrapper.appendChild(row);
    });

    container.appendChild(wrapper);
  }

  /**
   * Renders Bar Chart (Harmonics, 24h Activity)
   */
  static renderBarChart(
    canvas: HTMLCanvasElement,
    labels: string[],
    data: number[],
    color: string = '#00B5E2',
    unit: string = '',
    title: string = ''
  ) {
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const size = resolveSize(canvas, 500, 320);
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size.w * dpr;
    canvas.height = size.h * dpr;
    ctx.scale(dpr, dpr);

    const width = size.w;
    const height = size.h;

    const padLeft = 45;
    const padRight = 15;
    const padTop = 30;
    const padBottom = 35;

    const plotW = width - padLeft - padRight;
    const plotH = height - padTop - padBottom;

    const maxVal = Math.max(...data, 1) * 1.15;

    ctx.fillStyle = chartColor('--chart-bg', '#121212');
    ctx.fillRect(0, 0, width, height);

    if (title) {
      ctx.fillStyle = chartColor('--chart-text', '#FFFFFF');
      ctx.font = 'bold 12px Inter, system-ui, sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText(title, padLeft, 18);
    }

    const barW = Math.max(4, (plotW / data.length) * 0.7);
    const gap = plotW / data.length;

    data.forEach((val, i) => {
      const x = padLeft + i * gap + (gap - barW) / 2;
      const h = (val / maxVal) * plotH;
      const y = padTop + plotH - h;

      // Bar
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.roundRect(x, y, barW, h, [3, 3, 0, 0]);
      ctx.fill();

      // Label
      ctx.fillStyle = chartColor('--chart-text', '#A0A0A0');
      ctx.font = '10px Inter, system-ui, sans-serif';
      ctx.textAlign = 'center';
      if (i % 2 === 0 || data.length <= 12) {
        ctx.fillText(labels[i] || '', x + barW / 2, height - 10);
      }
    });
  }

  /**
   * Renders Energy Share Donut Chart
   */
  static renderDonut(
    canvas: HTMLCanvasElement,
    slices: Array<{ name: string; value: number; color: string }>
  ) {
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const size = resolveSize(canvas, 400, 360);
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size.w * dpr;
    canvas.height = size.h * dpr;
    ctx.scale(dpr, dpr);

    const width = size.w;
    const height = size.h;
    const cx = width / 2;
    const cy = height / 2;
    const radius = Math.min(cx, cy) * 0.85;
    const innerRadius = radius * 0.6;

    const total = slices.reduce((acc, s) => acc + s.value, 0) || 1;

    let startAngle = -Math.PI / 2;
    slices.forEach(s => {
      const sliceAngle = (s.value / total) * Math.PI * 2;
      ctx.beginPath();
      ctx.arc(cx, cy, radius, startAngle, startAngle + sliceAngle);
      ctx.arc(cx, cy, innerRadius, startAngle + sliceAngle, startAngle, true);
      ctx.closePath();
      ctx.fillStyle = s.color;
      ctx.fill();
      ctx.strokeStyle = '#121212';
      ctx.lineWidth = 2;
      ctx.stroke();

      startAngle += sliceAngle;
    });

    // Center text
    ctx.fillStyle = chartColor('--chart-text', '#FFFFFF');
    ctx.font = 'bold 15px Inter, system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(`${total.toFixed(0)} kWh`, cx, cy + 5);
  }
}
