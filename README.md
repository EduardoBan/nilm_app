# Plataforma de Análisis y Desagregación de Energía NILM (Non-Intrusive Load Monitoring)

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
7. **Firma Armónica Transitoria por Equipo (ΔH3 / ΔH5 / ΔH7)**:
   - Barras agrupadas con el salto medio de corriente armónica por orden en el instante de arranque de cada equipo, más un plano $\Delta H_5$ vs $|\Delta P|$ por evento.
   - Permite discriminar **electrónica de potencia** (ΔH alto con ΔP modesto, arriba-izquierda) de **motores de arranque directo** (ΔP alto con ΔH bajo, abajo-derecha), incluso antes de mirar el THD en régimen permanente.
8. **FHMM Exacto (Viterbi · hmmlearn)**:
   - Bloque de metadatos con el algoritmo efectivamente aplicado (`fhmm_exact_viterbi_hmmlearn` o `event_driven_fallback`), log-probabilidad, número de estados combinados, dimensiones por equipo y muestras decodificadas con su factor de submuestreo.
   - Gráfico de la secuencia de estado conjunto decodificada por Viterbi. Si el producto cartesiano de estados supera las 400 combinaciones o `hmmlearn` no está instalado, la pestaña cae automáticamente a las curvas desagregadas multi-estado.
9. **Validación de la Desagregación (PASO 3)**:
   - Error de reconstrucción global: **MAE / RMSE / MAPE** entre la potencia medida y `baseline + Σ equipos`, más el porcentaje de energía explicada por la desagregación.
   - **MAE del salto ON** por equipo: consistencia entre el ΔP del evento de arranque y el salto real en la curva desagregada.
   - **Matriz de confusión ON/OFF** (global y por equipo) contra la referencia de eventos pareados, con **precision / recall / F1 / accuracy** y gráfico de barras del F1 por equipo.
   - **Métricas de regresión (energía)** por equipo y global: **MAE/RMSE** de potencia (kW), **RE** (error relativo en la energía total acumulada, %) y **NEP** (error de potencia normalizado por la energía real).

## 🤖 Algoritmos de Inteligencia Artificial Disponibles

- **K-Means Clustering**: Agrupamiento óptimo por centroides multidimensionales con inicialización k-means++.
- **Gaussian Mixture Models (GMM)**: Modelado probabilístico con matrices de covarianza para capturar cargas con variabilidad de régimen.
- **DBSCAN**: Agrupamiento basado en densidad para identificar modos de operación atípicos o anomalías.
- ** Adjustable Trip Threshold **: Interactive current transient sensitivity selector ($\Delta I$ from 0.5 A to 10 A).

---

## 🧠 Opción A: Mejoras de IA y Desagregación

### 1. Modelado Multi-Estado (FHMM / HMM)
Actívelo con el interruptor **🧠 Multi-Estado (FHMM)** de la barra de control. En lugar de asumir estados binarios ON/OFF, el motor implementa un **Modelo Oculto de Markov Factorial**:

- **Estimación de niveles** (`estimate_machine_states`): los saltos de potencia de arranque (ΔP) de cada equipo se agrupan con K-Means + validación por silueta para detectar **estados intermedios** (ej. compresor en *Plena Carga* / *Marcha en Vacío* / *Apagado*).
- **Inferencia MAP factorial** (`disaggregate_load_fhmm`): la señal agregada se modela como la superposición `P_total(t) ≈ P_base + Σ nivel_c(estado_c(t))`. Se intentan dos estrategias en cascada:
  1. **FHMM exacto** (`_fhmm_exact_viterbi`): con `hmmlearn` se construye un `GaussianHMM` sobre el **producto cartesiano** de estados. La media combinada es `base + Σ niveles` y la matriz de transición combinada resulta del **producto de Kronecker** de las individuales (equipos independientes). Los parámetros se fijan analíticamente y se decodifica con **Viterbi** (sin re-estimación EM), submuestreando a ≤1500 puntos para acotar el costo. Si el producto de estados excede 400 combinaciones, el bloque se **poda** y se degrada al paso 2.
  2. **Descenso por eventos** (fallback): inicialización voraz + refinamiento **Viterbi por bloques** con emisiones gaussianas y costo de conmutación. Se usa cuando `hmmlearn` no está instalado o el modelo exacto es intratable.
- **Salidas**: curvas de potencia multi-nivel por equipo, Gantt con el nombre del estado activo, energía/tiempo por estado en las fichas de equipos (`multi_state_models` y `machine_statistics[].states`), firmas armónicas por equipo (`harmonic_signatures`) y diagnóstico del FHMM (`fhmm_exact`, `hmmlearn_available`) para la pestaña **🧠 FHMM-Viterbi**.

### 2. Edición y Etiquetado Manual de Equipos (Ground Truth - Punto B)
- **Renombrado en dos vías**: Pulse **✏️** junto al nombre del equipo en la **tabla resumen** o en las **fichas técnicas** para renombrarlo en línea (ej. *"Compresor / Motor Principal"* → *"Compresor Sala de Máquinas N° 1"*). `Enter` guarda, `Esc` cancela.
- **Ranking determinístico**: Los clústeres generados por la IA se reordenan automáticamente por potencia activa nominal descendente ($\Delta P$). El ID `0` siempre corresponde a la carga principal de mayor potencia, garantizando estabilidad permanente de las etiquetas manuales.
- **Persistencia en Servidor**: Las etiquetas se almacenan por medición + clúster en `backend/load_labels.json` (endpoints REST `GET /api/labels`, `POST /api/labels` y `DELETE /api/labels` para restablecer valores automáticos).
- **Propagación Integral**: El nombre personalizado se propaga en cascada hacia las curvas temporales desagregadas, los diagramas de Gantt, la nube 3D y los espacios de características 2D, acompañado del distintivo visual **GT**.
- **Informe PDF Dinámico**: El botón **📄 Informe PDF** genera al vuelo el reporte técnico para la medición activa, incluyendo una tabla de fichas de cargas con los nombres Ground Truth y la distribución porcentual de consumo eléctrico.

### 3. Refinamiento por Armónicos Transitorios
El motor calcula el salto de corriente armónica (H3…H13, `ΔIh/ΔI₁`) en el instante de cada arranque y lo combina con el ratio reactivo/activo (ΔQ/ΔP) y el THD para clasificar la tecnología de la carga:

| Firma del transitorio | Clasificación |
|---|---|
| ΔIh/ΔI₁ alto o THD ≥ 35 % con ΔQ/ΔP bajo | 🎛️ Electrónica de Potencia (Variador / Rectificador) |
| ΔIh/ΔI₁ alto con componente reactiva | ⚡ Carga No Lineal (Soldadora / Arco Eléctrico) |
| ΔQ/ΔP alto, armónicos bajos | ⚙️ Motor Inductivo (Arranque Directo / Estrella-Tríangulo) |
| ΔQ/ΔP medio | 🌀 Motor / Carga Mixta (Arranque Suave) |
| ΔQ/ΔP bajo, armónicos bajos | 🔥 Carga Resistiva (Calefacción / Iluminación) |

El resultado se muestra como badge en la tabla (columna *Tipo de Carga*) y en las fichas, junto a la **Firma Armónica ΔIh/ΔI₁** de cada equipo.

### 4. Validación de la Desagregación (PASO 3)
Pestaña **✅ Validación**: cada análisis calcula la clave `validation` con la calidad de la desagregación automática:

- **Error de reconstrucción** (`reconstruction`): MAE/RMSE/MAPE entre la potencia medida y `baseline + Σ equipos`, porcentaje de energía explicada, **RE** (error relativo de la energía total acumulada) y **NEP** (error de potencia normalizado). Cuantifica cuánto de la señal real captura el modelo NILM.
- **Consistencia de saltos** (`machines[].jump_mae_kw`): en cada arranque ON se compara el ΔP esperado del evento contra el salto real de la curva desagregada del equipo.
- **Detección ON/OFF** (`confusion_global`, `machines[].confusion`): referencia = pareo de eventos (ON tras un arranque, OFF tras una parada); predicción = curva desagregada por encima del umbral (10 % del nominal). Se reportan TP/FP/FN/TN con **precision/recall/F1/accuracy**.
- **Regresión por equipo** (`machines[].reg_mae_kw`, `reg_rmse_kw`, `re_pct`, `nep`): MAE/RMSE en kW contra la señal de referencia por eventos (nominal mientras activo, 0 kW si no); RE compara la energía acumulada predicha vs referida; NEP normaliza el error absoluto por la energía de referencia (comparable entre equipos de distinto tamaño).
- La pestaña muestra tarjetas de métricas (MAE/RMSE/MAPE/RE/NEP + F1/accuracy), fichas por equipo con su matriz de confusión y un gráfico de barras del **F1 por equipo** (1.0 = desagregación perfecta).