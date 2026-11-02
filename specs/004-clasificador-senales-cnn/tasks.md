# Tasks: Clasificador CNN de Señales y Cadencia de Marcha

**Feature**: `004-clasificador-senales-cnn` | **Date**: 2026-11-02

**Input**: [spec.md](./spec.md), [plan.md](./plan.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

## Fase 1 — Exportación del modelo (proyecto de entrenamiento)

- [x] **T001** Crear `optipilot_classifier/exportar_onnx.py` con conversión `MobileNet.keras → .onnx`, metadata y verificación de paridad.
- [x] **T002** Instalar `tf2onnx`, `onnx` y `onnxruntime` en el Python 3.13 de entrenamiento.
- [x] **T003** Ejecutar `python exportar_onnx.py` y confirmar `max|Δ| < 1e-4` y top-1 `12/12` (resultado: 5.36e-07, 12/12).
- [x] **T004** Copiar `senales_mobilenet.onnx` y `senales_mobilenet.json` a `OptiPilot/assets/modelos/`.

**Criterio**: el artefacto existe, la metadata incluye clases/tamaño/preproceso/hash y la paridad es aceptable.

## Fase 2 — Runtime ONNX

- [x] **T005** Añadir `onnxruntime>=1.31` a `pyproject.toml` y registrar el marcador `cnn` en `[tool.pytest.ini_options]`; ejecutar `uv sync`.
- [x] **T006** Verificar `import onnxruntime` y una inferencia de humo en el venv 3.14.

## Fase 3 — Modelos y configuración

- [x] **T007** Añadir `ClaseSenalExtra`, `ModoMarcha`, `ColorRegion`, `PrediccionSenal`, `RegionSenal`, `ClasificacionCNN` y los campos opcionales de `CandidatoSenal`/`ResultadoProcesamiento` en `src/vision/modelos.py`.
- [x] **T008** Añadir `rango_hsv_amarillo` y los campos del clasificador/cadencia en `src/vision/configuracion.py`.
- [x] **T009** Añadir los valores por defecto y validaciones (HSV, umbral, área, intervalos).
- [x] **T010** Actualizar `config/vision.json`.

**Criterio**: `cargar_parametros` acepta la configuración nueva y rechaza valores inválidos con `ConfiguracionInvalidaError`.

## Fase 4 — Localizador clásico

- [x] **T011** Crear `src/vision/localizacion_senales.py` con máscaras rojo/verde/amarillo, morfología, contornos, área/aspecto, color de origen y supresión por IoU.
- [x] **T012** Tests unitarios con imágenes sintéticas: PARE rojo, SIGA verde, ZONA amarilla, VELOCIDAD con borde rojo y fotograma vacío.

**Criterio**: las 4 señales generan una región; el fondo no genera propuestas.

## Fase 5 — Clasificador ONNX

- [x] **T013** Crear `src/clasificacion/base.py` con el `Protocol ClasificadorSenales`.
- [x] **T014** Crear `src/clasificacion/onnx.py` con carga de sesión, metadata, preproceso MobileNet, mapeo de clases y cierre idempotente.
- [x] **T015** Tests unitarios con una sesión falsa: forma de entrada, preproceso, top-1, umbral y etiqueta desconocida.

**Criterio**: el adaptador funciona sin TensorFlow y no lanza ante imágenes inválidas.

## Fase 6 — Integración en el pipeline

- [x] **T016** Extender `PipelineVision.__init__` con `clasificador=None` y mantener el camino clásico intacto.
- [x] **T017** En `procesar`, localizar regiones, clasificar el contexto del fotograma, filtrar por confianza y coherencia color/forma, y construir `CandidatoSenal` para PARE/SIGA.
- [x] **T018** Confirmar clases extra (`n_confirmacion_extra`) y propagar `modo_marcha`.
- [x] **T019** Exponer `clasificaciones_cnn` (como `ClasificacionCNN`, con caja), `rechazadas_cnn` y `modo_marcha` en `ResultadoProcesamiento`.
- [x] **T020** Tests de integración con un clasificador falso: PARE, SIGA, ZONA y VELOCIDAD.

**Criterio**: sin clasificador, los tests existentes pasan; con clasificador falso, las 4 clases producen el comportamiento esperado.

## Fase 7 — Cadencia de marcha

- [x] **T021** Crear `src/vision/cadencia_marcha.py` con la lógica de intervalos y reinicio.
- [x] **T022** Tests unitarios: SIGA 1.0 s, ZONA 2.0 s, VELOCIDAD 0.5 s, primer `w` inmediato, PARE prioritario.
- [x] **T023** Integrar la cadencia en `_correr` de `src/main.py`, usando `t_s` y el modo del resultado, solo cuando el clasificador esté activo; con `off`, conservar `indice % fotogramas_por_orden`.
- [x] **T024** Asegurar que cualquier `DETENER` (veto de FSM, pérdida de línea o fallo seguro) se envía de inmediato con el clasificador activo, y que al reanudar el modo vuelve a SIGA.

**Criterio**: los intervalos medidos coinciden con la tabla y el PARE sigue deteniendo 3.0 s.

## Fase 8 — CLI y errores

- [x] **T025** Añadir `--clasificador`, `--modelo-senales`, `--metadatos-senales`.
- [x] **T026** Construir el clasificador al inicio; abortar con código 2 si se pidió ONNX y falla.
- [x] **T027** Verificar que `--clasificador off` no importa ONNX ni cambia el comportamiento.

## Fase 9 — Métricas y visualización

- [x] **T028** Registrar conteos por clase, confianza media, rechazos y modo final en `metricas.json`.
- [x] **T029** Dibujar caja, etiqueta y confianza de cada `ClasificacionCNN` en los fotogramas anotados; mostrar el modo de marcha.
- [x] **T030** Tests de que las métricas nuevas son aditivas y no rompen el contrato existente.

## Fase 10 — Validación y documentación

- [x] **T031** Ejecutar `uv run pytest -q` y dejar la suite verde (538 passed, 12 skipped).
- [x] **T032** Ejecutar el smoke test `-m cnn` con el modelo real (1 passed).
- [x] **T032A** Medir accuracy con el localizador como compuerta y el contexto del fotograma: 61/63 = 0.968 en muestras con región; cobertura 63/80 = 0.762. Sin confusiones PARE↔SIGA en la muestra gated.
- [x] **T033** Procesar los 9 videos sin señales (1369 fotogramas muestreados) y verificar 0 PARE falsos; también 0 SIGA y 0 clases extra aceptadas.
- [x] **T034** Medir latencia: inferencia 10.6 ms media / 13.64 ms p95; bucle CLI 9.48 ms media / 14.66 ms p95. Se fijaron 4 hilos de ONNX Runtime.
- [x] **T035** Actualizar `AGENTS.md` (estado, comandos, riesgos) y este `tasks.md`.
- [x] **T036** Documentar el resultado para el póster: accuracy, latencia y cadencia en `research.md`/AGENTS.md.

## Dependencias

```text
T001→T002→T003→T004→T005→T006
T006→T007→T008→T009→T010
T010→T011→T012
T006→T013→T014→T015
T012+T015→T016→T017→T018→T019→T020
T019→T021→T022→T023→T024
T019→T025→T026→T027
T019→T028→T029→T030
T020+T024+T030→T031→T032→T032A→T033→T034→T035→T036
```

## MVP

El MVP mínimo es T001–T020 + T021–T024: clasificación híbrida de las 4 señales y cadencia de marcha, con tests, sin métricas/visor nuevos. La evidencia visual (T028–T030) se añade antes de la demostración.
