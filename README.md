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
   - **Rasgos extendidos (MEJORA #20)**: ratio de inrush (×), cos φ medio y tipo de fase (*Monofásico (1 fase)* / *Asimétrico (2 fases)* / *Trifásico equilibrado*), presentes tanto en la tabla resumen como en las fichas técnicas de cada equipo.
   - **Coste económico (MEJORA #16)**: EUR por equipo y por turno con tarifa horaria (periodos valle/llano/punta del 2.0TD peninsular, ejemplo editable en `NILMEngine.DEFAULT_TARIFF`), proyección a EUR/mes y coste del residuo/standby; columna "Coste (€)" en la tabla y bloque resumen en la pestaña Equipos.
   - **Calidad por equipo (MEJORA #15)**: potencia aparente del salto `avg_delta_s` (kVA), potencia de distorsión `dist_kva` con su fracción `dist_ratio` D/S (IEEE 1459) y desbalance de fases `phase_imbalance`; columnas "kVA distorsión" y "Desbalance" en la tabla de equipos y stats en las fichas técnicas.
- **Anomalías sobre el residuo (MEJORA #14)**: MAE móvil del residuo (~30 min) con umbral robusto (mediana + 3·1.4826·MAD), eventos sostenidos con marcas de tiempo y gráfica MAE vs umbral en el bloque de la pestaña Fugas/Standby; campo `residual_anomalies` en la respuesta del análisis.
7. **Firma Armónica Transitoria por Equipo (ΔH3 / ΔH5 / ΔH7)**:
   - Barras agrupadas con el salto medio de corriente armónica por orden en el instante de arranque de cada equipo, más un plano $\Delta H_5$ vs $|\Delta P|$ por evento.
   - Permite discriminar **electrónica de potencia** (ΔH alto con ΔP modesto, arriba-izquierda) de **motores de arranque directo** (ΔP alto con ΔH bajo, abajo-derecha), incluso antes de mirar el THD en régimen permanente.
8. **FHMM Exacto (Viterbi · hmmlearn)**:
   - Bloque de metadatos con el algoritmo efectivamente aplicado (`fhmm_exact_viterbi_priors_hmmlearn` con priors, `fhmm_exact_viterbi_hmmlearn` sin ellos o `event_driven_fallback`), log-probabilidad, número de estados combinados, dimensiones por equipo, muestras decodificadas con su factor de submuestreo y estado de los priors horarios.
   - Gráfico de la secuencia de estado conjunto decodificada por Viterbi. Si el producto cartesiano de estados supera las 400 combinaciones o `hmmlearn` no está instalado, la pestaña cae automáticamente a las curvas desagregadas multi-estado.
   - **Priors horarios (MEJORA #2)**: perfil de arranque por equipo derivado de los eventos ON (24 valores/hora) que modula la transición OFF→ON del modelo en cada bloque horario. Se decodifica con Viterbi de transición dependiente del tiempo y la pestaña compara los minutos ON por hora sin/con priors, junto con el log-prob de ambos escenarios.
9. **Validación de la Desagregación (PASO 3)**:
   - Error de reconstrucción global: **MAE / RMSE / MAPE** entre la potencia medida y `baseline + Σ equipos`, más el porcentaje de energía explicada por la desagregación.
   - **MAE del salto ON** por equipo: consistencia entre el ΔP del evento de arranque y el salto real en la curva desagregada.
   - **Matriz de confusión ON/OFF** (global y por equipo) contra la referencia de eventos pareados, con **precision / recall / F1 / accuracy** y gráfico de barras del F1 por equipo.
   - **Métricas de regresión (energía)** por equipo y global: **MAE/RMSE** de potencia (kW), **RE** (error relativo en la energía total acumulada, %) y **NEP** (error de potencia normalizado por la energía real).
   - **Métrica de transiciones / arranques (MEJORA #11)**: pareo greedy de los bordes OFF→ON de cada curva desagregada contra los eventos ON de referencia (tolerancia `max(60 s, 2·dt)`, cada referencia una sola vez) con **TP/FP/FN, precision/recall/F1** y desfase temporal (med/máx), en tarjetas globales y filas por equipo de la pestaña Validación — la métrica que más importa para el Gantt.
   - **Intervalos de confianza (MEJORA #12)**: bootstrap multinomial de 1000 iteraciones (semilla fija, reproducible) sobre las celdas de la matriz ON/OFF y de transiciones → **F1 = media ± mitad de anchura con rango [p2.5, p97.5]** en tarjetas de la pestaña Validación, en vez de un número seco.
10. **Diagnóstico de Calidad Energética (MEJORA #21)**:
    - Pestaña **🔎 Calidad Energética** (`GET /api/powerquality`): semáforo de cumplimiento EN 50160 / IEC 61000 / IEEE C57.110 para tensión (±10 %), desequilibrio, THD U/I, corriente de neutro, K-factor y frecuencia; curvas de tensión por fase, THD U + desequilibrio y neutro vs. fases; y tabla de eventos sostenidos de **sag/swell** con duración, tensión extrema, profundidad y fase más afectada.

## 🤖 Algoritmos de Inteligencia Artificial Disponibles

- **K-Means Clustering**: Agrupamiento óptimo por centroides multidimensionales con inicialización k-means++. El vector de features incluye los **saltos armónicos transitorios** (`|ΔH3|, |ΔH5|, |ΔH7|`) junto a `|ΔP|, |ΔI|, THD, |ΔQ|`, lo que separa electrónica de potencia de motores desde el propio clustering (ver `mejoras.txt`, mejora #5).
- **Selección automática de K (MEJORA #6)**: checkbox *⚡ Auto (K óptimo)* en el panel de análisis → `_auto_select_k()` barre KMeans con k = 2…8 (semilla fija 42) y propone el K de **mayor Silhouette** (empates resueltos por **menor Davies-Bouldin**); el informe `k_selection` expone el K propuesto, sus métricas y todos los candidatos, y una nota junto al slider muestra el resultado. Desactiva el slider manual y añade el parámetro `auto_k` en el servidor.
- **Gaussian Mixture Models (GMM)**: Modelado probabilístico con matrices de covarianza para capturar cargas con variabilidad de régimen.
- **DBSCAN**: Agrupamiento basado en densidad para identificar modos de operación atípicos o anomalías.
- ** Adjustable Trip Threshold **: Interactive current transient sensitivity selector ($\Delta I$ from 0.5 A to 10 A).

---

## 🧠 Opción A: Mejoras de IA y Desagregación

### 1. Modelado Multi-Estado (FHMM / HMM)
Actívelo con el interruptor **🧠 Multi-Estado (FHMM)** de la barra de control. En lugar de asumir estados binarios ON/OFF, el motor implementa un **Modelo Oculto de Markov Factorial**:

- **Estimación de niveles** (`estimate_machine_states`): los saltos de potencia de arranque (ΔP) de cada equipo se agrupan con K-Means + validación por silueta para detectar **estados intermedios** (ej. compresor en *Plena Carga* / *Marcha en Vacío* / *Apagado*).
- **Inferencia MAP factorial** (`disaggregate_load_fhmm`): la señal agregada se modela como la superposición `P_total(t) ≈ P_base + Σ nivel_c(estado_c(t))`. Se intentan dos estrategias en cascada:
  QUERY LENGTH LIMIT EXCEEDED. MAX ALLOWED QUERY : 500 CHARS
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
### 5. Benchmark de Algoritmos y Estabilidad de Umbrales (MEJORAS #9 y #10)
Pestaña **🏁 Benchmark**: re-ejecuta automáticamente el análisis (`/api/analyze`) con 6 configuraciones y compara las métricas de validación del PASO 3:

- **Comparativa de algoritmos**: K-Means, GMM, DBSCAN y FHMM (K-Means + FHMM activo) con los umbrales nominales de la sesión.
- **Estabilidad ±20%**: K-Means con `current_threshold`/`power_threshold` al −20% y +20%; se reporta F1 medio ± desviación típica y RE medio ± std (un CV alto = desagregación frágil frente al ajuste manual de umbrales).
- **Salidas**: tabla ordenada por F1 (MAE, RMSE, RE %, F1, accuracy, nº de eventos y tiempo de ejecución por configuración), gráfico de barras del F1 y resumen con la mejor configuración y el coeficiente de variación del F1. Todo se mide en el cliente (`performance.now()`) sin cambios en el backend.

### 6. Firmas Extendidas por Equipo (MEJORA #20)
Además de la firma armónica (ΔH3/ΔH5/ΔH7), cada evento incorpora tres rasgos nuevos que entran **dentro del vector de features del clustering** (junto a `|ΔP|, |ΔI|, THD, |ΔQ|, |ΔH3|, |ΔH5|, |ΔH7|`) y se exponen en la tabla de equipos y en las fichas técnicas:

- **cos φ medio y Δcos φ transitorio** (`cos(φ) L1..L3`): un motor de arranque directo arranca con cos φ ≈ 0.3–0.5 y sube al cargar; una resistencia mantiene cos φ ≈ 1; un variador mantiene cos φ alto con PF penalizado por el THD.
- **Ratio de inrush** (`|ΔI| / I_previa`, con `log1p` para compactar la cola): DOL ≈ 5–8×, VFD ≈ 1–1.5×, resistivo ≈ 1×.
- **Concentración de fase** (`max(|ΔI fase|) / Σ|ΔI fase|`): ≈ 1/3 = trifásico equilibrado, ≈ 1 = carga monofásica → la ficha indica *Monofásico (1 fase)*, *Asimétrico (2 fases)* o *Trifásico equilibrado*.

Reglas añadidas a `_classify_load_class`: `inrush ≥ 4×` con I ≥ 5 A → **Motor Inductivo (Arranque DOL)**; `inrush ≤ 1.6×` con cos φ ≥ 0.97 y P ≥ 1 kW → **Carga Resistiva**. El post-nombrado heurístico también aprovecha el inrush (`Motor DOL / Compresor (inrush ×N)`).
Salidas: `machine_statistics[].avg_cosphi / avg_inrush / phase_type`, `harmonic_signatures[]` y las columnas **Inrush ×**, **cos φ** y **Fases** de la tabla de equipos.

### 7. Diagnóstico de Calidad Energética (MEJORA #21)
Pestaña **🔎 Calidad Energética** (endpoint `GET /api/powerquality?dataset_id=…&max_points=600`, implementado en `DataManager.get_power_quality`):

- **Checks de cumplimiento** con semáforo ok/warn/bad: tensión ±10 %, desequilibrio de tensión (U2/U1 si el analizador lo exporta, o `(max−min)/media`; límite EN 50160 < 2 %), THD de tensión (< 8 % en LV), THD de corriente (informativo), corriente de neutro (< 50 % de la fase), K-factor (IEEE C57.110 < 4), frecuencia (50 Hz ± 0.5) y sags/swells.
- **Gráficos**: tensión por fase (U L1/L2/L3 frente al nominal detectado), THD de tensión + desequilibrio en eje % y corriente de neutro vs. fases (armónicos triplen de cargas monofásicas).
- **Tabla de eventos de tensión**: agrupa muestras contiguas con U < 90 % (sag) o > 110 % (swell) del nominal, con duración en minutos, tensión extrema, profundidad (%) y fase más afectada.
- Limitación explícita: el analizador exporta **medias**, por lo que se detectan depresiones sostenidas, no sags de medio ciclo.

## 📈 Roadmap de Análisis por Magnitud (catálogo 2026-09-21)

Catálogo de análisis posibles que aprovechan columnas ya presentes en los exports del analizador de redes. Lo marcado como **[HECHO]** ya está implementado en la plataforma.

### 1. Tensión (U) — columnas: U L1/L2/L3, U L12/L23/L31, U0/U1, U2/U1, CF U
- **[HECHO]** Detección de sags/swells sostenidos: U < 90 % o > 110 % del nominal con duración, correlacionada con tus eventos ΔI/ΔP ya detectados → identifica qué equipo provoca la caída de tensión al arrancar (carga DOL grande). ⚠️ Limitación honesta: el PQM exporta medias, no formas de onda, así que se capturan depresiones sostenidas, no sags de medio ciclo.
- **[HECHO]** Desequilibrio de tensión (U2/U1 %): límite IEC 2 %; correlación con el reparto de corrientes → recomendación concreta de rebalanceo de cargas monofásicas.
- Sag de red vs. caída interna: si U cae sin salto de carga → problema externo de red; si cae junto a ΔI > 0 → arranque interno (separación automática de causas). *(pendiente)*
- CF de tensión anómalo → detección de notching/clipping en el bus. *(pendiente)*

### 2. Variación de corriente (I) — columnas: I *L1/L2/L3, I *N, I0/I1, I2/I1, CF I
- **[HECHO]** Ratio de inrush (ΔI / I previa por evento): DOL ≈5–8×, VFD ≈1–1.5×, resistivo ≈1× → entra al vector de features del clustering y a `_classify_load_class` (MEJORA #20). Nota metodológica: con medias de 10 s el pico real de un DOL se subestima (el transitorio dura < 2 s), así que el ratio se mide como ΔI sostenido frente a la corriente previa, no como I_pico/I_estable.
- **[HECHO]** Monofásico vs. trifásico: un salto de I en una sola fase = carga monofásica; en las 3 = trifásica → nuevo rasgo `phase_concentration` para el clustering y campo `phase_type` en las fichas de equipo (MEJORA #20).
- **[HECHO]** Neutro: I *N + confirmación de riesgo por triplen en el check de calidad (I *N > 50 % de la fase → `warn`; en este registro 16.4 A = 54 % de la fase) (MEJORA #21).
- I2/I1 (secuencia negativa) → desbalance de consumo. *(pendiente)*
### 3. Potencia (P, Q, S) — columnas: P Lx, Q1 Lx, S Lx, Sn Lx
- **[HECHO]** Desagregación bidimensional P+Q con el FHMM (hmmlearn): observación [P, Q] en vez de solo P → separa calentador de motor con idéntica P (MEJORA #1).
- Potencia de distorsión D = √(S² − P² − Q1²): el "kVA fantasma" que penalizan las tarifas; estimable por equipo vía ΔD en cada evento. *(pendiente)*
- Benchmark NILMTK real: convertir el DataFrame a HDF5 de NILMTK y correr CombinatorialOptimisation + FHMM oficiales + nilmtk.metrics → añadir "nilmtk-CO" como algoritmo extra en la pestaña 🏁 Benchmark. *(pendiente)*
- Curva de duración de carga y análisis de picos (dimensionamiento de contrato de capacidad). *(pendiente)*

### 4. Variación de cos φ — columnas: cos(φ) Lx, PF Lx, tg(φ)L+/C−/L−/C+
- **[HECHO]** Firma Δcos(φ) por evento: motor DOL arranca con cos φ≈0.3–0.5 y sube; VFD mantiene cos φ alto con PF bajo; una resistencia tiene PF = cos φ = 1 → `abs_delta_cosphi` entra al vector de features y `avg_cosphi` se expone por equipo y en las fichas (MEJORA #20). ⚠️ El analizador exporta `cos(φ) Lx` **con signo** (este registro trae L1/L2 negativas, consumo en cuadrante de exportación), por lo que el cos φ útil es el valor absoluto; si además existe `cos(φ) Σ`, promediarla con las fases distorsiona la firma.
- PF − cos(φ) = penalización armónica: PF incluye distorsión, cos(φ) solo desplazamiento → separa "reactiva clásica" de "reactiva por distorsión" por equipo. *(pendiente como indicador propio; ambas columnas ya están disponibles)*
- Detección de banco de condensadores: evento con ΔQ < 0 sin ΔP (vía tg(φ)C−) → auditar si la corrección del factor de potencia está bien graduada o hay sobrecompensación (reactiva exportada = dinero perdido). *(pendiente)*
### 5. Variación de distorsión — columnas: THD U Lx, THD I Lx/N, U/I H 1–50, K Lx
- **[HECHO]** K-factor (K Lx): derating de transformador por armónicos (IEEE C57.110) → "¿tu transformador soporta la carga actual?" (MEJORA #21). Se evalúa **solo sobre muestras con carga** (I ≥ 30 % del pico) y excluyendo la columna K del neutro: sin ese filtro el registro daba K máx = 327 (media 38) por artefactos en vacío; acotado a carga, la media es 3.8 y el máximo 22.
- **[HECHO]** THD U vs THD I: la pestaña de calidad muestra juntos el THD U del bus y el THD I de las fases con carga → distingue quién contamina el bus de quién solo padece la distorsión (MEJORA #21). El THD I se reporta con el mismo filtro de carga (IEEE 519 lo evalúa a carga nominal): pasa de 49.4 % a un valor de carga representativo.
- **[HECHO]** Frecuencia (f L1): desvío P95 frente a 50 Hz ± 0.5 (EN 50160) para etiquetar eventos externos de red (MEJORA #21).
- Vector espectral completo H1–H50 (hoy el resumen usa H1–H25): clasificación por distancia espectral → VFD (H5/H7/H11/H13), electrónica de IT (H3/H5), iluminación LED (H3); usar coseno de similitud lo hace discriminativo. *(pendiente — las columnas H1–H50 ya están en el dataset)*
- THD I % vs % de carga: si el THD I crece a carga parcial → electrónica con filtro mal dimensionado. *(pendiente)*

### Roadmap priorizado (valor/esfuerzo)
1. **[HECHO]** Pestaña "Calidad de Energía" (`/api/powerquality`): sags, desequilibrio, THD U/I, neutro, K-factor — 100 % cálculo con columnas ya presentes, sin dependencias nuevas (MEJORA #21).
2. **[HECHO]** Firmas extendidas en el clustering: Δcos(φ), ratio de inrush y balance de fases en la matriz de features → sube el F1 de la desagregación con lo que ya existe (MEJORA #20).
3. **[HECHO]** FHMM bidimensional P+Q — mejora la separación de equipos con la misma P (MEJORA #1).
4. Sag de red vs. caída interna, banco de condensadores y curva de duración de carga: los tres siguen siendo cálculo puro sobre columnas existentes.
5. Instalar NILMTK y añadir CO/FHMM-oficial + métricas `nilmtk.metrics` al Benchmark — es el único punto que requiere instalar dependencia (con riesgo de fricción con pandas 3.x; el motor propio seguiría siendo el principal).

---

## 🔎 Criterio de Cumplimiento del Informe de Calidad (MEJORA #21)

El registro del analizador de redes tiene una **carga de fondo muy variable**, de modo que evaluar los límites normativos con el máximo absoluto produce falsas alarmas. `get_power_quality` devuelve, junto a cada check, el percentil 95 de la magnitud y el método aplicado (campo `method`):

| Magnitud | Criterio | Por qué |
|---|---|---|
| Tensión (±10 %), desequilibrio, THD U, frecuencia | **Percentil 95** (EN 50160 exige que el 95 % de las muestras de 10 min cumplan) | El máximo puntual (12.1 % de desvío en un solo instante) no implica incumplimiento |
| THD I, K-factor | Solo **muestras con carga** (I ≥ 30 % del pico), sin la columna del neutro | IEEE 519 / C57.110 se evalúan a carga nominal; en vacío K y THD I se disparan sin significado operativo |
| Neutro | Máximo frente al 50 % de la corriente de fase | El pico del neutro es el riesgo real (sobrecarga por triplen) |
| Sags/swells | Eventos agrupados de muestras contiguas fuera de ±10 % | Coherente con la detección de arranques DOL |

Diagnóstico del registro real: **cumple** tensión, desequilibrio, THD U y frecuencia; **atención** en neutro (54 % de la fase) y 5 eventos de sag; **alerta** en K-factor (P95 11.1 frente al límite 4) y THD I → hay electrónica de potencia contaminando el bus y el transformador opera con derating por armónicos.