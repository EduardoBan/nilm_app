"""Generate a Spanish NILM analysis report with real data and charts."""
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


def main():
    dm = DataManager()
    engine = NILMEngine(dm)
    df = dm.load_dataset(DATASET)
    summary = dm.get_summary_stats(DATASET)
    df_work, events = engine.detect_events(df, current_threshold=2.0, power_threshold=1.0)
    clustered, cluster_info = engine.cluster_appliances(events, n_clusters=4, algorithm="kmeans")
    disagg, baseline, timeline, machine_stats = engine.disaggregate_load(df_work, clustered, cluster_info)

    with PdfPages(OUTPUT) as pdf:
        # 1. Executive summary
        fig = page("Informe de análisis NILM", "Desagregación no intrusiva de cargas eléctricas | Medición: 10 de abril")
        fig.text(0.08, 0.78, "Objetivo", fontsize=14, color=INTI["cyan"], weight="bold")
        add_wrapped(fig, "Inferir los equipos o modos de operación presentes en una instalación a partir de una medición eléctrica agregada, sin sensores individuales por máquina.", 0.08, 0.74, 108, 11)
        cards = [
            ("Muestras", f"{summary['samples']:,}"),
            ("Duración", f"{summary['duration_hours']:.2f} h"),
            ("Energía", f"{summary['total_energy_kwh']:.2f} kWh"),
            ("Pico", f"{summary['peak_power_kw']:.2f} kW"),
            ("Eventos", f"{len(clustered):,}"),
            ("Clústeres", f"{len(cluster_info)}"),
        ]
        for i, (label, value) in enumerate(cards):
            x = 0.08 + (i % 3) * 0.29
            y = 0.59 - (i // 3) * 0.18
            fig.add_artist(plt.Rectangle((x, y), 0.23, 0.12, facecolor="#F2F5F8", edgecolor=INTI["cyan"], linewidth=1.2))
            fig.text(x + 0.015, y + 0.078, label, fontsize=9, color=INTI["gray"])
            fig.text(x + 0.015, y + 0.03, value, fontsize=17, color=INTI["blue"], weight="bold")
        fig.text(0.08, 0.18, "Configuración reproducida", fontsize=13, color=INTI["cyan"], weight="bold")
        add_wrapped(fig, "Detección: ΔI ≥ 2 A o ΔP ≥ 1 kW (arranques) y apagados simétricos. Agrupamiento: K-Means con 4 grupos, normalización StandardScaler y semilla aleatoria 42.", 0.08, 0.14, 108, 10)
        pdf.savefig(fig); plt.close(fig)

        # 2. Pipeline and variables
        fig = page("Cómo se construye la firma eléctrica", "Variables calculadas antes de aplicar Machine Learning")
        steps = [
            ("1. Limpieza", "Fecha + hora → timestamp ordenado. Columnas eléctricas → valores numéricos."),
            ("2. Magnitudes", "I_total, V_avg, PF_avg, P_total, S_total, Q_total y THD_avg."),
            ("3. Cambios", "ΔI, ΔP y ΔQ entre muestras consecutivas."),
            ("4. Eventos", "Se conservan las transiciones positivas y negativas (arranque y apagado) que superan los umbrales."),
            ("5. Firma", "Cada evento se representa como [ΔP, ΔI, THD, ΔQ]."),
            ("6. Clustering", "StandardScaler + K-Means, GMM o DBSCAN."),
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

        # 4. 3D actual feature view
        fig = page("Nube 3D de actividad eléctrica", "Corriente y tensión en el plano inferior; tiempo en el eje vertical")
        ax = fig.add_subplot(111, projection="3d")
        sampled = clustered.sample(min(900, len(clustered)), random_state=42) if len(clustered) else clustered
        for cluster in sorted(sampled["cluster"].unique()) if len(sampled) else []:
            sub = sampled[sampled["cluster"] == cluster]
            ax.scatter(sub["I_total"], sub["V_avg"], sub["hour_of_day"] * 60, s=9, alpha=0.75, color=CLUSTER_COLORS[int(cluster) % len(CLUSTER_COLORS)], label=cluster_info[cluster]["name"][:28])
        ax.set_xlabel("Corriente [A]")
        ax.set_ylabel("Tensión [V]")
        ax.set_zlabel("Tiempo [min]")
        ax.set_title("Eventos agrupados por firma eléctrica")
        ax.view_init(elev=22, azim=-58)
        ax.legend(loc="upper left", bbox_to_anchor=(0.0, 1.02), fontsize=7, frameon=False)
        pdf.savefig(fig); plt.close(fig)

        # 5. Feature spaces
        fig = page("Espacios de características", "Separación visual de los eventos según potencia, corriente, reactiva y distorsión")
        axes = fig.subplots(1, 2)
        for cluster in sorted(clustered["cluster"].unique()):
            sub = clustered[clustered["cluster"] == cluster]
            color = CLUSTER_COLORS[int(cluster) % len(CLUSTER_COLORS)]
            name = cluster_info[cluster]["name"][:18]
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

        # 6. Algorithms and identification rules
        fig = page("Algoritmos e identificación de equipos", "Qué calcula el sistema y qué parte corresponde a inferencia heurística")
        fig.text(0.08, 0.78, "Algoritmos", fontsize=14, color=INTI["cyan"], weight="bold")
        add_wrapped(fig, "K-Means: asigna eventos a centroides y es el método predeterminado. GMM: modela grupos como distribuciones gaussianas y permite solapamiento probabilístico. DBSCAN: agrupa por densidad y puede encontrar eventos atípicos.", 0.08, 0.74, 105, 10)
        fig.text(0.08, 0.59, "Reglas de interpretación", fontsize=14, color=INTI["cyan"], weight="bold")
        add_wrapped(fig, "El clustering encuentra grupos eléctricos, pero no conoce el nombre físico del equipo. Después se aplican reglas: ΔP ≥ 25 kW o ΔI ≥ 40 A → motor/compresor principal; THD ≥ 40 % → variador/carga electrónica; ΔP ≥ 8 kW → bomba/ventilador; ΔP ≥ 2 kW → motor mediano; el resto → auxiliar/standby.", 0.08, 0.55, 105, 10)
        fig.text(0.08, 0.36, "Bibliotecas", fontsize=14, color=INTI["cyan"], weight="bold")
        add_wrapped(fig, "Backend: pandas para datos tabulares, NumPy para cálculo numérico, scikit-learn para K-Means/GMM/DBSCAN/StandardScaler y Tornado para la API. Frontend: TypeScript y Canvas HTML5 para los gráficos, sin una biblioteca 3D externa.", 0.08, 0.32, 105, 10)
        pdf.savefig(fig); plt.close(fig)

        # 7. Limitations and next steps
        fig = page("Interpretación y próximos pasos", "Resultados actuales y recomendaciones para una identificación más robusta")
        fig.text(0.08, 0.78, "Qué significa el resultado", fontsize=14, color=INTI["cyan"], weight="bold")
        add_wrapped(fig, "La aplicación identifica patrones de consumo y los agrupa según su firma eléctrica. Los nombres mostrados son categorías inferidas, no una confirmación del modelo exacto de la máquina.", 0.08, 0.74, 105, 10)
        fig.text(0.08, 0.59, "Limitaciones actuales", fontsize=14, color=INTI["cyan"], weight="bold")
        add_wrapped(fig, "La potencia se estima a partir de tensión, corriente y factor de potencia; las duraciones se estiman a partir de las transiciones de apagado (con heurística si no existe apagado limpio); y los umbrales de identificación son reglas fijas.", 0.08, 0.55, 105, 10)
        fig.text(0.08, 0.4, "Mejoras recomendadas", fontsize=14, color=INTI["cyan"], weight="bold")
        add_wrapped(fig, "Validar contra mediciones individuales por equipo, usar duración y armónicos como características, entrenar un clasificador supervisado con etiquetas reales y evaluar precisión, recall, F1 y error de energía.", 0.08, 0.36, 105, 10)
        fig.text(0.08, 0.16, "Conclusión", fontsize=14, color=INTI["cyan"], weight="bold")
        add_wrapped(fig, "El sistema actual constituye una base funcional de NILM: detecta cambios, construye firmas, agrupa eventos y reconstruye curvas aproximadas por carga.", 0.08, 0.12, 105, 10)
        pdf.savefig(fig); plt.close(fig)

    print(f"PDF generado: {OUTPUT}")


if __name__ == "__main__":
    main()
