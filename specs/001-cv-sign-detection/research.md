# Phase 0 — Research: Módulo de Procesamiento de Imagen y Detección de Señales PARE/SIGA

**Feature**: `specs/001-cv-sign-detection` | **Date**: 2026-09-24

Resolución de incógnitas técnicas del Technical Context y decisiones de diseño previas a la Fase 1.

## R1. Biblioteca de visión: OpenCV headless para Python 3.14

- **Decision**: usar `opencv-python-headless` ≥ 4.13 (a 2026-07, la serie 4.14.0.9x está publicada).
- **Rationale**: los wheels oficiales declaran soporte de Python 3.14 (classifier `Programming
  Language :: Python :: 3.14` y wheels `cp314`/abi3), por lo que no hay compilación desde fuente;
  la variante *headless* evita GUI (el procesamiento y las pruebas son sin ventana) y reduce
  dependencias del sistema. OpenCV se usa **solo como biblioteca de primitivas permitidas** (color,
  umbralización, morfología, contornos, aproximación poligonal, Canny); la lógica de detección es
  propia (Principio I).
- **Alternatives considered**:
  - `opencv-python` (con GUI): rechazado — GUI innecesaria y problemática en headless.
  - `opencv-contrib-python`: rechazado — módulos extra no requeridos; algunos (ArUco, QR, DNN)
    automatizan detección y quedan prohibidos por Reto 1.
  - Compilar desde fuente: rechazado — sin wheels implicaría toolchain C++ y riesgo de
    irresproducibilidad.
- **Nota de cumplimiento**: prohibido usar en el pipeline cualquier submódulo de OpenCV que detecte
  automáticamente línea o señales (DNN, ArUco, QR, `HoughCircles` como detector de señales, etc.).

## R2. Gestión de dependencias y reproducibilidad (uv)

- **Decision**: declarar dependencias en `pyproject.toml` (`[project].dependencies` y grupo dev PEP
  735), marcar `[tool.uv] package = false` (proyecto virtual, no se instala el paquete `src`),
  instalar con `uv sync` y **versionar `uv.lock`**; documentarlo en `AGENTS.md`.
- **Rationale**: el venv no tiene `pip`; uv 0.12.18 ya está disponible; `uv sync` + lockfile da
  reproducibilidad exacta (Principio III) y no requiere configurar un backend de build para un
  paquete que se ejecuta desde el repositorio (`python -m src.main`). La constitución permite
  adoptar lockfile si se documenta.
- **Alternatives considered**:
  - `uv pip install` sin lock: rechazado — instalación no reproducible.
  - `pip` + `requirements.txt`: rechazado — pip no existe en el venv y duplicaría la declaración.
  - Paquete instalable (`package = true` con setuptools): rechazado — aporta complejidad de build
    sin beneficio para este proyecto académico.

## R3. Formato de configuración (parámetros centralizados)

- **Decision**: JSON estándar (`config/vision.json`) con valores por defecto embebidos en
  `configuracion.py`; override por archivo y por argumentos del CLI.
- **Rationale**: FR-024 exige parámetros centralizados, documentados y modificables sin tocar la
  lógica; JSON es stdlib, inspeccionable y no añade dependencias.
- **Alternatives considered**: YAML (dependencia extra PyYAML), TOML (solo lectura en stdlib y
  pensado para build), módulo Python (menos seguro y no editable en caliente).

## R4. Estrategia de segmentación por visión clásica

- **Decision**: segmentación por color en **HSV** con umbrales configurables; rojo con **dos
  intervalos de tono** por el wrap (0–10 y 170–179); verde en rango medio; **ROI independientes**
  para línea (zona inferior/central) y señales (zona alta); limpieza con **apertura y cierre**;
  descarte por **área mínima**; contornos externos; validación de octágono con **`approxPolyDP`**
  (8 vértices ± 1 de tolerancia), **relación de aspecto** de la caja (~1.0) y propiedades de
  contorno (área, perímetro, centroide).
- **Rationale**: todas son técnicas autorizadas y explicables etapa por etapa (rúbrica 5/9/12);
  HSV separa color de brillo, lo que da robustez razonable a iluminación; los dos rangos de rojo
  evitan perder el tono en el límite circular de H.
- **Alternatives considered**:
  - CIELab: más estable a iluminación en teoría, pero umbrales menos intuitivos de explicar;
    se deja como posible mejora futura (documentada en análisis de resultados).
  - K-Means básico (autorizado): no se usa en v1 — añade costo y requiere fijar semilla; la
    umbralización por color cubre la necesidad actual. Queda como alternativa permitida.
  - Canny: opcional como apoyo de validación de bordes; no imprescindible para el pipeline base.

## R5. Confirmación temporal y supresión de falsos positivos

- **Decision**: una señal se confirma tras **N = 3 fotogramas consecutivos** con candidato válido;
  se toleran pérdidas de hasta **K = 2 fotogramas** sin revocar la confirmación; la misma ocurrencia
  se **re-arma tras X = 5 fotogramas** sin verla. Los tres valores son configurables.
- **Rationale**: SC-005 y FR-011/FR-021; elimina parpadeos y ruido sin retrasar la detección más
  allá del presupuesto de latencia (8 fotogramas, SC-006).
- **Alternatives considered**: confirmación por tiempo en ms (depende de fps y complica pruebas);
  confirmación por un solo fotograma (frágil ante ruido).

## R6. Máquina de estados determinista PARE/SIGA

- **Decision**: tres estados observables `EN_MARCHA`, `DETENIDO_MINIMO` (T en curso) y
  `DETENIDO_ESPERANDO_SIGA` (T cumplido); bandera `siga_armado`; cronómetro de parada; transiciones
  puras a partir de (`señales presentes`, `t`). Reglas implementadas (spec + clarificaciones):
  PARE confirmado detiene; T es mínimo y no reanuda por sí solo; cualquier SIGA confirmado durante
  la detención arma la reanudación (incluido el co-visible al detenerse); SIGA antes de T no
  adelanta la reanudación; PARE nuevo durante la detención no altera T ni el SIGA armado; PARE
  latcheado hasta su re-armado; pérdidas ≤ K no afectan la parada.
- **Rationale**: FR-015–FR-022 y las 4 clarificaciones de la spec; un módulo puro y determinista se
  prueba por inyección de secuencias (US2, 9 escenarios) sin cámara.
- **Alternatives considered**: máquina implícita dentro del pipeline (difícil de aislar y probar);
  temporizadores con hilos (no deterministas y prohibidos por simplicidad).

## R7. Fuente de fotogramas y testabilidad

- **Decision**: `src/vision/` es puro (fotograma → resultado, sin I/O); `src/main.py` implementa las
  fuentes: archivo de video (`cv2.VideoCapture`), directorio de imágenes y, a futuro, índice de
  cámara. Las pruebas no dependen de cámara ni de red.
- **Rationale**: separación de responsabilidades y pruebas headless deterministas; el hardware de
  captura está fuera de alcance (assumptions de la spec).
- **Alternatives considered**: leer la cámara dentro del pipeline (intesteable sin hardware);
  hilos productor/consumidor (complejidad prematura; el presupuesto de latencia se mide por
  fotograma).

## R8. Pruebas e integración continua local

- **Decision**: pytest headless. Unitarias por etapa con fixtures sintéticas (generador de
  octágonos/líneas con `cv2.fillPoly` y HSV controlado, ruido, rotación, escala); integración con
  secuencias sintéticas completas (incluye escenarios US2); corrida opcional sobre footage real vía
  variable `OPTIPILOT_VIDEO_DIR` (marcador `footage`); benchmark de latencia separado (marcador
  `perf`, no bloqueante en máquinas ajenas).
- **Rationale**: sin tests no hay validación posible de la lógica determinista (Principio V);
  fixtures sintéticas evitan depender de videos externos y hacen los casos borde reproducibles.
- **Alternatives considered**: unittest stdlib (menos ecosistema de fixtures/parametrización);
  videos de prueba versionados (peso y licencias; rechazado).

## R9. Métricas y evidencia por corrida

- **Decision**: por corrida se escriben `eventos.jsonl` (un evento por línea), `metricas.json`
  (resumen) y salidas de diagnóstico (fotogramas anotados o video). Las **ocurrencias** del registro
  se delimitan por re-armado; el **denominador de las tasas** de SC-001/002/003 es la anotación de
  referencia de señales físicas (clarificación Q3). Se registra latencia por decisión y duración de
  paradas.
- **Rationale**: FR-023/FR-025 y SC-012; formatos simples, diffeables y exportables al póster y al
  análisis de resultados.
- **Alternatives considered**: base de datos (innecesaria), CSV único (pierde estructura de eventos).

## R10. Entorno Windows 11 / OneDrive

- **Decision**: todas las salidas a `salidas/` (git-ignored); videos de validación en `videos/`
  (git-ignored); evitar rutas largas; `.pytest_cache/` ignorado.
- **Rationale**: el repositorio vive en OneDrive y el venv ya pesa cientos de MB; mantener binarios
  de prueba fuera del control de versiones evita sincronización innecesaria.

## Resolución de NEEDS CLARIFICATION

No quedan incógnitas en el Technical Context: cámara/hardware y canal de comunicación están fuera de
alcance por spec (assumptions); T se expone como parámetro configurable con valor provisional
documentado (`3.0 s`, pendiente de confirmación del docente); fps objetivo asumido en 30 (SC-006/007)
y validable en pista. La biblioteca elegida tiene soporte verificado para Python 3.14 (R1).
