# Research: Clasificador CNN de Señales y Cadencia de Marcha

**Feature**: `004-clasificador-senales-cnn` | **Date**: 2026-11-02

## Decisión 1 — ONNX Runtime en Python 3.14, no Keras in-process

**Contexto**: OptiPilot usa CPython 3.14.7. El proyecto de entrenamiento usa CPython 3.13.7 con TensorFlow 2.21.0 y Keras 3.15.1.

**Evidencia**:
- TensorFlow 2.21.0 publica wheels `cp313` para Windows (`manylinux`, `macosx`, `win_amd64`) pero **no** `cp314`; verificado en el índice JSON de PyPI.
- `onnxruntime` 1.31.1 sí publica `onnxruntime-1.31.1-cp314-cp314-win_amd64.whl`.
- `tf2onnx` 1.17.0 requiere Python ≥3.10 y convierte modelos Keras con `tf2onnx.convert.from_keras`.

**Decisión**: exportar el modelo a ONNX una sola vez en Python 3.13 y ejecutarlo en Python 3.14 con `onnxruntime`.

**Alternativas descartadas**:
- Migrar OptiPilot a Python 3.13 + TensorFlow: cambia el entorno, añade ~1 GB, ralentiza el arranque y obliga a revalidar la suite.
- Dos procesos (3.14 + 3.13) con IPC: evita la migración pero añade complejidad, latencia y una segunda cámara/ventana.
- TFLite: no hay wheel `cp314` de `tflite-runtime` para Windows en el entorno actual.

## Decisión 2 — Integración híbrida, no clasificación del frame completo

**Contexto**: el clasificador `MobileNet.keras` se entrenó con fotos de teléfono (4000×3000) redimensionadas a 224×224. El dataset tiene 131 PARE, 129 SIGA, 143 ZONA ESCOLAR y 136 VELOCIDAD 60; el reporte de test da 1.0 de accuracy sobre 54 imágenes de la misma sesión.

**Evidencia de riesgo**: se ejecutó el MobileNet sobre fotogramas de `videos/rutaIdeal/video1.mp4` (footage de seguimiento de línea, sin señales):
- frame 0: `SIGA` 95.6 %
- frame 100: `SIGA` 60.8 %
- frame 300: `SIGA` 85.9 %
- frame 600: `SIGA` 78.4 %

El modelo aprende el fondo/sesión y no solo la señal; clasificar el frame completo produciría eventos falsos.

**Decisión**: el detector clásico localiza regiones candidatas con máscaras de color y contornos y actúa como **compuerta**; la CNN solo se ejecuta cuando hay al menos una región y clasifica el **contexto del fotograma**. Esto:
- evita ejecutar la CNN en fotogramas sin ninguna señal candidata;
- conserva caja, centroide, área y ocurrencia para la FSM, el cruce y las métricas;
- mantiene el dominio de entrenamiento del modelo (imágenes completas), que es donde rinde.

**Evidencia de la decisión (2026-11-02)**:
- Recorte ajustado con margen 0.2 sobre 409 regiones del dataset: accuracy 0.802.
- Margen 1.0: 0.841.
- Muestra de 8 imágenes por clase: margen 1.0 → 0.926; contexto del fotograma → 1.0.
- El recorte ajustado cambia la escala y el fondo respecto al entrenamiento; el contexto del fotograma no.

**Riesgo asumido**: el contexto del fotograma sin compuerta predice `SIGA` con 95.3 % sobre un fotograma de `rutaIdeal` que solo tiene una mancha verde. La compuerta y el filtro de forma de PARE/SIGA son obligatorios; sin ellos, la integración no es segura.

**Hallazgo durante la integración (2026-11-02)**: sobre `videos/rutaIdeal/video1.mp4` (sin señales), el localizador encontró una mancha verde grande en el borde izquierdo y el MobileNet la clasificó como `SIGA` con 89 % de confianza en 27 fotogramas. El filtro de forma de PARE/SIGA de 001 la rechaza (`n_vertices = 4`, no 7–9). Por eso el pipeline aplica ese filtro **solo a PARE/SIGA** después de la CNN; las clases extra (pentágono/círculo) no lo usan. Sin ese filtro, el robot habría cambiado de modo por una mancha verde.

**Alternativas descartadas**:
- CNN full-frame como detector principal: falsos positivos medidos.
- CNN sobre ventanas deslizantes: coste alto y muchos fondos.
- Sustituir el detector clásico de PARE/SIGA: no aporta valor para dos clases que el color ya separa.

## Decisión 3 — Localizador clásico con rojo, verde y amarillo

**Contexto**: las 4 clases usan colores distintos:
- PARE: octágono rojo.
- SIGA: octágono verde.
- ZONA ESCOLAR: pentágono amarillo.
- VELOCIDAD 60: círculo blanco con borde rojo.

**Decisión**: dentro de `roi_senales`, construir una máscara de propuestas con:
- rojo (dos rangos de tono, ya existentes);
- verde (ya existente);
- amarillo (rango nuevo, H≈20–35, S≥100, V≥80).

La máscara de VELOCIDAD 60 se obtiene por su borde rojo; la caja incluye el interior blanco. Se aplican apertura/cierre, `findContours`, `approxPolyDP`, área mínima relativa, `aspecto_min`/`aspecto_max` y supresión por IoU. No se exige forma de octágono: ZONA ESCOLAR es un pentágono y VELOCIDAD 60 es un círculo.

**Ventaja**: no requiere un detector de formas específico para las clases nuevas y reutiliza la técnica clásica ya validada.

**Riesgo**: un objeto amarillo del entorno puede generar una propuesta; la CNN y el umbral de confianza la descartan.

## Decisión 4 — Confirmación temporal y modo de marcha

**Contexto**: la FSM solo conoce PARE/SIGA. ZONA/VELOCIDAD no tienen estado en la FSM.

**Decisión**:
- PARE/SIGA usan el `Detector` existente (`n_confirmacion`, `k_tolerancia`, `x_rearme`).
- Las clases extra usan un contador de confirmación propio (`n_confirmacion_extra = 3`) y confianza ≥ 0.70.
- El `ModoMarcha` resultante se propaga en `ResultadoProcesamiento` y persiste hasta otra confirmación.
- PARE no fija modo; al reanudar, el modo vuelve a SIGA.

**Alternativa descartada**: extender `ClaseSenal` con las clases extra. Habría obligado a tocar la FSM, el detector y todos sus tests; se prefiere un enum separado.

## Decisión 5 — Cadencia en segundos, no en fotogramas

**Contexto**: el bucle actual envía una orden cada `fotogramas_por_orden` (6 frames). El usuario pidió intervalos en segundos por clase.

**Decisión**:
- El modo determina el intervalo de `w`: SIGA 1.0 s, ZONA 2.0 s, VELOCIDAD 0.5 s.
- El intervalo se mide con `t_s`, que en vivo es reloj de pared y en video es `indice / fps` (determinista para tests).
- Las correcciones `IZQUIERDA`/`DERECHA` siguen con `fotogramas_por_orden`.
- El primer `w` tras una corrección, una pérdida o una reanudación se envía de inmediato.
- `DETENER`/`x` se envía de inmediato y tiene prioridad absoluta.

**Supuesto de hardware**: el firmware del mBot interpreta cada `w` como un paso y el espaciado modula la velocidad. No está verificado; se validará en pista.

## Decisión 6 — PARE con la FSM existente

**Contexto**: la FSM ya implementa `t_parada_s = 3.0`, el no-reinicio del cronómetro y la reanudación autónoma.

**Decisión**: no duplicar el cronómetro en la cadencia. La FSM sigue siendo la única autoridad; el compositor mantiene el veto. La cadencia solo se aplica cuando la FSM autoriza el movimiento.

## Decisión 7 — Artefacto del modelo fuera de `src/`

**Contexto**: `optipilot_classifier` no es un paquete instalable, no tiene `__init__.py` y depende de TensorFlow.

**Decisión**: no importar el proyecto. Se copian al runtime:
- `assets/modelos/senales_mobilenet.onnx`
- `assets/modelos/senales_mobilenet.json` (clases, tamaño, preproceso, hash, paridad)

`src/clasificacion/onnx.py` es la única frontera que abre el modelo. `src/vision/` no importa ONNX.

## Evidencia de exportación (ejecutada 2026-11-02)

`optipilot_classifier/exportar_onnx.py`:
1. cargó `MobileNet.keras`;
2. convirtió con `tf2onnx.convert.from_keras`;
3. generó `senales_mobilenet.onnx` (12.25 MB) y su metadata;
4. comparó Keras vs ONNX en 12 imágenes del dataset.

Resultado: `max|delta| = 5.36e-07`, top-1 `12/12`. El artefacto se copió a `assets/modelos/`.

## Resultados medidos

- **Paridad ONNX/Keras**: 5.36e-07, 12/12 top-1.
- **Accuracy gated (contexto del fotograma)**: muestra de 80 imágenes, 63 con región, 61 correctas = **0.968**; cobertura del localizador 0.762. Los 17 fallos de cobertura son imágenes de teléfono cuyo cartel queda fuera de la `roi_senales` calibrada para el robot.
- **Falsos positivos sobre 9 videos** (1369 fotogramas muestreados 1/2, footage sin señales): **0 PARE, 0 SIGA, 0 clases extra**; 390 regiones rechazadas por color/forma/umbral; modo siempre SIGA.
- **Latencia de inferencia** (60 fotogramas 850×478): media **10.6 ms**, p95 **13.64 ms**, máx 14.96 ms con `intra_op_num_threads=4`. Con el valor automático de ONNX Runtime (0 hilos) era 35.8 ms de media; por eso el adaptador fija 4 hilos.
- **Latencia del CLI con CNN** (60 fotogramas): media 9.48 ms, p95 14.66 ms. Dentro del presupuesto de 33 ms.
- **Cadencia**: cubierta por tests unitarios (`test_cadencia_marcha.py`); falta validarla con el robot físico.
