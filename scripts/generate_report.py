"""Generate a Spanish NILM analysis report with real data, Ground Truth labels, and charts."""
from pathlib import Path
import sys
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.data_manager import DataManager
from backend.nilm_engine import NILMEngine

OUTPUT = ROOT / "Informe_NILM_Inti.pdf"
DATASET = "coop_gouge_v2_10_abril"
INTI = {
    "blue": "#003087",
    "cyan": "#00B5E2",
    "coral": "#FF6C75",
    "orange": "#FCB04C",
    "lime": "#D3EA34",
    "turquoise": "#44D2C8",
    "violet": "#5C46F9",
    "ink": "#121212",
    "gray": "#717171",
    "light": "#D0D0D0",
}
CLUSTER_COLORS = [INTI["cyan"], INTI["turquoise"], INTI["orange"], INTI["coral"], INTI["violet"], INTI["lime"]]

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.titleweight": "bold",
    "axes.edgecolor": INTI["gray"],
    "axes.labelcolor": INTI["ink"],
    "xtick.color": INTI["gray"],
    "ytick.color": INTI["gray"],
})


def page(title, subtitle=None):
    fig = plt.figure(figsize=(11.69, 8.27), facecolor="white")
    fig.subplots_adjust(left=0.08, right=0.94, top=0.86, bottom=0.1)
    fig.text(0.08, 0.93, title, fontsize=21, color=INTI["blue"], weight="bold")
    if subtitle:
        fig.text(0.08, 0.895, subtitle, fontsize=10, color=INTI["gray"])
    fig.text(0.08, 0.035, "NILM Energy Analytics | Informe generado desde la aplicación", fontsize=7, color=INTI["gray"])
    return fig


def add_wrapped(fig, text, x, y, width=105, fontsize=10, line_height=0.031, color=INTI["ink"]):
    lines = []
    for paragraph in text.split("\n"):
        lines.extend(textwrap.wrap(paragraph, width=width) or [""])
    for index, line in enumerate(lines):
        fig.text(x, y - index * line_height, line, fontsize=fontsize, color=color, va="top")
    return y - len(lines) * line_height


def generate_report(dataset_id: str = "coop_gouge_v2_10_abril",
                    n_clusters: int = 4,
                    algorithm: str = "kmeans",
                    output_path: Path = None,
                    labels: dict = None) -> Path:
    """
    Generates a multi-page PDF report with real dataset signals, Ground-Truth
    appliance labels, operational metrics, and 2D/3D feature spaces.
    """
    if output_path is None:
        output_path = OUTPUT
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    dm = DataManager()
    engine = NILMEngine(dm)

    if labels is None:
        labels = dm.get_labels(dataset_id)

    df = dm.load_dataset(dataset_id)
    summary = dm.get_summary_stats(dataset_id)
    df_work, events = engine.detect_events(df, current_threshold=2.0, power_threshold=1.0)
    clustered, cluster_info = engine.cluster_appliances(
        events, n_clusters=n_clusters, algorithm=algorithm, custom_labels=labels
    )
    disagg, baseline, timeline, machine_stats = engine.disaggregate_load(df_work, clustered, cluster_info)

    with PdfPages(output_path) as pdf:
        # 1. Executive summary
        fig = page("Informe de análisis NILM", f"Desagregación no intrusiva de cargas eléctricas | Medición: {dataset_id}")
        fig.text(0.08, 0.78, "Objetivo", fontsize=14, color=INTI["cyan"], weight="bold")
        add_wrapped(fig, "Inferir los equipos o modos de operación presentes en una instalación a partir de una medición eléctrica agregada, sin sensores individuales por máquina.", 0.08, 0.74, 108, 11)
        cards = [
            ("Muestras", f"{summary['samples']:,}"),
            ("Duración", f"{summary['duration_hours']:.2f} h"),
            ("Energía Total", f"{summary['total_energy_kwh']:.2f} kWh"),
            ("Potencia Pico", f"{summary['peak_power_kw']:.2f} kW"),
            ("Eventos Detectados", f"{len(clustered):,}"),
            ("Cargas / Clústeres", f"{len(cluster_info)}"),
        ]
        for i, (label, value) in enumerate(cards):
            x = 0.08 + (i % 3) * 0.29
            y = 0.59 - (i // 3) * 0.18
            fig.add_artist(plt.Rectangle((x, y), 0.23, 0.12, facecolor="#F2F5F8", edgecolor=INTI["cyan"], linewidth=1.2))
            fig.text(x + 0.015, y + 0.078, label, fontsize=9, color=INTI["gray"])
            fig.text(x + 0.015, y + 0.03, value, fontsize=17, color=INTI["blue"], weight="bold")

        has_gt = any(m.get("custom_label") for m in machine_stats)
        gt_note = " · Ground Truth activo (etiquetas manuales personalizadas)" if has_gt else ""
        fig.text(0.08, 0.18, "Configuración reproducida", fontsize=13, color=INTI["cyan"], weight="bold")
        add_wrapped(fig, f"Detección: ΔI ≥ 2 A o ΔP ≥ 1 kW (arranques) y transiciones simétricas. Agrupamiento: {algorithm.upper()} con {n_clusters} grupos, normalización StandardScaler.{gt_note}", 0.08, 0.14, 108, 10)
        pdf.savefig(fig); plt.close(fig)

        # 2. Pipeline and variables
        fig = page("Cómo se construye la firma eléctrica", "Variables calculadas antes de aplicar Machine Learning")
        steps = [
            ("1. Limpieza", "Fecha + hora → timestamp ordenado. Columnas eléctricas → valores numéricos."),
            ("2. Magnitudes", "I_total, V_avg, PF_avg, P_total, S_total, Q_total y THD_avg."),
            ("3. Cambios", "ΔI, ΔP y ΔQ entre muestras consecutivas de 10 segundos."),
            ("4. Eventos", "Se conservan transiciones positivas y negativas (arranque/parada) sobre el umbral."),
            ("5. Firma", "Cada evento se representa como [ΔP, ΔI, THD, ΔQ, ΔIh/ΔI1]."),
            ("6. Clustering", f"StandardScaler + {algorithm.upper()} con remapeo determinístico por potencia."),
        ]
        for i, (head, body) in enumerate(steps):
            y = 0.79 - i * 0.105
            fig.add_artist(plt.Rectangle((0.09, y - 0.045), 0.18, 0.065, facecolor=INTI["blue"], edgecolor=INTI["blue"]))
            fig.text(0.105, y - 0.02, head, fontsize=10, color="white", weight="bold")
            fig.text(0.31, y, body, fontsize=10, color=INTI["ink"], va="center")
        fig.text(0.09, 0.14, "Fórmulas principales", fontsize=13, color=INTI["cyan"], weight="bold")
        formulas = [
            r"I_total = I_L1 + I_L2 + I_L3",
            r"P = (V_avg · I_total · PF_avg) / 1000",
            r"S = (V_avg · I_total) / 1000",
            r"Q = sqrt(max(0, S² − P²))",
            r"Δx_t = x_t − x_(t−1)",
        ]
        for i, formula in enumerate(formulas):
            fig.text(0.11 + (i % 3) * 0.29, 0.095 - (i // 3) * 0.035, formula, fontsize=10, color=INTI["blue"], family="DejaVu Sans Mono")
        pdf.savefig(fig); plt.close(fig)

        # 3. Real time series
        fig = page("Señal agregada y eventos detectados", "La detección busca saltos eléctricos compatibles con arranques o cambios de carga")
        ax = fig.add_subplot(111)
        sample = df_work.iloc[::max(1, len(df_work) // 1800)]
        ax.plot(sample["timestamp"], sample["P_total"], color=INTI["blue"], linewidth=1.0, label="Potencia total estimada")
        event_times = clustered["timestamp"]
        event_power = clustered["P_total"]
        ax.scatter(event_times, event_power, s=10, color=INTI["coral"], alpha=0.7, label=f"Eventos detectados ({len(clustered)})")
        ax.set_xlabel("Tiempo")
        ax.set_ylabel("Potencia activa [kW]")
        ax.set_title("Potencia agregada y transiciones detectadas (ON/OFF)")
        ax.grid(alpha=0.2)
        ax.legend(frameon=False)
        fig.autofmt_xdate()
        pdf.savefig(fig); plt.close(fig)

        # 4. Fichas de Cargas y Reparto Energético (Ground Truth)
        fig = page("Equipos Desagregados y Reparto Energético", "Fichas técnicas de las máquinas identificadas y validación Ground Truth")
        
        # Upper subplot: Table
        ax_table = fig.add_axes([0.08, 0.44, 0.86, 0.40])
        ax_table.axis('off')

        headers = ["Carga", "Equipo Identificado", "Tipo / Firma", "Potencia", "ΔI Pico", "THD", "Arranques", "Uso", "Energía", "Participación"]
        table_rows = []
        cell_colors = []
        for m in machine_stats:
            gt_tag = " [GT]" if m.get("custom_label") else ""
            table_rows.append([
                f"M{m['id']}",
                f"{m['name'][:24]}{gt_tag}",
                f"{m.get('load_class', m['category'])[:22]}",
                f"{m['nominal_power_kw']:.1f} kW",
                f"{m['peak_current_a']:.1f} A",
                f"{m['thd_pct']:.1f} %",
                f"{m['event_count']}",
                f"{m['active_minutes']/60.0:.1f} h",
                f"{m['energy_kwh']:.2f} kWh",
                f"{m['energy_share_pct']:.1f} %"
            ])
            cell_colors.append(["#F9FAFB"] * len(headers))

        table = ax_table.table(
            cellText=table_rows,
            colLabels=headers,
            cellLoc='center',
            loc='center',
            cellColours=cell_colors
        )
        table.auto_set_font_size(False)
        table.set_fontsize(8)
        table.scale(1.0, 1.6)

        # Style table headers
        for k in range(len(headers)):
            cell = table[(0, k)]
            cell.set_facecolor(INTI["blue"])
            cell.set_text_props(color='white', weight='bold')

        # Lower subplot: Bar chart of energy share
        ax_bar = fig.add_axes([0.08, 0.12, 0.86, 0.24])
        machine_names = [f"M{m['id']}: {m['name'][:18]}" + (" [GT]" if m.get("custom_label") else "") for m in machine_stats]
        shares = [m["energy_share_pct"] for m in machine_stats]
        bar_colors = [m.get("color", INTI["cyan"]) for m in machine_stats]

        y_pos = np.arange(len(machine_names))
        bars = ax_bar.barh(y_pos, shares, color=bar_colors, edgecolor=INTI["gray"], height=0.55)
        ax_bar.set_yticks(y_pos)
        ax_bar.set_yticklabels(machine_names, fontsize=8)
        ax_bar.invert_yaxis()
        ax_bar.set_xlabel("Participación en el consumo total diario (%)", fontsize=8)
        ax_bar.set_title("Distribución porcentual de energía desagregada por carga", fontsize=9, weight="bold")
        ax_bar.grid(axis='x', alpha=0.3)

        for bar in bars:
            w = bar.get_width()
            ax_bar.text(w + 0.5, bar.get_y() + bar.get_height() / 2, f"{w:.1f}%", va='center', fontsize=8, weight='bold', color=INTI["ink"])

        fig.text(0.08, 0.07, "* Nota: [GT] indica equipo con nombre personalizado por el usuario (Ground Truth persistido en base de datos).", fontsize=7.5, color=INTI["gray"], style='italic')
        pdf.savefig(fig); plt.close(fig)

        # 5. 3D actual feature view
        fig = page("Nube 3D de actividad eléctrica", "Corriente y tensión en el plano inferior; tiempo en el eje vertical")
        ax = fig.add_subplot(111, projection="3d")
        sampled = clustered.sample(min(900, len(clustered)), random_state=42) if len(clustered) else clustered
        for cluster in sorted(sampled["cluster"].unique()) if len(sampled) else []:
            sub = sampled[sampled["cluster"] == cluster]
            color = cluster_info[cluster].get("color", CLUSTER_COLORS[int(cluster) % len(CLUSTER_COLORS)])
            gt_tag = " [GT]" if cluster_info[cluster].get("custom_label") else ""
            label_text = f"{cluster_info[cluster]['name'][:24]}{gt_tag}"
            ax.scatter(sub["I_total"], sub["V_avg"], sub["hour_of_day"] * 60, s=9, alpha=0.75, color=color, label=label_text)
        ax.set_xlabel("Corriente [A]")
        ax.set_ylabel("Tensión [V]")
        ax.set_zlabel("Tiempo [min]")
        ax.set_title("Eventos agrupados por firma eléctrica")
        ax.view_init(elev=22, azim=-58)
        ax.legend(loc="upper left", bbox_to_anchor=(0.0, 1.02), fontsize=7, frameon=False)
        pdf.savefig(fig); plt.close(fig)

        # 6. Feature spaces
        fig = page("Espacios de características", "Separación visual de los eventos según potencia, corriente, reactiva y distorsión")
        axes = fig.subplots(1, 2)
        for cluster in sorted(clustered["cluster"].unique()):
            sub = clustered[clustered["cluster"] == cluster]
            color = cluster_info[cluster].get("color", CLUSTER_COLORS[int(cluster) % len(CLUSTER_COLORS)])
            gt_tag = " [GT]" if cluster_info[cluster].get("custom_label") else ""
            name = f"{cluster_info[cluster]['name'][:16]}{gt_tag}"
            axes[0].scatter(sub["delta_P"], sub["delta_Q"], s=8, alpha=0.65, color=color, label=name)
            axes[1].scatter(sub["delta_I"], sub["THD_avg"], s=8, alpha=0.65, color=color, label=name)
        axes[0].set_title("ΔP vs ΔQ")
        axes[0].set_xlabel("ΔP [kW]")
        axes[0].set_ylabel("ΔQ [kvar]")
        axes[1].set_title("ΔI vs THD")
        axes[1].set_xlabel("ΔI [A]")
        axes[1].set_ylabel("THD [%]")
        for ax in axes:
            ax.grid(alpha=0.2)
        axes[1].legend(fontsize=7, frameon=False, loc="best")
        pdf.savefig(fig); plt.close(fig)

        # 7. Algorithms and identification rules
        fig = page("Algoritmos e identificación de equipos", "Qué calcula el sistema y qué parte corresponde a inferencia heurística")
        fig.text(0.08, 0.78, "Algoritmos de Clasificación", fontsize=14, color=INTI["cyan"], weight="bold")
        add_wrapped(fig, "K-Means: asigna eventos a centroides y es el método predeterminado. GMM: modela grupos como distribuciones gaussianas con variabilidad de régimen. DBSCAN: agrupa por densidad y separa modos atípicos o ruidos.", 0.08, 0.74, 105, 10)
        fig.text(0.08, 0.59, "Etiquetado Manual (Ground Truth - Punto B)", fontsize=14, color=INTI["cyan"], weight="bold")
        add_wrapped(fig, "El sistema permite al operador renombrar cualquier equipo detectado de forma manual. Estas etiquetas se persisten permanentemente en el servidor (backend/load_labels.json) asociadas a la firma y ranking del equipo, sobrescribiendo las heurísticas automáticas tanto en las pantallas interactivas como en los informes PDF emitidos.", 0.08, 0.55, 105, 10)
        fig.text(0.08, 0.36, "Bibliotecas y Motor", fontsize=14, color=INTI["cyan"], weight="bold")
        add_wrapped(fig, "Backend: pandas para datos tabulares, NumPy para cálculo numérico, scikit-learn para K-Means/GMM/DBSCAN/StandardScaler y Tornado para la API REST asíncrona. Frontend: TypeScript y Canvas HTML5 para gráficos a 60 FPS sin dependencias externas pesadas.", 0.08, 0.32, 105, 10)
        pdf.savefig(fig); plt.close(fig)

        # 8. Limitations and next steps
        fig = page("Interpretación y próximos pasos", "Resultados actuales y recomendaciones para una identificación más robusta")
        fig.text(0.08, 0.78, "Qué significa el resultado", fontsize=14, color=INTI["cyan"], weight="bold")
        add_wrapped(fig, "La aplicación identifica patrones de consumo y los agrupa según su firma eléctrica. Los nombres mostrados combinan inferencias físicas automáticas con las validaciones Ground Truth introducidas por el operador.", 0.08, 0.74, 105, 10)
        fig.text(0.08, 0.59, "Limitaciones y conservación de potencia", fontsize=14, color=INTI["cyan"], weight="bold")
        add_wrapped(fig, "La potencia se calcula a partir del registro del analizador trifásico. Para el perfeccionamiento continuo, se avanza hacia modelos de Conservación Estricta de Energía (Punto C) y Optimización Combinatoria para asegurar que la suma de potencias desagregadas más la base iguale exactamente la potencia total en cada instante.", 0.08, 0.55, 105, 10)
        fig.text(0.08, 0.4, "Mejoras recomendadas", fontsize=14, color=INTI["cyan"], weight="bold")
        add_wrapped(fig, "Completar la validación Ground Truth con mediciones de sub-medición de contraste, entrenar clasificadores supervisados con las etiquetas guardadas y evaluar métricas estándar de desagregación (F1-score, MAE, SAE).", 0.08, 0.36, 105, 10)
        fig.text(0.08, 0.16, "Conclusión", fontsize=14, color=INTI["cyan"], weight="bold")
        add_wrapped(fig, "El sistema actual constituye una plataforma profesional completa de NILM: detecta eventos, clasifica firmas eléctricas, resporta desgloses energéticos y sincroniza el conocimiento del operador con el motor de IA.", 0.08, 0.12, 105, 10)
        pdf.savefig(fig); plt.close(fig)

    print(f"PDF generado: {output_path}")
    return output_path


def main():
    generate_report()


if __name__ == "__main__":
    main()
