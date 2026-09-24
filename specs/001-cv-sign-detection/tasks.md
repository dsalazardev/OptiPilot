# Tasks: Módulo de Procesamiento de Imagen y Detección de Señales PARE/SIGA

**Input**: Design documents from `/specs/001-cv-sign-detection/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Incluidos — solicitados por el usuario y exigidos por la constitución (Principio V: pruebas
headless de la lógica determinista).

**Organization**: fases lógicas solicitadas (fundamentos/contratos → pipeline de visión por etapas →
máquina de estados determinista → persistencia/métricas → pruebas de integración) con etiquetas de
historia de usuario para trazabilidad. Cada fase es un incremento verificable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/`, `tests/`, `config/` en la raíz del repositorio (ver plan.md §Project
  Structure). Rutas relativas a la raíz.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicialización de proyecto y estructura básica

- [X] T001 Añadir configuración de proyecto y dependencias en `pyproject.toml`: `dependencies = ["opencv-python-headless>=4.13", "numpy>=2.4"]`, `[dependency-groups] dev = ["pytest>=8"]`, `[tool.uv] package = false` y `[tool.pytest.ini_options]` con `pythonpath = ["."]`, `testpaths = ["tests"]` y `markers = ["footage", "perf"]`
- [X] T002 [P] Actualizar `.gitignore`: ignorar `salidas/`, `videos/` y `.pytest_cache/`; `uv.lock` NO se ignora (se versiona)
- [X] T003 Ejecutar `uv sync` y verificar la instalación con `uv run python -c "import cv2; print(cv2.__version__)"` (esperado ≥ 4.13); genera `uv.lock` (depende de T001)
- [X] T004 [P] Crear `config/vision.json` con los defaults exactos del contrato `contracts/esquema-configuracion.md` (incluye `t_parada_s: 3.0` provisional y rango de línea oscura provisional)

---

## Phase 2: Fundamentos y contratos (Blocking Prerequisites)

**Purpose**: Configuración, entidades y fixture base que bloquean todas las historias

**⚠ CRITICAL**: Ninguna fase de pipeline puede comenzar hasta completar esta fase

- [X] T005 Implementar `src/vision/__init__.py` y `src/vision/configuracion.py`: `ParametrosConfiguracion` (frozen) con los parámetros del contrato `contracts/esquema-configuracion.md` y sus validaciones verbatim (H 0–179; S/V 0–255; ROIs en [0,1] con `x+w ≤ 1` y `y+h ≤ 1`; `kernel_morfologico_px` impar ≥ 3; `0 < area_minima_rel < 1`; `n_confirmacion ≥ 1`; `k_tolerancia ≥ 0`; `x_rearme ≥ 0`; `t_parada_s ≥ 0`; `presupuesto_latencia_frames ≥ 1`; `fps_objetivo > 0`; `vertices_objetivo = 8`; `tolerancia_vertices ≥ 0`; `0 < aspecto_min ≤ aspecto_max`), `ConfiguracionInvalidaError(ValueError)` con campo y motivo, `cargar_parametros(ruta)` y `ParametrosConfiguracion.por_defecto()` (depende de T001)
- [X] T006 [P] Implementar entidades y enums compartidos en `src/vision/modelos.py` según `data-model.md`: enums `ClaseSenal`, `EstadoRobot` (EN_MARCHA/DETENIDO_MINIMO/DETENIDO_ESPERANDO_SIGA), `DecisionMovimiento`, `TipoEvento` y `CausaTransicion`; dataclasses `ResultadoSegmentacion`, `CandidatoSenal`, `SenalConfirmada`, `Ocurrencia`, `EventoSenal`, `TransicionEstado` y `ResultadoProcesamiento` con las restricciones del modelo (`area_px ≥ área mínima`; `caja w,h > 0`; `es_valido = 8±1 vértices y aspecto en [0.70, 1.40]`; `motivo_invalidez` presente si no es válido)
- [X] T007 [P] Implementar `tests/fixtures/__init__.py` y `tests/fixtures/generador_sintetico.py` (fotogramas BGR con octágonos rojo/verde, línea y ruido, con HSV, rotación y escala controlados) y `tests/conftest.py` (depende de T003)
- [X] T008 [P] Tests unit de configuración en `tests/unit/test_configuracion.py`: defaults, merge de JSON parcial y cada regla de validación produciendo `ConfiguracionInvalidaError` con campo y motivo (depende de T005, T007)

**Checkpoint**: Fundación lista — el pipeline puede comenzar

---

## Phase 3: Pipeline de visión por etapas (US1 · US3)

**Goal**: Procesar fotogramas en un pipeline clásico por etapas que produce las máscaras de línea y
señales, los candidatos de octágonos y las detecciones confirmadas PARE/SIGA.

**Independent Test**: con el generador sintético, un octágono rojo/verde se confirma en ≤ 3
fotogramas; escenas sin señales u objetos no octogonales producen 0 detecciones; la máscara de línea
aísla la línea sintética y reporta «no detectado» sin excepción.

- [ ] T009 [US1] Implementar `src/vision/preprocesamiento.py`: suavizado Gaussiano, conversión BGR→HSV y recorte por ROIs normalizadas (línea y señales); documentar en docstrings la técnica clásica de OpenCV usada y su propósito (Constitución §II) (depende de T005, T006)
- [ ] T010 [US1] Implementar `src/vision/segmentacion.py`: máscaras binarias a tamaño completo (línea; rojo con los dos rangos de tono 0–10 y 170–179; verde), apertura y cierre con `kernel_morfologico_px`; fotograma sin línea o sin candidatos ⇒ máscaras vacías sin excepción (FR-014); documentar en docstrings la técnica clásica de OpenCV usada y su propósito (Constitución §II) (depende de T009)
- [ ] T011 [US1] Implementar `src/vision/candidatos.py`: contornos externos, descarte de `area_rel < area_minima_rel`, `approxPolyDP` (tolerancia ~2–4 % del perímetro), `n_vertices` en 8±`tolerancia_vertices`, aspecto en [`aspecto_min`, `aspecto_max`], centro/área/caja y `es_valido` con `motivo_invalidez`; documentar en docstrings la técnica clásica de OpenCV usada y su propósito (Constitución §II) (depende de T010)
- [ ] T012 [US1] Implementar `src/vision/deteccion.py`: clasificación PARE/SIGA según la máscara de origen; confirmación tras `n_confirmacion = 3` fotogramas consecutivos tolerando `k_tolerancia = 2` pérdidas; emisión de `SenalConfirmada` en flanco de subida; ciclo de vida de `Ocurrencia` con re-armado a los `x_rearme = 5` fotogramas; eventos `SENAL_PERDIDA` y `PARE_REARMADO`; documentar en docstrings la técnica clásica de OpenCV usada y su propósito (Constitución §II) (depende de T011, T006)
- [ ] T013 [US1] Implementar `src/vision/pipeline.py`: `PipelineVision(params).procesar(indice, t_s, imagen_bgr) -> ResultadoProcesamiento` componiendo preprocesamiento→segmentación→candidatos→detección, con `latencia_ms` vía `time.perf_counter`; expone el marcador de visibilidad plena por señal (primer fotograma completamente dentro de la ROI y área ≥ mínima — Q2/SC-006); determinista; fotograma vacío ⇒ resultado vacío sin excepción; documentar en docstrings la técnica clásica de OpenCV usada y su propósito (Constitución §II) (depende de T012)
- [ ] T014 [P] [US1] Tests de segmentación en `tests/unit/test_segmentacion.py`: máscaras roja/verde sobre fixtures sintéticas, ruido suprimido por morfología y escena sin señales ⇒ máscaras vacías (depende de T010, T007)
- [ ] T015 [P] [US1] Tests de candidatos en `tests/unit/test_candidatos.py`: octágonos válidos; objetos rojos/verdes no octogonales descartados; área mínima y aspecto fuera de rango con `motivo_invalidez` (depende de T011, T007)
- [ ] T016 [P] [US1] Tests de detección y confirmación en `tests/unit/test_deteccion_confirmacion.py`: confirmación en ≤ 3 fotogramas; pérdidas ≤ 2 no revocan; re-armado a los 5 fotogramas; sin confusión PARE↔SIGA (depende de T012, T007)
- [ ] T017 [US3] Añadir escenarios de línea en `tests/unit/test_segmentacion.py`: la máscara aísla una línea sintética, fotograma sin línea ⇒ máscara vacía y «no detectado», sombra/ruido no rompen la máscara (depende de T014)

**Checkpoint**: US1 y US3 funcionales y verificables de forma independiente

---

## Phase 4: Máquina de estados determinista (US2)

**Goal**: Decidir `AUTORIZADO`/`NO_AUTORIZADO` con parada por T mínimo y reanudación exclusiva por
SIGA confirmado, de forma pura y determinista.

**Independent Test**: inyectando secuencias de detecciones y tiempos, los 9 escenarios de US2
(spec §User Story 2) producen las transiciones esperadas y ningún re-disparo.

- [ ] T018 [US2] Implementar `src/vision/maquina_estados.py`: `MaquinaEstados(params, t_inicial)` con `actualizar(presentes, eventos, t_s) -> ResultadoEstado` (estado, decisión y `transiciones_nuevas` con origen, destino, causa y momento — FR-023); reglas: PARE nuevo detiene; T es mínimo y no reanuda por sí solo; cualquier SIGA confirmado durante la detención arma la reanudación (incluido el co-visible al detenerse); PARE nuevo durante la detención no reinicia T ni invalida el SIGA armado; PARE latcheado hasta re-armado; pérdidas ≤ K no afectan (depende de T006, T005)
- [ ] T019 [P] [US2] Tests de la máquina de estados en `tests/unit/test_maquina_estados.py`: los 9 escenarios de `spec.md` §User Story 2, más invariantes (en DETENIDO_* siempre `NO_AUTORIZADO`; misma secuencia ⇒ mismas transiciones) (depende de T018)

**Checkpoint**: US2 funcional y verificable sin cámara

---

## Phase 5: Persistencia, métricas y evidencia (US4)

**Goal**: Registrar y exportar métricas por corrida y generar evidencia visual por etapa a través de
un CLI de validación.

**Independent Test**: una corrida sobre footage sintético produce `eventos.jsonl`, `metricas.json` y
fotogramas anotados con contadores coherentes; el resumen nunca omite claves.

- [ ] T020 [US4] Implementar `src/vision/metricas.py`: `MetricasCorrida` con registro de fotogramas, eventos, señales, paradas, latencias y transiciones (`registrar_transicion`); calcula la latencia de decisión por ocurrencia desde el marcador de visibilidad plena hasta la decisión emitida (fotogramas y ms — Q2/SC-006); `resumen()`; `exportar(directorio)` escribiendo `eventos.jsonl` (una línea por evento, incluidas las transiciones con tipo `TRANSICION`) y `metricas.json` conforme a `contracts/esquema-eventos-metricas.md` (claves nunca omitidas; `retardo_s` = espera de SIGA tras T) (depende de T006)
- [ ] T021 [P] [US4] Implementar `src/vision/visualizacion.py`: `anotar(imagen_bgr, resultado, estado=None) -> np.ndarray` dibujando máscaras, contornos, clase, estado y decisión; devuelve copia y no guarda (depende de T006)
- [ ] T022 [US4] Reemplazar el sample por el CLI de validación en `src/main.py`: `--fuente` (video/directorio/índice), `--config`, `--diagnostico`, `--salida`, `--max-fotogramas`; compone pipeline + máquina + métricas (volcado de transiciones y decisiones incluido); códigos de salida 0/1/2 (contrato `api-pipeline.md`); resumen en consola y anotados en `salidas/<corrida>/frames/` (depende de T013, T018, T020, T021)
- [ ] T023 [P] [US4] Tests unit de métricas en `tests/unit/test_metricas.py`: conteos de ocurrencias, `retardo_s`, claves en 0/listas vacías y una línea JSON por evento, incluidas las transiciones `TRANSICION` (depende de T020)

**Checkpoint**: US4 funcional — la corrida de validación produce evidencia completa

---

## Phase 6: Pruebas de integración y validación (Cross-cutting)

**Goal**: Verificar el sistema completo de extremo a extremo sobre secuencias y artefactos.

**Independent Test**: la suite `uv run pytest -q` pasa completa en entorno headless sin cámara; los
marcadores `footage` y `perf` se ejecutan por separado y no bloquean.

- [ ] T024 [US1] Test de integración del pipeline en `tests/integration/test_pipeline_fotogramas.py`: secuencia sintética completa (línea + PARE + SIGA) encadenando `PipelineVision` → `MaquinaEstados` → `MetricasCorrida`; verifica detecciones, decisiones y resumen (depende de T013, T018, T020)
- [ ] T025 [P] [US2] Test de integración de escenarios de estado en `tests/integration/test_escenarios_estado.py`: co-visible, SIGA antes de T, PARE nuevo durante la detención y pérdida ≤ K sobre secuencias end-to-end (depende de T018)
- [ ] T026 [P] [US4] Test de la corrida demo en `tests/integration/test_corrida_demo.py`: genera un video sintético temporal, ejecuta el CLI por `subprocess` y verifica artefactos (`eventos.jsonl`, `metricas.json`, frames) y código de salida 0 (depende de T022)
- [ ] T027 [P] [US3] Test de línea con footage real en `tests/integration/test_footage_linea.py`: marcado `footage`, opt-in por `OPTIPILOT_VIDEO_DIR`; verifica la máscara de línea y el reporte «no detectado»; exige IoU promedio ≥ 0.60 solo si hay anotación y hace skip limpio si no hay footage (depende de T010, T007)
- [ ] T028 [P] Benchmark de latencia en `tests/integration/test_rendimiento.py`: marcado `perf`; mediana ≤ 33 ms por fotograma 640×480 sintético en 100 fotogramas; no bloqueante por defecto (depende de T013)

**Checkpoint**: Sistema completo verificado de extremo a extremo

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentación, protocolo de evaluación y validación final

- [ ] T029 [P] Actualizar `AGENTS.md`: comandos verificados (`uv sync`, `uv run pytest`, CLI), dependencias nuevas (`opencv-python-headless`, `pytest`), estado del proyecto y límites vigentes (depende de T003, T022)
- [ ] T030 Actualizar `specs/001-cv-sign-detection/quickstart.md` con el protocolo de evaluación (tamaño y criterio de anotación para SC-001/002/010, registro de intervenciones para SC-011 y criterio de ajuste si la latencia excede el presupuesto) y validar los comandos de extremo a extremo registrando los resultados observados (depende de T024, T026, T027)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias
- **Fundamentos (Phase 2)**: depende de Setup — BLOQUEA todas las historias
- **Pipeline (Phase 3, US1/US3)**: depende de Phase 2
- **Máquina de estados (Phase 4, US2)**: depende de Phase 2 (puede desarrollarse en paralelo con
  Phase 3 si hay capacidad)
- **Persistencia/métricas (Phase 5, US4)**: depende de Phase 2; T022 depende de T013 (US1) y T018 (US2)
- **Integración (Phase 6)**: depende de las fases 3–5 según la tabla de cada tarea
- **Polish (Phase 7)**: depende de las fases 3–6

### Task Dependencies (estrictas)

```text
T001 ─┬─▶ T003 ─▶ T007 ─┬─▶ T008
      └─▶ T005 ─┬───────┘
                └─▶ T009 ─▶ T010 ─▶ T011 ─▶ T012 ─▶ T013 ─▶ T014 ─▶ T017
                                                        ├─▶ T015
                                                        ├─▶ T016
                                                        ├─▶ T024
                                                        ├─▶ T026 (vía T022)
                                                        └─▶ T028
T006 ─┬─▶ T009 (con T005)   T006 ─▶ T018 ─▶ T019
      ├─▶ T012              T018 ─▶ T025
      ├─▶ T018              T020 ─▶ T023
      ├─▶ T020 ─▶ T022 (con T013, T018, T021)
      └─▶ T021 [P]
T004 (independiente)
T022 ─▶ T026;  T024, T026, T027 ─▶ T030
T003, T022 ─▶ T029
```

### Parallel Opportunities

- Setup: T002 y T004 en paralelo con T001/T003 (archivos distintos)
- Fundamentos: T006, T007 en paralelo tras T003; T005 y T006 en paralelo
- Tras Phase 2: Phase 3 (US1/US3) y Phase 4 (US2) pueden ir en paralelo por personas distintas
- Tests unitarios: T014, T015, T016 en paralelo (archivos distintos) y T019, T023 en paralelo
- Integración: T025, T026, T027, T028 en paralelo (archivos distintos)

---

## Parallel Example: Phase 3 + Phase 4 en paralelo

```text
# Persona A (pipeline de visión):
T009 → T010 → T011 → T012 → T013
# Persona B (máquina de estados, tras T006):
T018
# Tests en paralelo al cerrar cada módulo:
T014, T015, T016 (US1) · T019 (US2)
```

---

## Implementation Strategy

### MVP First (US1)

1. Phase 1 (Setup) → Phase 2 (Fundamentos)
2. Phase 3 (US1): pipeline con detección y confirmación PARE/SIGA
3. **VALIDAR**: `uv run pytest tests/unit/test_deteccion_confirmacion.py -q`
4. Demo: detección sobre un video con `PipelineVision` (aún sin CLI)

### Incremental Delivery

1. Setup + Fundamentos → pipeline por etapas (US1/US3) → validar
2. Máquina de estados (US2) → validar con T019/T025
3. Métricas + CLI (US4) → validar con T023/T026
4. Integración y benchmark → suite completa
5. Polish: `AGENTS.md` y quickstart con protocolo de evaluación

---

## Notes

- [P] = archivos distintos, sin dependencias pendientes
- Las etiquetas [US#] trazan cada tarea a la historia del spec (US1 detección, US2 máquina de
  estados, US3 línea, US4 evidencia/métricas)
- Todo el trabajo es headless y determinista; las pruebas no dependen de cámara ni de red
- Los parámetros provienen siempre de `config/vision.json` / `ParametrosConfiguracion`; ninguna tarea
  debe introducir constantes no configurables (constitución §IV, FR-024)
- No commitear `salidas/` ni `videos/`; `uv.lock` sí se versiona
- Ejecutar la suite antes de cerrar cada fase: `uv run pytest -q`
