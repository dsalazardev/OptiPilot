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

## Solución de problemas

| Síntoma | Causa probable | Acción |
|---------|----------------|--------|
| `ModuleNotFoundError: cv2` | Dependencias no sincronizadas | `uv sync` y repetir |
| Fuente no encontrada (exit 2) | Ruta de video/ruta de imágenes inválida | Verificar `--fuente`; colocar archivos en `videos/` |
| Máscara vacía en pista real | Rangos HSV provisionales | Ajustar `config/vision.json` (calibración con footage) |
| Parada más larga de lo esperado | SIGA no detectado (fallo seguro por diseño) | Revisar rango verde y calibrar; analizar `eventos.jsonl` |
| Latencia > presupuesto | ROI grande o resolución alta | Reducir ROI / preprocesar; medir con `-m perf` |
