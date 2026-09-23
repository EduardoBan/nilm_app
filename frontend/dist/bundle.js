/**
 * NILM Industrial Energy Analytics Dashboard - Compiled Bundle
 * Generated from TypeScript sources: src/app.ts, src/components/ChartEngine.ts, src/services/api.ts
 */
(function() {
  'use strict';

  // --- ChartEngine Component ---
  /**
 * ChartEngine: High Performance Canvas/SVG Charts for NILM Dashboard
 * Zero external dependencies, pure TypeScript implementation.
 */

                               
               
                 
                
                 
                  
 

function chartColor(variable        , fallback        )         {
  return getComputedStyle(document.documentElement).getPropertyValue(variable).trim() || fallback;
}

/**
 * Resolves the real available size for a canvas. Falls back to the parent
 * element width (even when the canvas rect reports 0 because the tab was
 * hidden at render time), and finally to the viewport, so charts always
 * stretch to the full width of the page.
 */
function resolveSize(
  canvas                   ,
  fallbackW        ,
  fallbackH        
)                           {
  const rect = canvas.getBoundingClientRect?.() || { width: 0, height: 0 };
  const parent = canvas.parentElement;
  const parentW = parent ? parent.clientWidth || parent.getBoundingClientRect().width || 0 : 0;
  const parentH = parent ? parent.clientHeight || parent.getBoundingClientRect().height || 0 : 0;
  const w = rect.width || parentW || window.innerWidth || fallbackW;
  const h = rect.height || parentH || fallbackH;
  return { w, h };
}

class ChartEngine {
  /**
   * Renders interactive multi-line / area time-series chart on HTML5 Canvas
   */
  static renderTimeSeries(
    canvas                   ,
    labels          ,
    seriesList                ,
    unit         = 'kW',
    title         = ''
  )                          {
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

    // Find min and max -> eje ajustado al rango medido +/-20% (más visual)
    // Antes minVal=0 fijo aplanaba las curvas (ej: 220-240V parecía plano de 0 a 260).
    let dataMin = Infinity;
    let dataMax = -Infinity;
    seriesList.forEach(s => {
      s.data.forEach(v => {
        if (Number.isFinite(v)) {
          if (v > dataMax) dataMax = v;
          if (v < dataMin) dataMin = v;
        }
      });
    });

    if (dataMax === -Infinity || dataMin === Infinity) {
      dataMin = 0;
      dataMax = 10;
    }
    let range = dataMax - dataMin;
    if (range <= 0) range = Math.abs(dataMax) * 0.2 || 1;
    let minVal = dataMin - range * 0.2;
    let maxVal = dataMax + range * 0.2;
    // Magnitudes siempre positivas (A, V, kW): no bajar de 0
    if (dataMin >= 0) minVal = Math.max(0, minVal);

    let hoverIdx                = null;

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
          const val = s.data[hoverIdx ] !== undefined ? s.data[hoverIdx ].toFixed(2) : '--';
          ctx.fillStyle = s.color;
          ctx.font = '11px Inter, system-ui, sans-serif';
          ctx.fillText(`● ${s.name}: ${val} ${unit}`, tooltipX + 8, tooltipY + 34 + idx * 18);
        });
      }
    }

    draw();

    // Mouse events (throttled con rAF: evita re-dibujar 100x/seg con 6 series x 1000 pts)
    let hoverQueued = false;
    const onMouseMove = (e            ) => {
      const b = canvas.getBoundingClientRect();
      const mx = e.clientX - b.left;
      let next                = null;
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
    canvas                   ,
    events                                                                                                          = [],
    xLabel         = 'Corriente [A]',
    yLabel         = 'Tensión [V]',
    zLabel         = 'Tiempo [min]'
  )                                                                       {
    const ctx = canvas.getContext('2d');
    if (!ctx) return { destroy: () => {}, setView: (_view                    ) => {} };

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
    const normY = (y        ) => (y - yMin) / ySpan;

    const originX = width * 0.44;
    const originY = height * 0.84;
    const xLen = width * 0.38;
    const yLen = width * 0.22;
    const zLen = height * 0.64;

    const state = {
      hoverIndex: -1,
      hiddenClusters: new Set        (),
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
    function project3D(x01        , y01        , z01        ) {
      const yawCos = Math.cos(state.yaw);
      const yawSin = Math.sin(state.yaw);
      const rotatedX = x01 * yawCos - y01 * yawSin;
      const depth = x01 * yawSin + y01 * yawCos;
      const scale = 1.0 - depth * 0.18;
      const px = originX + (rotatedX * xLen) - (depth * yLen * 0.72);
      const py = originY - (z01 * zLen) - (depth * yLen * 0.38);
      return { x: px, y: py, scale };
    }

    function drawGridLine(x0        , y0        , z0        , x1        , y1        , z1        , color        ) {
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
        // project3D espera coordenadas normalizadas del cubo (0..1):
        // x01 = corriente/maxX, y01 = normY(tension), z01 = tiempo/maxZ.
        // Sin normalizar, los puntos se proyectan a miles de pixeles fuera
        // del canvas y la nube 3D aparece vacia.
        const p = project3D(Math.abs(ev.x) / maxX, normY(ev.y), ev.z / maxZ);
        return { ...ev, idx, px: p.x, py: p.y, scale: p.scale };
      }).filter(ev => !state.hiddenClusters.has(ev.cluster));

      projectedPoints.forEach(ev => {
        const active = state.hoverIndex === ev.idx;
        ctx.beginPath();
        ctx.arc(ev.px, ev.py, active ? 7.5 : Math.max(2.2, 5.2 * ev.scale), 0, Math.PI * 2);
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

    const onMove = (e            ) => {
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
        // Misma normalizacion que en el dibujo (cube coords 0..1)
        const p = project3D(Math.abs(ev.x) / maxX, normY(ev.y), ev.z / maxZ);
        const dist = Math.hypot(mx - p.x, my - p.y);
        if (dist < 12 && dist < bestDist) {
          bestDist = dist;
          bestIndex = idx;
        }
      });

      state.hoverIndex = bestIndex;
      draw();
    };

    const onClick = (e            ) => {
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

    const onPointerDown = (e              ) => {
      state.dragging = true;
      state.pointerX = e.clientX;
      state.pointerY = e.clientY;
      state.hoverIndex = -1;
      canvas.setPointerCapture(e.pointerId);
      canvas.style.cursor = 'grabbing';
    };

    const onPointerUp = (e              ) => {
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

    const setView = (view                    ) => {
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
    canvas                   ,
    events                                                                                              ,
    xLabel         = 'Salto de Potencia Activa ΔP [kW]',
    yLabel         = 'Distorsión Armónica THD [%]'
  )                          {
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

    // Calcular rangos incluyendo negativos si existen
    let minX = 0, maxX = 5;
    let minY = 0, maxY = 5;
    events.forEach(e => {
      if (e.x < minX) minX = e.x;
      if (e.x > maxX) maxX = e.x;
      if (e.y < minY) minY = e.y;
      if (e.y > maxY) maxY = e.y;
    });
    // Margen 15% y asegurar que 0 esté visible si hay signos mixtos
    const rangeX = maxX - minX;
    const rangeY = maxY - minY;
    minX = minX - rangeX * 0.08;
    maxX = maxX + rangeX * 0.08;
    minY = minY - rangeY * 0.08;
    maxY = maxY + rangeY * 0.08;

    let hoveredEvent      = null;

    // Mapeo lineal generalizado (soporta negativos)
    function mapX(v        )         {
      return padLeft + ((v - minX) / (maxX - minX)) * plotW;
    }
    function mapY(v        )         {
      return padTop + plotH - ((v - minY) / (maxY - minY)) * plotH;
    }

    function niceStep(range        , ticks        )         {
      const raw = range / ticks;
      const mag = Math.pow(10, Math.floor(Math.log10(raw)));
      const norm = raw / mag;
      let step;
      if (norm <= 1.5) step = 1;
      else if (norm <= 3) step = 2;
      else if (norm <= 7) step = 5;
      else step = 10;
      return step * mag;
    }

    function draw() {
      if (!ctx) return;
      ctx.clearRect(0, 0, width, height);

      // Background
      ctx.fillStyle = chartColor('--chart-bg', '#121212');
      ctx.fillRect(0, 0, width, height);

      // --- Fondo del area de dibujo (encima del bg, debajo de puntos/grid) ---
      ctx.fillStyle = 'rgba(255,255,255,0.018)';
      ctx.fillRect(padLeft, padTop, plotW, plotH);

      // Grid y ticks
      ctx.strokeStyle = '#717171';
      ctx.lineWidth = 1;
      ctx.fillStyle = chartColor('--chart-text', '#A0A0A0');
      ctx.font = '11px Inter, system-ui, sans-serif';

      // Y Ticks (5 divisiones)
      const stepY = niceStep(maxY - minY, 5);
      ctx.textAlign = 'right';
      const startY = Math.ceil(minY / stepY) * stepY;
      for (let v = startY; v <= maxY + 1e-9; v += stepY) {
        if (v < minY) continue;
        const y = mapY(v);
        if (y < padTop - 0.5 || y > padTop + plotH + 0.5) continue;
        ctx.beginPath();
        ctx.moveTo(padLeft, y);
        ctx.lineTo(padLeft + plotW, y);
        ctx.stroke();
        ctx.fillText(v.toFixed(2), padLeft - 8, y + 4);
      }

      // X Ticks (5 divisiones)
      const stepX = niceStep(maxX - minX, 5);
      ctx.textAlign = 'center';
      const startX = Math.ceil(minX / stepX) * stepX;
      for (let v = startX; v <= maxX + 1e-9; v += stepX) {
        if (v < minX) continue;
        const x = mapX(v);
        if (x < padLeft - 0.5 || x > padLeft + plotW + 0.5) continue;
        ctx.beginPath();
        ctx.moveTo(x, padTop);
        ctx.lineTo(x, padTop + plotH);
        ctx.stroke();
        ctx.fillText(v.toFixed(2), x, height - padBottom + 18);
      }

      // Ejes de referencia en 0 (si está dentro del rango)
      if (minX < 0 && maxX > 0) {
        const x0 = mapX(0);
        ctx.strokeStyle = 'rgba(255,255,255,0.35)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(x0, padTop);
        ctx.lineTo(x0, padTop + plotH);
        ctx.stroke();
        ctx.lineWidth = 1;
      }
      if (minY < 0 && maxY > 0) {
        const y0 = mapY(0);
        ctx.strokeStyle = 'rgba(255,255,255,0.35)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(padLeft, y0);
        ctx.lineTo(padLeft + plotW, y0);
        ctx.stroke();
        ctx.lineWidth = 1;
      }

      // Bordes del grafico
      ctx.strokeStyle = 'rgba(255,255,255,0.18)';
      ctx.lineWidth = 1;
      ctx.strokeRect(padLeft + 0.5, padTop + 0.5, plotW, plotH);

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

      // --- CLIP al area del grafico: los puntos no invaden ejes/labels ---
      ctx.save();
      ctx.beginPath();
      ctx.rect(padLeft, padTop, plotW, plotH);
      ctx.clip();

      // Render points
      events.forEach(e => {
        const px = mapX(e.x);
        const py = mapY(e.y);
        // solo dibuja si está dentro (con pequeño margen para el stroke)
        if (px < padLeft - 8 || px > padLeft + plotW + 8) return;
        if (py < padTop - 8 || py > padTop + plotH + 8) return;

        ctx.beginPath();
        ctx.arc(px, py, 4.5, 0, Math.PI * 2);
        ctx.fillStyle = e.color + 'CC';
        ctx.fill();
        ctx.strokeStyle = '#FFFFFF';
        ctx.lineWidth = 0.7;
        ctx.stroke();
      });

      ctx.restore(); // fin clip

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

    const onMouseMove = (e            ) => {
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
    container             ,
    machines                                                    ,
    intervals                                                                                                                                         
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
    container             ,
    machines                                                    ,
    intervals                                                                                                                                         
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

    const parseSec = (t        )         => {
      const p = t.split(':').map(Number);
      return (p[0] || 0) * 3600 + (p[1] || 0) * 60 + (p[2] || 0);
    };

    const fmtTime = (sec        )         => {
      sec = Math.max(0, Math.round(sec));
      const h = Math.floor(sec / 3600) % 24;
      const m = Math.floor((sec % 3600) / 60);
      return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
    };

    // Merge consecutive / overlapping intervals into readable operation blocks
    const buildBlocks = (machineId        ) => {
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
    canvas                   ,
    labels          ,
    data          ,
    color         = '#00B5E2',
    unit         = '',
    title         = ''
  )                          {
    const ctx = canvas.getContext('2d');
    if (!ctx) return { destroy: () => {} };

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

    return { destroy: () => {} };
  }

  /**
   * Renders Grouped Bar Chart (STEP 1: harmonic signature ΔH3/ΔH5/ΔH7 per team)
   */
  static renderGroupedBars(
    canvas                   ,
    xLabels          ,
    series                                                        ,
    title         = ''
  )                          {
    const ctx = canvas.getContext('2d');
    if (!ctx) return { destroy: () => {} };

    const size = resolveSize(canvas, 640, 360);
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size.w * dpr;
    canvas.height = size.h * dpr;
    ctx.scale(dpr, dpr);

    const width = size.w;
    const height = size.h;

    const padLeft = 55;
    const padRight = 15;
    const padTop = 34;
    const padBottom = 60;
    const legendH = 22;

    const plotW = width - padLeft - padRight;
    const plotH = height - padTop - padBottom - legendH;

    let maxVal = 0.001;
    series.forEach(s => s.data.forEach(v => {
      if (Number.isFinite(v) && v > maxVal) maxVal = v;
    }));
    maxVal *= 1.18;

    function draw() {
      if (!ctx) return;
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = chartColor('--chart-bg', '#121212');
      ctx.fillRect(0, 0, width, height);

      if (title) {
        ctx.fillStyle = chartColor('--chart-text', '#FFFFFF');
        ctx.font = 'bold 12px Inter, system-ui, sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText(title, padLeft, 20);
      }

      // Grid
      ctx.strokeStyle = chartColor('--chart-grid', '#717171');
      ctx.lineWidth = 1;
      ctx.fillStyle = chartColor('--chart-text', '#A0A0A0');
      ctx.font = '10px Inter, system-ui, sans-serif';
      ctx.textAlign = 'right';
      for (let i = 0; i <= 4; i++) {
        const v = (maxVal * i) / 4;
        const y = padTop + plotH - (v / maxVal) * plotH;
        ctx.beginPath();
        ctx.moveTo(padLeft, y);
        ctx.lineTo(padLeft + plotW, y);
        ctx.stroke();
        ctx.fillText(v.toFixed(2), padLeft - 6, y + 3);
      }

      if (xLabels.length === 0 || series.length === 0) {
        ctx.fillStyle = chartColor('--chart-text', '#94A3B8');
        ctx.textAlign = 'center';
        ctx.fillText('Sin firmas armónicas (ejecuta el análisis NILM)', width / 2, padTop + plotH / 2);
        return;
      }

      const nGroups = xLabels.length;
      const nSeries = series.length;
      const groupW = plotW / nGroups;
      const barW = Math.max(4, Math.min(32, (groupW * 0.72) / nSeries));

      xLabels.forEach((lbl, gi) => {
        const gx = padLeft + gi * groupW;
        series.forEach((s, si) => {
          const v = Number(s.data[gi]) || 0;
          const h = (v / maxVal) * plotH;
          const totalBarsW = barW * nSeries;
          const x = gx + (groupW - totalBarsW) / 2 + si * barW;
          const y = padTop + plotH - h;
          ctx.fillStyle = s.color;
          ctx.beginPath();
          (ctx       ).roundRect
            ? (ctx       ).roundRect(x + 1, y, barW - 2, Math.max(1, h), [3, 3, 0, 0])
            : ctx.rect(x + 1, y, barW - 2, Math.max(1, h));
          ctx.fill();
        });
        // etiqueta grupo (nombre equipo truncado)
        ctx.fillStyle = chartColor('--chart-text', '#A0A0A0');
        ctx.font = '10px Inter, system-ui, sans-serif';
        ctx.textAlign = 'center';
        const short = lbl.length > 18 ? lbl.slice(0, 17) + '…' : lbl;
        ctx.fillText(short, gx + groupW / 2, padTop + plotH + 14);
      });

      // Leyenda series
      ctx.textAlign = 'left';
      let lx = padLeft;
      const ly = height - 14;
      series.forEach(s => {
        ctx.fillStyle = s.color;
        ctx.fillRect(lx, ly - 9, 12, 9);
        ctx.fillStyle = chartColor('--chart-text', '#CBD5E1');
        ctx.font = '11px Inter, system-ui, sans-serif';
        ctx.fillText(s.name, lx + 16, ly);
        lx += 16 + ctx.measureText(s.name).width + 22;
      });

      ctx.strokeStyle = 'rgba(255,255,255,0.18)';
      ctx.strokeRect(padLeft + 0.5, padTop + 0.5, plotW, plotH);
    }

    draw();
    return { destroy: () => {} };
  }

  /**
   * Renders Energy Share Donut Chart
   */
  static renderDonut(
    canvas                   ,
    slices                                                       
  )                          {
    const ctx = canvas.getContext('2d');
    if (!ctx) return { destroy: () => {} };

    const size = resolveSize(canvas, 720, 480);
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size.w * dpr;
    canvas.height = size.h * dpr;
    ctx.scale(dpr, dpr);

    const width = size.w;
    const height = size.h;
    const bgSep = chartColor('--chart-bg', '#121212');

    // Datos ordenados por consumo descendente (solo valores > 0)
    const data = slices
      .filter(s => s.value > 0)
      .map(s => ({ ...s, pct: 0 }))
      .sort((a, b) => b.value - a.value);
    const total = data.reduce((acc, s) => acc + s.value, 0);
    data.forEach(s => { s.pct = total > 0 ? (s.value / total) * 100 : 0; });

    // Layout: donut a la izquierda + leyenda a la derecha (o debajo si es estrecho)
    // leyenda SIEMPRE visible: si el canvas es muy estrecho, se dibuja debajo
    const minLegendW = 200;
    const legendW = width >= 520 ? Math.min(260, width * 0.42) : 0;
    const legendOnRight = legendW >= minLegendW;
    const padL = 20;
    const padR = 16;
    const donutAreaW = legendOnRight ? width - legendW - padL - padR : width - padL - padR;
    const legendX = legendOnRight ? (padL + donutAreaW + padR) : padL;
    const legendRowH = 32;
    const legendBlockH = data.length * legendRowH + 16;
    const legendY = legendOnRight
      ? Math.max(padL, (height - legendBlockH) / 2)
      : height - legendBlockH;

    const cx = legendOnRight ? padL + donutAreaW / 2 : width / 2;
    const cy = legendOnRight ? height / 2 : Math.max(80, (height - legendBlockH) * 0.45);
    const radius = Math.max(50, Math.min(donutAreaW, legendOnRight ? height : height - legendBlockH - 10) * 0.34);
    const innerRadius = radius * 0.60;

    let hoverIndex = -1;
    const cursor = { x: 0, y: 0 };

    // Angulos de cada sector (desde las 12 en punto)
    const angles                                        = [];
    {
      let a = -Math.PI / 2;
      data.forEach(s => {
        const span = total > 0 ? (s.value / total) * Math.PI * 2 : 0;
        angles.push({ start: a, end: a + span });
        a += span;
      });
    }

    function slicePath(idx        , explode        ) {
      const s = angles[idx];
      const mid = (s.start + s.end) / 2;
      const ox = Math.cos(mid) * explode;
      const oy = Math.sin(mid) * explode;
      ctx.beginPath();
      ctx.arc(cx + ox, cy + oy, radius, s.start, s.end);
      ctx.arc(cx + ox, cy + oy, innerRadius, s.end, s.start, true);
      ctx.closePath();
    }

    function hitTest(mx        , my        )         {
      const dist = Math.hypot(mx - cx, my - cy);
      if (dist < innerRadius - 2 || dist > radius + 10) return -1;
      let ang = Math.atan2(my - cy, mx - cx);
      if (ang < -Math.PI / 2) ang += Math.PI * 2;
      for (let i = 0; i < angles.length; i++) {
        if (ang >= angles[i].start - 1e-9 && ang <= angles[i].end + 1e-9) return i;
      }
      return -1;
    }

    function drawRoundRect(x        , y        , w        , h        , r        ) {
      // Manual: compatible con navegadores sin ctx.roundRect
      ctx.beginPath();
      ctx.moveTo(x + r, y);
      ctx.lineTo(x + w - r, y);
      ctx.arcTo(x + w, y, x + w, y + r, r);
      ctx.lineTo(x + w, y + h - r);
      ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
      ctx.lineTo(x + r, y + h);
      ctx.arcTo(x, y + h, x, y + h - r, r);
      ctx.lineTo(x, y + r);
      ctx.arcTo(x, y, x + r, y, r);
      ctx.closePath();
    }

    function truncate(text        , maxW        )         {
      if (ctx.measureText(text).width <= maxW) return text;
      let t = text;
      while (t.length > 1 && ctx.measureText(t + '…').width > maxW) {
        t = t.slice(0, -1);
      }
      return t + '…';
    }

    function draw() {
      if (!ctx) return;
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = chartColor('--chart-bg', '#121212');
      ctx.fillRect(0, 0, width, height);

      if (data.length === 0) {
        ctx.fillStyle = chartColor('--chart-text', '#94A3B8');
        ctx.font = '12px Inter, system-ui, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Sin datos de energía para esta medición', width / 2, height / 2);
        return;
      }

      // Sectores (el sector bajo el cursor se resalta desplazado)
      data.forEach((_s, i) => {
        slicePath(i, i === hoverIndex ? 8 : 0);
        ctx.fillStyle = data[i].color;
        ctx.fill();
        ctx.strokeStyle = bgSep;
        ctx.lineWidth = 2;
        ctx.stroke();
      });

      // Porcentajes sobre los sectores (solo si el sector >= 4%)
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.font = 'bold 11px Inter, system-ui, sans-serif';
      data.forEach((s, i) => {
        if (s.pct < 4) return;
        const mid = (angles[i].start + angles[i].end) / 2;
        const r = (radius + innerRadius) / 2;
        const x = cx + Math.cos(mid) * r;
        const y = cy + Math.sin(mid) * r;
        const label = `${s.pct.toFixed(0)}%`;
        ctx.lineWidth = 3;
        ctx.strokeStyle = 'rgba(0, 0, 0, 0.55)';
        ctx.strokeText(label, x, y);
        ctx.fillStyle = '#FFFFFF';
        ctx.fillText(label, x, y);
      });
      ctx.textBaseline = 'alphabetic';

      // Centro: referencia del total
      ctx.textAlign = 'center';
      ctx.fillStyle = chartColor('--chart-text', '#94A3B8');
      ctx.font = '11px Inter, system-ui, sans-serif';
      ctx.fillText('Consumo total', cx, cy - 16);
      ctx.fillStyle = chartColor('--chart-text', '#FFFFFF');
      ctx.font = 'bold 20px Inter, system-ui, sans-serif';
      ctx.fillText(`${total.toFixed(1)} kWh`, cx, cy + 10);

      // Leyenda: color + nombre + kWh + %
      ctx.font = '10.5px Inter, system-ui, sans-serif';
      ctx.textAlign = 'left';
      const rowH = legendRowH;
      const maxLabelW = legendW - 78;
      const valueX = legendX + legendW - 10;
      data.forEach((s, i) => {
        const y = legendY + i * rowH;
        const hovered = i === hoverIndex;

        // swatch de color
        ctx.fillStyle = s.color;
        drawRoundRect(legendX, y + 2, 12, 12, 3);
        ctx.fill();

        // nombre (truncado para que no tape al valor)
        ctx.fillStyle = hovered ? chartColor('--chart-text', '#FFFFFF') : chartColor('--chart-text', '#CBD5E1');
        ctx.font = hovered ? 'bold 10.5px Inter, system-ui, sans-serif' : '10.5px Inter, system-ui, sans-serif';
        const labelText = maxLabelW > 30 ? truncate(s.name, maxLabelW) : s.name.substring(0, 14);
        ctx.fillText(labelText, legendX + 18, y + 12);

        // kWh y % alineados a la derecha
        ctx.fillStyle = chartColor('--chart-text', '#94A3B8');
        ctx.font = '10px Inter, system-ui, sans-serif';
        ctx.textAlign = 'right';
        ctx.fillText(`${s.value.toFixed(1)} kWh · ${s.pct.toFixed(1)}%`, valueX, y + 12);
        ctx.textAlign = 'left';
      });

      // Tooltip del sector bajo el cursor
      if (hoverIndex >= 0) {
        const s = data[hoverIndex];
        const tipW = 230;
        const tipH = 66;
        const tx = Math.min(width - tipW - 8, Math.max(8, cursor.x + 14));
        const ty = Math.min(height - tipH - 8, Math.max(8, cursor.y - tipH - 10));

        ctx.fillStyle = 'rgba(15, 23, 42, 0.94)';
        ctx.strokeStyle = s.color;
        ctx.lineWidth = 1.5;
        drawRoundRect(tx, ty, tipW, tipH, 8);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = '#FFFFFF';
        ctx.font = 'bold 11px Inter, system-ui, sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText(truncate(s.name, tipW - 24), tx + 12, ty + 18);
        ctx.fillStyle = '#CBD5E1';
        ctx.font = '10px Inter, system-ui, sans-serif';
        ctx.fillText(`${s.value.toFixed(2)} kWh`, tx + 12, ty + 36);
        ctx.fillText(`${s.pct.toFixed(1)}% del consumo total`, tx + 12, ty + 52);
      }
    }

    const onMove = (e            ) => {
      const b = canvas.getBoundingClientRect();
      cursor.x = (e.clientX - b.left) * (width / (b.width || width));
      cursor.y = (e.clientY - b.top) * (height / (b.height || height));
      const idx = hitTest(cursor.x, cursor.y);
      if (idx !== hoverIndex || idx >= 0) {
        hoverIndex = idx;
        draw();
      }
    };

    const onLeave = () => {
      hoverIndex = -1;
      draw();
    };

    canvas.addEventListener('mousemove', onMove);
    canvas.addEventListener('mouseleave', onLeave);

    draw();

    return {
      destroy: () => {
        canvas.removeEventListener('mousemove', onMove);
        canvas.removeEventListener('mouseleave', onLeave);
      }
    };
  }
}


  // --- NILM API Service ---
  /**
 * API Service Client for NILM Python Server
 */


class NILMApiService {
          baseUrl        ;

  constructor(baseUrl         = '') {
    this.baseUrl = baseUrl || window.location.origin;
  }

  async getDatasets()                         {
    const res = await fetch(`${this.baseUrl}/api/datasets`);
    if (!res.ok) throw new Error(`Error fetching datasets: ${res.statusText}`);
    const json = await res.json();
    return json.data;
  }

  async getSummary(datasetId        )                        {
    const res = await fetch(`${this.baseUrl}/api/summary?dataset_id=${encodeURIComponent(datasetId)}`);
    if (!res.ok) throw new Error(`Error fetching summary: ${res.statusText}`);
    const json = await res.json();
    return json.data;
  }

  async getTimeseries(datasetId        , maxPoints         = 1200)                          {
    const res = await fetch(`${this.baseUrl}/api/timeseries?dataset_id=${encodeURIComponent(datasetId)}&max_points=${maxPoints}`);
    if (!res.ok) throw new Error(`Error fetching timeseries: ${res.statusText}`);
    const json = await res.json();
    return json.data;
  }

  async getHarmonics(datasetId        )                         {
    const res = await fetch(`${this.baseUrl}/api/harmonics?dataset_id=${encodeURIComponent(datasetId)}`);
    if (!res.ok) throw new Error(`Error fetching harmonics: ${res.statusText}`);
    const json = await res.json();
    return json.data;
  }

  /** MEJORA #21: diagnóstico de calidad energética (EN 50160 / IEC) */
  async getPowerQuality(datasetId        , maxPoints         = 600)                              {
    const res = await fetch(`${this.baseUrl}/api/powerquality?dataset_id=${encodeURIComponent(datasetId)}&max_points=${maxPoints}`);
    if (!res.ok) throw new Error(`Error fetching power quality: ${res.statusText}`);
    const json = await res.json();
    return json.data;
  }

  async uploadDataset(file      )                       {
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

  async runAnalysis(params                )                              {
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
  async getLabels(datasetId        )                                  {
    const res = await fetch(`${this.baseUrl}/api/labels?dataset_id=${encodeURIComponent(datasetId)}`);
    if (!res.ok) throw new Error(`Error fetching labels: ${res.statusText}`);
    const json = await res.json();
    return json.data.labels || {};
  }

  /** Saves (or clears when name is empty) a custom appliance label */
  async saveLabel(datasetId        , clusterId        , name        )                                  {
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
  async clearLabels(datasetId        )                                  {
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

const api = new NILMApiService();


  // --- Application Controller ---
  /**
 * NILM Industrial Energy Analytics Dashboard Application
 * Main TypeScript Controller
 */





/** Escapa HTML para evitar XSS via nombres Ground-Truth personalizados. */
function escapeHtml(s        )         {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** Formatea un número opcionalmente NaN/undefined para tablas del benchmark. */
function fmtNum(v        , digits        )         {
  return Number.isFinite(v) ? v.toFixed(digits) : '--';
}

class NILMApp {
          currentDatasetId         = '';
          datasets                = [];
          summary                      = null;
          timeseries                        = null;
          harmonics                       = null;
          analysis                            = null;
          activeTab            = 'overview';
  /* Opción A: modelado multi-estado FHMM (persistido entre sesiones) */
          useFhmm          = (localStorage.getItem('nilm-fhmm') ?? 'on') !== 'off';

  /* MEJORA #9/#10: benchmark de algoritmos + estabilidad de umbrales */
          benchmark                         = null;

  /* MEJORA #21: diagnóstico de calidad energética */
          powerQuality                            = null;

          chartCleanups                    = [];

  async init() {
    this.setupTheme();
    this.setupEventListeners();
    await this.loadInitialData();
  }

          setupTheme() {
    const themeSelect = document.getElementById('theme-select')                     ;
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

          setupEventListeners() {
    // Dataset dropdown selector
    const selectDs = document.getElementById('select-dataset')                     ;
    selectDs?.addEventListener('change', async () => {
      if (selectDs.value && selectDs.value !== this.currentDatasetId) {
        this.currentDatasetId = selectDs.value;
        const found = this.datasets.find(d => d.id === this.currentDatasetId);
        if (found) this.updateFileLabel(found.filename);
        await this.refreshData();
      }
    });

    // File picker (upload a measurement file)
    const fileInput = document.getElementById('dataset-file')                    ;
    fileInput?.addEventListener('change', () => {
      this.handleFileSelected(fileInput);
    });

    // Run Analysis Button
    const btnRun = document.getElementById('btn-run-analysis');
    btnRun?.addEventListener('click', () => {
      this.runNILMAnalysis();
    });

    // Sliders
    const clusterSlider = document.getElementById('slider-clusters')                    ;
    const clusterVal = document.getElementById('val-clusters');
    clusterSlider?.addEventListener('input', () => {
      if (clusterVal) clusterVal.textContent = clusterSlider.value;
    });

    const thresholdSlider = document.getElementById('slider-threshold')                    ;
    const thresholdVal = document.getElementById('val-threshold');
    thresholdSlider?.addEventListener('input', () => {
      if (thresholdVal) thresholdVal.textContent = `${thresholdSlider.value} A`;
    });

    // Opción A: Multi-state FHMM modeling toggle
    const fhmmCheck = document.getElementById('chk-fhmm')                    ;
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
        } catch (err     ) {
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
        const target = (e.currentTarget               ).dataset.tab             ;
        this.switchTab(target);
      });
    });

    // Window resize handler
    window.addEventListener('resize', () => {
      this.renderCurrentTabCharts();
    });
  }

          switchTab(tab           ) {
    this.activeTab = tab;
    document.querySelectorAll('.nav-tab').forEach(b => {
      if ((b               ).dataset.tab === tab) b.classList.add('active');
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

          async loadInitialData() {
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
    } catch (err     ) {
      console.error(err);
      this.updateFileLabel(null);
      this.showToast(`Error al cargar datos iniciales: ${err.message}`, 'error');
    } finally {
      this.showLoading(false);
    }
  }

          updateDatasetSelect() {
    const selectDs = document.getElementById('select-dataset')                     ;
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

          async handleFileSelected(input                  ) {
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
    } catch (err     ) {
      console.error(err);
      this.updateFileLabel(null);
      this.showToast(`Error al cargar archivo: ${err.message}`, 'error');
    } finally {
      this.showLoading(false);
      input.value = '';
    }
  }

          updateFileLabel(name               , uploading          = false) {
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

          async refreshData() {
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
      const reportLink = document.getElementById('report-link-btn')                     ;
      if (reportLink && this.currentDatasetId) {
        reportLink.href = `/api/report?dataset_id=${encodeURIComponent(this.currentDatasetId)}`;
      }

      await this.runNILMAnalysis();
    } catch (err     ) {
      console.error(err);
      this.showToast(`Error cargando dataset: ${err.message}`, 'error');
    } finally {
      this.showLoading(false);
    }
  }

          async runNILMAnalysis() {
    const clusterSlider = document.getElementById('slider-clusters')                    ;
    const thresholdSlider = document.getElementById('slider-threshold')                    ;
    const algoSelect = document.getElementById('select-algo')                     ;

    const n_clusters = clusterSlider ? parseInt(clusterSlider.value, 10) : 4;
    const current_threshold = thresholdSlider ? parseFloat(thresholdSlider.value) : 2.0;
    const algorithm = (algoSelect ? algoSelect.value : 'kmeans')       ;

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
      const warn = (this.analysis       ).warning;
      if (warn) this.showToast(warn, 'info');
      this.showToast(`Análisis NILM completado (${this.analysis.total_events_detected} eventos · ${this.analysis.timeline_intervals.length} intervalos Gantt · modo ${mode})`, 'success');
    } catch (err     ) {
      console.error(err);
      this.showToast(`Error ejecutando análisis NILM: ${err.message}`, 'error');
    } finally {
      this.showLoading(false);
    }
  }

          updateKPIs() {
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

          updateApplianceTable() {
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
    tbody.querySelectorAll                   ('button.edit-btn').forEach(btn => {
      btn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        const id = parseInt(btn.dataset['edit'] || '0', 10);
        const nameSpan = tbody.querySelector             (`.editable-name[data-machine="${id}"]`);
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
          startRename(machineId        , host             ) {
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
    const finish = (commit         ) => {
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
        .catch((err     ) => {
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
          applyNameOverride(machineId        , newName        ) {
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

          clearChartCleanups() {
    this.chartCleanups.forEach(fn => fn());
    this.chartCleanups = [];
  }

          renderCurrentTabCharts() {
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

          renderOverviewCharts() {
    if (!this.analysis || !this.timeseries) return;

    // 1. Total & Disaggregated Curves Chart
    const canvasMain = document.getElementById('chart-main-power')                     ;
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
    const canvasDonut = document.getElementById('chart-energy-donut')                     ;
    if (canvasDonut) {
      const machineSlices = this.analysis.machine_statistics.map(m => ({
        name: m.name,
        value: m.energy_kwh,
        color: m.color
      }));
      const machineEnergy = machineSlices.reduce((a, s) => a + s.value, 0);

      // Energia total de la red (campo del backend) o derivada de los shares
      let totalEnergy = (this.analysis       ).total_energy_kwh                      ;
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

          renderMachinesTab() {
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
    container.querySelectorAll                   ('button.edit-btn').forEach(btn => {
      btn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        const id = parseInt(btn.dataset['edit'] || '0', 10);
        const nameSpan = container.querySelector             (`.editable-name[data-machine="${id}"]`);
        if (nameSpan) this.startRename(id, nameSpan);
      });
    });
  }

  /** MEJORA #16: resumen del coste energetico (tarifa, totales, periodos, turnos) */
          renderCostSummary() {
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
          renderMachineStatesBlock(m     )         {
    if (!m.states || m.states.length <= 1) return '';
    const maxMin = Math.max(1, ...m.states.map((s     ) => s.minutes || 0));
    const rows = m.states
      .filter((s     ) => s.kw > 0)
      .map((s     ) => `
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

          renderTimelineTab() {
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
      machine_id: Number((iv       ).machine_id),
      machine_name: escapeHtml(iv.machine_name || ''),
      // El backend FHMM envia `state`; el normal no tiene estado.
      state_name: iv.state_name || (iv       ).state || undefined
    }));

    if (intervals.length === 0) {
      const warn = (this.analysis       ).warning;
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

    ChartEngine.renderGanttTimeline(container, machines, intervals       );

    const levelsContainer = document.getElementById('operation-levels-container');
    if (levelsContainer) {
      ChartEngine.renderOperationLevelLines(levelsContainer, machines, intervals       );
    }
  }

          renderFeatures3DTab() {
    if (!this.analysis) return;

    const canvas3D = document.getElementById('chart-activity-3d')                     ;
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

      document.querySelectorAll                   ('[data-3d-view]').forEach(button => {
        const onViewClick = () => {
          document.querySelectorAll('[data-3d-view]').forEach(item => item.classList.remove('active'));
          button.classList.add('active');
          res.setView(button.dataset['3dView']                      );
        };
        button.addEventListener('click', onViewClick);
        this.chartCleanups.push(() => button.removeEventListener('click', onViewClick));
      });
    }
  }

          renderFeatures2DTab() {
    if (!this.analysis) return;

    const canvasP_Q = document.getElementById('chart-scatter-pq')                     ;
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

    const canvasI_THD = document.getElementById('chart-scatter-ithd')                     ;
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

          renderHourlyTab() {
    if (!this.analysis) return;
    const canvas = document.getElementById('chart-hourly-activity')                     ;
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

          renderQualityTab() {
    if (!this.timeseries || !this.harmonics) return;

    // 1. 3-Phase Currents
    const canvasCurrent = document.getElementById('chart-phase-currents')                     ;
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
    const canvasVoltage = document.getElementById('chart-phase-voltages')                     ;
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
    const canvasHarmonics = document.getElementById('chart-harmonics-spectrum')                     ;
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
          renderHarmonicTab() {
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

    const canvasSig = document.getElementById('chart-harmonic-signature')                     ;
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

    const canvasHarm = document.getElementById('chart-scatter-harm')                     ;
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
          renderFhmmTab() {
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

    const canvas = document.getElementById('chart-fhmm-viterbi')                     ;
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
        canvas, this.analysis.timestamps, seriesList       , 'kW',
        'Desagregación FHMM (descenso por eventos — hmmlearn no disponible o podado)'
      );
      this.chartCleanups.push(res.destroy);
    }
  }

  /** MEJORA #2: priors horarios — perfil de arranque por equipo y comparativa minutos ON sin/con priors */
          renderFhmmHourlyCharts()       {
    const fx = this.analysis?.fhmm_exact;
    if (!fx) return;
    const palette = ["#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899", "#06B6D4", "#84CC16"];

    // Grafico 1: perfil horario del prior de arranque por equipo (mejora #2)
    const c1 = document.getElementById("chart-fhmm-priors")                            ;
    if (c1 && fx.priors_used && fx.hourly_priors) {
      const ctx = c1.getContext("2d");
      if (ctx) {
        const W = c1.width, H = c1.height;
        ctx.clearRect(0, 0, W, H);
        const padL = 46, padR = 12, padT = 16, padB = 24;
        const keys = Object.keys(fx.hourly_priors);
        const vals = keys.map(k => fx.hourly_priors [k]);
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
          const arr = fx.hourly_priors [k];
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
    const c2 = document.getElementById("chart-fhmm-compare")                            ;
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

          renderValidationTab() {
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

    const canvas = document.getElementById('chart-validation-f1')                     ;
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
          renderStandbyTab()       {
    const sb = this.analysis?.standby ?? null;
    // MEJORA #14: el bloque de anomalias vive en la misma pestana.
    this.renderAnomalyBlock();
    const kpiBox = document.getElementById('standby-kpis');
    const methodBox = document.getElementById('standby-method');
    const empty = '<div class="empty-state"><p>Ejecuta el análisis NILM para cuantificar el consumo fantasma (residuo no atribuido).</p></div>';
    if (!sb || !sb.duration_baseline_kw || sb.duration_baseline_kw.length < 2) {
      if (kpiBox) kpiBox.innerHTML = empty;
      if (methodBox) methodBox.innerHTML = '';
      const c1 = document.getElementById('chart-standby-duration')                            ;
      const c2 = document.getElementById('chart-standby-hist')                            ;
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

    const cDur = document.getElementById('chart-standby-duration')                            ;
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
    const cHist = document.getElementById('chart-standby-hist')                            ;
    if (cHist && sb.hist.counts.length > 0) {
      const labels = sb.hist.edges.slice(0, -1).map(e => e.toFixed(1));
      const res = ChartEngine.renderBarChart(cHist, labels, sb.hist.counts, '#8B5CF6', '', 'Distribución del standby (kW)');
      this.chartCleanups.push(res.destroy);
    }
  }

  /** MEJORA #14: anomalías sobre el residuo — MAE móvil vs umbral MAD. */
          renderAnomalyBlock()       {
    const ra = this.analysis?.residual_anomalies ?? null;
    const kpiBox = document.getElementById('anomaly-kpis');
    const eventsBox = document.getElementById('anomaly-events');
    const methodBox = document.getElementById('anomaly-method');
    const canvas = document.getElementById('chart-anomaly-mae')                            ;
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

          async runBenchmark() {
    if (!this.currentDatasetId) {
      this.showToast('Carga primero una medición para ejecutar el benchmark.', 'error');
      return;
    }

    const clusterSlider = document.getElementById('slider-clusters')                    ;
    const thresholdSlider = document.getElementById('slider-threshold')                    ;
    const nClusters = clusterSlider ? parseInt(clusterSlider.value, 10) : 4;
    const currentThr = thresholdSlider ? parseFloat(thresholdSlider.value) : 2.0;
    const powerThr = 1.0;

    const configs                                                                                                                          = [
      { label: `K-Means (nominal)`, kind: 'algoritmo', algorithm: 'kmeans', cur: currentThr, pow: powerThr, fhmm: false },
      { label: `GMM (nominal)`, kind: 'algoritmo', algorithm: 'gmm', cur: currentThr, pow: powerThr, fhmm: false },
      { label: `DBSCAN (nominal)`, kind: 'algoritmo', algorithm: 'dbscan', cur: currentThr, pow: powerThr, fhmm: false },
      { label: `FHMM (K-Means + FHMM)`, kind: 'algoritmo', algorithm: 'kmeans', cur: currentThr, pow: powerThr, fhmm: this.useFhmm },
      { label: `Umbral −20% (${(currentThr * 0.8).toFixed(2)} A)`, kind: 'estabilidad', algorithm: 'kmeans', cur: currentThr * 0.8, pow: powerThr * 0.8, fhmm: false },
      { label: `Umbral +20% (${(currentThr * 1.2).toFixed(2)} A)`, kind: 'estabilidad', algorithm: 'kmeans', cur: currentThr * 1.2, pow: powerThr * 1.2, fhmm: false }
    ];

    const progress = document.getElementById('benchmark-progress');
    const btn = document.getElementById('btn-run-benchmark')                            ;
    if (btn) btn.disabled = true;
    if (progress) progress.innerHTML = '<p>⏳ Ejecutando benchmark… 0 / ' + configs.length + '</p>';

    try {
    const rows                 = [];
    for (let i = 0; i < configs.length; i++) {
      const c = configs[i];
      if (progress) progress.innerHTML = `<p>⏳ Ejecutando benchmark… ${i + 1} / ${configs.length} — <strong>${escapeHtml(c.label)}</strong></p>`;
      const t0 = performance.now();
      try {
        const res = await api.runAnalysis({
          dataset_id: this.currentDatasetId,
          n_clusters: nClusters,
          algorithm: c.algorithm       ,
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
      } catch (err     ) {
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
    const mean = (a          ) => a.length ? a.reduce((s, v) => s + v, 0) / a.length : NaN;
    const std = (a          ) => a.length > 1 ? Math.sqrt(mean(a.map(v => (v - mean(a)) ** 2))) : 0;

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
    } catch (err     ) {
      console.error('Error fatal en benchmark:', err);
      if (progress) progress.innerHTML = `<p>❌ Error en el benchmark: ${escapeHtml(String(err?.message ?? err))}</p>`;
      if (btn) btn.disabled = false;
      this.showToast(`Error en el benchmark: ${err?.message ?? err}`, 'error');
    }
  }

  /* ================= MEJORA #21: Calidad Energética ================= */

          renderPowerQualityTab() {
    const checksEl = document.getElementById('pq-checks');
    const eventsEl = document.getElementById('pq-events-table');
    const canvasV = document.getElementById('chart-pq-voltage')                            ;
    const canvasTHD = document.getElementById('chart-pq-thdu')                            ;
    const canvasN = document.getElementById('chart-pq-neutral')                            ;

    if (!this.powerQuality) {
      if (checksEl) {
        checksEl.innerHTML = '<div class="empty-state"><p>Calidad energética no disponible para esta medición (el debe incluir columnas de tensión, THD y neutro).</p></div>';
      }
      return;
    }
    const pq = this.powerQuality;

    // Tarjetas de cumplimiento (ok/warn/bad)
    if (checksEl) {
      const icon                         = { ok: '✅', warn: '⚠️', bad: '❌' };
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
      const series        = [
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
      const series        = [
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

          renderBenchmarkTab() {
    const progress = document.getElementById('benchmark-progress');
    const summary = document.getElementById('benchmark-summary');
    const tableEl = document.getElementById('benchmark-table');
    const canvas = document.getElementById('chart-benchmark-f1')                            ;

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

          showLoading(show         ) {
    const loader = document.getElementById('loading-overlay');
    if (loader) {
      if (show) loader.classList.add('visible');
      else loader.classList.remove('visible');
    }
  }

          showToast(msg        , type                               = 'info') {
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

})();
