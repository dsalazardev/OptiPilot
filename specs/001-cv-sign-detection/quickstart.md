# Quickstart — Validación del módulo de visión PARE/SIGA

**Feature**: `specs/001-cv-sign-detection` | **Date**: 2026-09-24

Guía para validar el módulo de extremo a extremo. Referencias: [spec.md](./spec.md),
[data-model.md](./data-model.md), [contracts/](./contracts/). Los comandos existen una vez
implementada la feature (ver `tasks.md`).

## Prerequisites

- Windows 11 con el repositorio clonado; `uv` ≥ 0.12 disponible (`uv --version`).
- Para corridas sobre video: archivos de práctica en `videos/` (no versionados; el Drive del reto o
  grabaciones propias). Sin video, la validación sintética funciona completa.
- No se requiere cámara, GUI ni `pip`.

## Setup

```powershell
uv sync                                  # crea/actualiza .venv con las dependencias de pyproject.toml
uv run python -c "import cv2; print(cv2.__version__)"   # esperado: 4.13+ (headless)
```

## Pruebas (headless, sin hardware)

```powershell
uv run pytest -q                         # unitarias + integración sintética (por defecto)
$env:OPTIPILOT_VIDEO_DIR = "C:\ruta\a\videos"
uv run pytest -m footage -q              # validación con footage real (opcional)
uv run pytest -m perf -q                 # benchmark de latencia (no bloqueante)
```

## Corrida de demostración

```powershell
.venv\Scripts\python.exe -m src.main --fuente videos\pista_practica.mp4 --config config\vision.json --diagnostico --salida salidas\demo_01
```

**Resultado esperado**: resumen en consola (fotogramas procesados, ocurrencias PARE/SIGA, paradas,
latencias) y en `salidas\demo_01\`: `eventos.jsonl`, `metricas.json` y `frames/` con las etapas
anotadas. Código de salida `0`.

## Escenarios de validación

| # | Escenario (spec) | Comando / entrada | Resultado esperado |
|---|------------------|-------------------|--------------------|
| 1 | US1 — detección y clasificación (P1) | `uv run pytest tests/unit/test_deteccion_confirmacion.py tests/unit/test_candidatos.py -q` | Octágonos rojo/verde sintéticos confirmados en ≤ 3 fotogramas; escenas sin señales y objetos no octogonales ⇒ 0 detecciones |
| 2 | US2 — máquina de estados (P2) | `uv run pytest tests/unit/test_maquina_estados.py -q` | Los 9 escenarios de US2 (incluye co-visible, SIGA antes de T, PARE nuevo durante detención, pérdida ≤ K) |
| 3 | US3 — máscara de línea (P3) | `uv run pytest tests/unit/test_segmentacion.py -q` y corrida con `-m footage` | Máscara de línea estable; reporta «no detectado» sin excepción; IoU ≥ 0.60 en el subconjunto anotado |
| 4 | US4 — evidencia y métricas (P3) | corrida demo con `--diagnostico` | `eventos.jsonl`, `metricas.json` y anotaciones por etapa generados; contadores coherentes con la entrada |

## Criterios de aceptación (verificación por corrida)

- **SC-001/SC-002**: 100 % de ocurrencias anotadas detectadas y clasificadas (comparar
  `metricas.json` contra la anotación de referencia).
- **SC-003/SC-004**: 0 confusiones PARE↔SIGA y 0 falsos positivos que provoquen decisiones; una
  corrida sin señales produce 0 detecciones confirmadas.
- **SC-005**: confirmaciones estables ante pérdidas ≤ 2 fotogramas.
- **SC-006**: latencia ≤ 8 fotogramas desde visibilidad plena; el robot se detiene antes de la señal
  (validar en pista con la capa de control).
- **SC-007**: latencia de procesamiento ≤ 33 ms por fotograma (referencia 30 fps).
- **SC-008/SC-009**: parada ≥ T con tolerancia ± 0.3 s; reanudación ≤ 5 fotogramas tras la condición
  (T cumplido y SIGA armado).
- **SC-010**: IoU de línea ≥ 0.60 en el subconjunto anotado (marcador `footage`).
- **SC-011/SC-012**: 0 intervenciones por errores de detección/estado; evidencia visual por etapa.

## Protocolo de evaluación (T030)

Este protocolo define **cómo se mide cada criterio** y en **qué entorno**. La Regla de Oro es
una sola: *un número sin denominador declarado no se publica*. Si un criterio no se puede
medir en el entorno disponible, se reporta **NO EVALUABLE** con la razón concreta, nunca 0 ni
una estimación.

El formato y el procedimiento de la anotación de referencia (máscara de línea y señales) están
definidos en [`contracts/anotacion-referencia.md`](./contracts/anotacion-referencia.md). Ninguna
evaluación es válida si no cumple sus cinco condiciones de validez (§4 de ese contrato).

### Entornos de validación

| Entorno | Qué representa | Corpus | Estado |
|---------|----------------|--------|--------|
| **SINT** | Escenario controlado: fondo uniforme, línea conocida, octágonos de radio y posición conocidos, ruido gaussiano controlado | `tests/fixtures/generador_sintetico.py`, 640×480 | **Operativo** — es el único entorno donde todos los criterios son evaluables |
| **PERF** | Coste computacional: presupuesto de latencia | fotogramas sintéticos, marcador `perf` | **Operativo** |
| **FOOT** | Footage real de práctica (9 videos, 478×850 vertical) | `documents/videos/VideosPruebaRobotSeguidorLinea/` | **Parcial** — el video se procesa, pero su geometría no es la del robot (ver §27 de `AGENTS.md`) |

Un resultado obtenido en SINT **no** se extrapola a FOOT, y FOOT **no** sustituye a SINT. Se
reportan por separado y en esa forma.

### Criterios por entorno

Leyenda: **CUMPLE** / **NO CUMPLE** / **NO EVALUABLE** (con la razón).

| Criterio | Qué mide | SINT | FOOT | Observado (2026-09-28) |
|----------|----------|------|------|------------------------|
| SC-001 | Reconocimiento de PARE, 100 % de ocurrencias | **CUMPLE** — `test_candidatos.py`, `test_deteccion_confirmacion.py` | **NO EVALUABLE** — sin `anotacion_linea.json`/ocurrencias anotadas | 0 confirmaciones en los 9 videos reales |
| SC-002 | Reconocimiento de SIGA, 100 % | **CUMPLE** — ídem | **NO EVALUABLE** — ídem | 0 confirmaciones |
| SC-003 | 0 confusiones PARE↔SIGA | **CUMPLE** — `test_escenarios_estado.py` | **NO EVALUABLE** — sin ground truth | 0 confusiones *y* 0 detecciones: no es evidencia |
| SC-004 | 0 falsos positivos que provoquen decisión | **CUMPLE** — escena sin señales ⇒ 0 detecciones | **NO EVALUABLE** — sin ground truth | 0 falsos positivos, pero tampoco detecciones: no es concluyente |
| SC-005 | Confirmación estable ante pérdidas ≤ K (2) | **CUMPLE** — `test_deteccion_confirmacion.py`, `test_escenarios_estado.py` | **NO EVALUABLE** | — |
| SC-006 | Parada antes de la señal (≤ 8 fotogramas) | **NO EVALUABLE** — requiere la capa de control y la pista | **NO EVALUABLE** | La FSM no gobierna motores |
| SC-007 | Latencia ≤ 33 ms/fotograma (30 fps) | **CUMPLE** — `test_rendimiento.py` (`perf`) | **CUMPLE** | SINT p95 ≈ 4 ms · FOOT p95 **2.98–3.88 ms** (9 videos) |
| SC-008 | Parada ≥ T, tolerancia ± 0.3 s | **CUMPLE** — `test_pipeline_fotogramas.py` cronometra T | **NO EVALUABLE** | `t_parada_s = 3.0` es **provisional**, no un valor del docente |
| SC-009 | Reanudación ≤ 5 fotogramas tras T y SIGA | **CUMPLE** — `test_escenarios_estado.py` rearme | **NO EVALUABLE** | — |
| SC-010 | IoU de línea ≥ 0.60 | **NO EVALUABLE** — no hay corpus anotado | **NO EVALUABLE** — ídem | La maquinaria (`test_footage_linea.py`) existe y valida el contrato; sin máscaras no hay número. **Techo medido: 0.125** contra una referencia sintética de 3 px, porque la máscara actual predice la línea a 24 px (§27.12 de `AGENTS.md`) |
| SC-011 | 0 intervenciones humanas | **CUMPLE** por construcción (sintético) | **NO EVALUABLE** — sin robot | Ver protocolo de intervenciones abajo |
| SC-012 | Evidencia visual por etapa | **CUMPLE** — `--diagnostico` genera `frames/` | **CUMPLE** | Artefactos generados en los 9 videos |

**Lectura honesta de la tabla**: hoy el sistema es **demo reproducible y medible en escenario
controlado**, y **no está validado en pista**. Eso es exactamente lo que la rúbrica pide poder
explicar (criterio 11, *Análisis de resultados*): los límites son parte del resultado, no un
defecto que esconder.

### Registro de intervenciones (SC-011)

SC-011 mide si el robot requirió intervención humana. Como hoy no hay capa de control, el
registro se prepara para cuando la haya, y se documenta como **no evaluable** hasta entonces.

Para cada corrida en pista se anota una fila:

| Corrida | Fecha | Intervenciones | Motivo | Fotograma | Tiempo (s) | Acción tomada |
|---------|-------|----------------|--------|-----------|------------|--------------|
| — | — | — | — | — | — | *(sin datos: no hay corrida en pista registrada)* |

Criterio: **0 intervenciones** atribuibles a fallo de detección o de estado. Una intervención por
problema mecánico o eléctrico se registra pero **no cuenta** contra SC-011; se distingue en la
columna *Motivo* precisamente para que la cifra sea auditable y no una afirmación.

### Criterio de ajuste si la latencia excede el presupuesto

`presupuesto_latencia_frames = 8` y `fps_objetivo = 30.0` fijan el presupuesto (≈ 266.7 ms por
fotograma). Si una corrida lo excede, se ajusta **en este orden**, parando en el primer paso que
restablezca el cumplimiento:

1. **Reducir `kernel_morfologico_px`** y el área de `roi_senales` — es lo más barato y no afecta
   la lógica de estado.
2. **Reducir el número de candidatos** subiendo `area_minima_rel` o `aspecto_min`/`aspecto_max`:
   el coste está en `findContours` + `approxPolyDP`, no en la FSM.
3. **Recortar `n_confirmacion`** — **no recomendado**: es un parámetro de seguridad del robot
   (evita falsos positivos con una sola confirmación) y recortarlo degrada SC-005.
4. Si persiste, **reducir resolución de captura** antes que simplificar el algoritmo, porque
   retirar una etapa del pipeline rompe la trazabilidad exigida por el criterio 5 de la rúbrica
   (*uso de técnicas de visión artificial* justificado).

En ningún caso se recurre a técnicas prohibidas (§11 de `AGENTS.md`) para ganar latencia.

### Resultados observados de esta validación

```text
Suite completa          : 167 passed, 5 skipped (opt-in)          → §18 de AGENTS.md
Benchmark (perf)        : 14 passed, 158 deselected
Footage (opt-in)        : 2 passed, 3 skipped (sin anotación)
CLI, 9 videos reales    : 690+399+337+543+165+133+187+149+127 fotogramas
                          PARE=0  SIGA=0  en los 9 videos
                          latencia p95 = 2.98 – 3.88 ms/fotograma
                          fps promedio reportado = 25.13 (video1)
```

Las dos últimas cifras requieren una aclaración para no malinterpretarlas:

- **`fps promedio = 25.13` no es el rendimiento del pipeline.** Es `fotogramas / t_último`, donde
  `t_último` es la marca de tiempo *nominal* del último fotograma según el FPS declarado del video.
  El video se decodifica más rápido de lo que se reproduce. El coste real por fotograma es el de
  **latencia proc.**, que sí se mide con reloj: p95 ≈ 3 ms.
- **0 detecciones de PARE/SIGA en footage real no es un fallo de `approxPolyDP`.** Un barrido con
  umbrales relajados encuentra 305 contornos que ya cumplen el criterio de forma (7–9 vértices,
  aspecto 0.7–1.4), pero **304 de ellos están fuera de `roi_senales`**, que cubre el 60 % superior
  del fotograma mientras el footage se grabó mirando hacia abajo. Es un desajuste de calibración
  de las Fases 3–5, deliberadamente **no** corregido aquí: T027 mide, no repara el pipeline.

## Solución de problemas

| Síntoma | Causa probable | Acción |
|---------|----------------|--------|
| `ModuleNotFoundError: cv2` | Dependencias no sincronizadas | `uv sync` y repetir |
| Fuente no encontrada (exit 2) | Ruta de video/ruta de imágenes inválida | Verificar `--fuente`; colocar archivos en `videos/` |
| Máscara vacía en pista real | Rangos HSV provisionales | Ajustar `config/vision.json` (calibración con footage) |
| 0 detecciones de PARE/SIGA en video | `roi_senales` no cubre la zona donde aparecen las señales | Revisar la geometría de la cámara y las ROIs antes de tocar `approxPolyDP` (§27.11 de `AGENTS.md`) |
| `SKIPPED ... ningún video trae anotacion_linea.json` | Footage presente pero sin corpus anotado | Pintar las máscaras según `contracts/anotacion-referencia.md` §2.2; el test hace skip **a propósito** para no inventar un número |
| Parada más larga de lo esperado | SIGA no detectado (fallo seguro por diseño) | Revisar rango verde y calibrar; analizar `eventos.jsonl` |
| Latencia > presupuesto | ROI grande o resolución alta | Seguir el criterio de ajuste de arriba; medir con `-m perf` |
