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
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = (rect.width || 800) * dpr;
    canvas.height = (rect.height || 350) * dpr;
    ctx.scale(dpr, dpr);

    const width = rect.width || 800;
    const height = rect.height || 350;

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

    // Mouse events
    const onMouseMove = (e            ) => {
      const b = canvas.getBoundingClientRect();
      const mx = e.clientX - b.left;
      if (mx >= padLeft && mx <= padLeft + plotW) {
        const ratio = (mx - padLeft) / plotW;
        hoverIdx = Math.round(ratio * (labels.length - 1));
        draw();
      } else {
        if (hoverIdx !== null) {
          hoverIdx = null;
          draw();
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

    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = (rect.width || 700) * dpr;
    canvas.height = (rect.height || 380) * dpr;
    ctx.scale(dpr, dpr);

    const width = rect.width || 700;
    const height = rect.height || 380;

    const maxX = Math.max(...events.map(e => Math.abs(e.x)), 1) * 1.15;
    const maxY = Math.max(...events.map(e => Math.abs(e.y)), 1) * 1.15;
    const maxZ = Math.max(...events.map(e => e.z), 1) * 1.1;

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

    function project3D(x        , y        , z        ) {
      const yawCos = Math.cos(state.yaw);
      const yawSin = Math.sin(state.yaw);
      const rotatedX = x * yawCos - y * yawSin;
      const depth = x * yawSin + y * yawCos;
      const scale = 1.0 - (depth / maxY) * 0.18;
      const px = originX + ((rotatedX / maxX) * xLen) - ((depth / maxY) * yLen * 0.72);
      const py = originY - ((z / maxZ) * zLen) - ((depth / maxY) * yLen * 0.38);
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
        const x = project3D(maxX * ratio, 0, 0);
        ctx.beginPath();
        ctx.moveTo(x.x, x.y - 4);
        ctx.lineTo(x.x, x.y + 4);
        ctx.stroke();
        ctx.textAlign = 'center';
        ctx.fillText(`${(maxX * ratio).toFixed(1)} A`, x.x, x.y + 18);

        const y = project3D(0, maxY * ratio, 0);
        ctx.beginPath();
        ctx.moveTo(y.x - 4, y.y - 2);
        ctx.lineTo(y.x + 4, y.y + 2);
        ctx.stroke();
        ctx.textAlign = 'left';
        ctx.fillText(`${(maxY * ratio).toFixed(0)} V`, y.x + 8, y.y + 3);

        const z = project3D(0, 0, maxZ * ratio);
        ctx.beginPath();
        ctx.moveTo(z.x - 4, z.y);
        ctx.lineTo(z.x + 4, z.y);
        ctx.stroke();
        ctx.textAlign = 'right';
        ctx.fillText(`${(maxZ * ratio).toFixed(0)} min`, z.x - 8, z.y + 4);
      }
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
      const xAxisEnd = project3D(maxX, 0, 0);
      const yAxisEnd = project3D(0, maxY, 0);
      const zAxisEnd = project3D(0, 0, maxZ);

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
        [0, 0, 0], [maxX, 0, 0], [0, maxY, 0], [maxX, maxY, 0],
        [0, 0, maxZ], [maxX, 0, maxZ], [0, maxY, maxZ], [maxX, maxY, maxZ]
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
        drawGridLine(0, 0, maxZ * q, maxX, 0, maxZ * q, 'rgba(148, 163, 184, 0.12)');
        drawGridLine(0, maxY * q, 0, 0, maxY * q, maxZ, 'rgba(148, 163, 184, 0.12)');
        drawGridLine(maxX * q, 0, 0, maxX * q, maxY, 0, 'rgba(148, 163, 184, 0.12)');
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

    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = (rect.width || 600) * dpr;
    canvas.height = (rect.height || 350) * dpr;
    ctx.scale(dpr, dpr);

    const width = rect.width || 600;
    const height = rect.height || 350;

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

    let hoveredEvent      = null;

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

      const mIntervals = intervals.filter(it => it.machine_id === m.id);
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
   * Renders Bar Chart (Harmonics, 24h Activity)
   */
  static renderBarChart(
    canvas                   ,
    labels          ,
    data          ,
    color         = '#00B5E2',
    unit         = '',
    title         = ''
  ) {
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = (rect.width || 400) * dpr;
    canvas.height = (rect.height || 250) * dpr;
    ctx.scale(dpr, dpr);

    const width = rect.width || 400;
    const height = rect.height || 250;

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
    canvas                   ,
    slices                                                       
  ) {
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = (rect.width || 250) * dpr;
    canvas.height = (rect.height || 250) * dpr;
    ctx.scale(dpr, dpr);

    const width = rect.width || 250;
    const height = rect.height || 250;
    const cx = width / 2;
    const cy = height / 2;
    const radius = Math.min(cx, cy) * 0.75;
    const innerRadius = radius * 0.58;

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
}

const api = new NILMApiService();


  // --- Application Controller ---
  /**
 * NILM Industrial Energy Analytics Dashboard Application
 * Main TypeScript Controller
 */





class NILMApp {
          currentDatasetId         = 'coop_gouge_v2_10_abril';
          datasets                = [];
          summary                      = null;
          timeseries                        = null;
          harmonics                       = null;
          analysis                            = null;
          activeTab            = 'overview';

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
    // Dataset select
    const dsSelect = document.getElementById('dataset-select')                     ;
    dsSelect?.addEventListener('change', (e) => {
      this.currentDatasetId = (e.target                     ).value;
      this.refreshData();
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
      this.populateDatasetSelector();

      if (this.datasets.length > 0) {
        this.currentDatasetId = this.datasets[0].id;
      }

      await this.refreshData();
    } catch (err     ) {
      console.error(err);
      this.showToast(`Error al cargar datos iniciales: ${err.message}`, 'error');
    } finally {
      this.showLoading(false);
    }
  }

          populateDatasetSelector() {
    const dsSelect = document.getElementById('dataset-select')                     ;
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

          async refreshData() {
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
        power_threshold: 1.0
      });

      this.updateApplianceTable();
      this.renderCurrentTabCharts();
      this.showToast(`Análisis NILM completado (${this.analysis.total_events_detected} eventos clasificados)`, 'success');
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
      const slices = this.analysis.machine_statistics.map(m => ({
        name: m.name,
        value: m.energy_kwh,
        color: m.color
      }));
      ChartEngine.renderDonut(canvasDonut, slices);
    }
  }

          renderMachinesTab() {
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

          renderTimelineTab() {
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
