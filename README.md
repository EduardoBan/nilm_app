<!DOCTYPE html> npsis y Desagregación de Energía NILM (Non-Intrusive Load Monitoring)

Plataforma Cliente-Servidor de alto rendimiento para el análisis, desagregación y monitoreo no intrusivo de cargas eléctricas industriales y comerciales a partir de registros de analizadores de redes eléctricas (archivos Excel de `C:\Users\local\Documents\IA\Energia\Data`).

---

## 🏗️ Arquitectura de la Aplicación

```
nilm_app/
├── backend/
│   ├── data_manager.py     # Gestor de datos, lectura de Excel, pre-caching a Pickle/Feather (<50ms)
│   ├── nilm_engine.py      # Motor IA NILM: Detección de eventos, K-Means, GMM, DBSCAN, Gantt y Desagregación
│   └── server.py           # Servidor REST API asíncrono con Tornado (Endpoints JSON + Servidor Estático)
├── frontend/
│   ├── index.html          # Interfaz de usuario interactiva (Single Page Application)
│   ├── css/
│   │   └── styles.css      # Estilos modernos para panel industrial (Dark Mode)
│   ├── src/
│   │   ├── types/nilm.ts   # Modelos e interfaces en TypeScript
│   │   ├── services/api.ts # Cliente API en TypeScript
│   │   ├── components/ChartEngine.ts # Motor gráfico en Canvas de alto rendimiento
│   │   └── app.ts          # Controlador principal y gestión de estado reactivo
│   └── dist/
│       └── bundle.js       # Código compilado desde TypeScript
├── scripts/
│   └── build.js            # Compilador y empaquetador de TypeScript nativo de Node.js 22
├── start_server.py         # Script de inicio rápido en un clic
└── README.md
```

---

## 🚀 Cómo Ejecutar la Aplicación

1. **Iniciar el Servidor Python**:
   ```bash
   .venv\Scripts\python.exe C:\Users\local\Documents\IA\Energia\nilm_app\start_server.py
   ```
2. **Abrir en el Navegador**:
   - URL: [http://localhost:8000](http://localhost:8000)

_(Si realizas modificaciones al código fuente en TypeScript dentro de `frontend/src/`, vuelve a compilar con: `node scripts/build.js`)_

### NILMTK

El motor integra opcionalmente el detector de estados de potencia de NILMTK. Para instalar la versión moderna desde el repositorio oficial:

```bash
python -m pip install -r requirements.txt
```

Cuando NILMTK está disponible, el análisis devuelve los estados de potencia agregada en `nilmtk_power_states_kw` y marca `nilmtk_available` como `true`. Si la instalación no está disponible, el motor conserva el análisis local basado en eventos y `scikit-learn`, sin impedir que la aplicación arranque.

---

## 📊 Curvas y Estudios que Realiza la Aplicación

1. **Curva de Potencia Total y Desagregada por Equipo**:
   - Muestra la potencia activa medida ($P_{\Sigma}$) junto a la descomposición de potencia consumida en tiempo real por cada máquina detectada ($P_1(t), P_2(t), \dots$) y la carga base de fondo (_Standby_).
2. **Diagrama de Gantt Operacional (Línea de Tiempo 00:00 a 24:00)**:
   - Permite visualizar con precisión los intervalos de arranque, parada y tiempo de funcionamiento continuo de cada equipo en la planta.
3. **Espacios de Características para Clasificación IA**:
   - **Plano $\Delta P$ vs $\Delta Q$**: Separación de equipos según su demanda de potencia activa y reactiva.
   - **Plano $\Delta I$ vs $THD_I$**: Identificación por corriente de arranque y distorsión armónica generada (clave para variadores de velocidad e inversores).
4. **Distribución Horaria de Arranques y Actividad (24h)**:
   - Histograma de eventos de arranque por hora del día para identificar turnos de trabajo y picos de simultaneidad.
5. **Calidad de Red y Armónicos**:
   - Curvas temporales de corriente trifásica ($I_{L1}, I_{L2}, I_{L3}$) y tensión ($U_{L1}, U_{L2}, U_{L3}$).
   - Espectro de armónicos de corriente (fundamental hasta el armónico 25) para auditoría de calidad eléctrica.
6. **Fichas Técnicas y Reparto Energético**:
   - Potencia nominal estimada por equipo (kW), corriente de arranque (A), factor de distorsión THD (%), energía total consumida (kWh) y porcentaje de participación en la factura eléctrica.

## 🤖 Algoritmos de Inteligencia Artificial Disponibles

- **K-Means Clustering**: Agrupamiento óptimo por centroides multidimensionales con inicialización k-means++.
- **Gaussian Mixture Models (GMM)**: Modelado probabilístico con matrices de covarianza para capturar cargas con variabilidad de régimen.
- **DBSCAN**: Agrupamiento basado en densidad para identificar modos de operación atípicos o anomalías.
- **Umbral de Disparo Ajustable**: Selector interactivo de sensibilidad de transitorio de corriente ($\Delta I$ de 0.5 A a 10 A).
  time_minutes: number;   * Renders a pseudo-3D activity cloud using current, voltage and time as axes.    const canvas3D = document.getElementById('chart-activity-3d') as HTMLCanvasElement;                "time_minutes": float(r['timestamp'].hour * 60 + r['timestamp'].minute + r['timestamp'].second / 60.0),    const maxX = Math.max(...events.map(e => Math.abs(e.x)), 1) * 1.15;      const root = project3D(0, 0, 0);    const state = {