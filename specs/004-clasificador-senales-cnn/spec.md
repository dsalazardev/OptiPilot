# Feature Specification: Clasificador CNN de Señales y Cadencia de Marcha

**Feature Branch**: `main` (no se creó rama nueva)

**Created**: 2026-11-02

**Status**: Draft

**Input**: User description: "Estamos en otra fase del semestre: ahora integramos redes neuronales para que el robot vea las señales. El clasificador ya existe fuera del repositorio (`optipilot_classifier`) y distingue PARE, SIGA, ZONA ESCOLAR y VELOCIDAD 60. La integración debe ser híbrida: el detector clásico localiza la región de la señal y la CNN la clasifica. En ejecución se usará ONNX Runtime sobre el Python 3.14 de OptiPilot, sin TensorFlow. La cadencia autónoma será: PARE detiene con `x` durante 3.0 s y reanuda; SIGA envía `w` cada 1.0 s; ZONA ESCOLAR cada 2.0 s; VELOCIDAD 60 cada 0.5 s."

**Contexto heredado**: `specs/001-cv-sign-detection` implementó la detección clásica de octágonos PARE/SIGA y la FSM; `specs/002-control-trayectoria` implementó el seguimiento de línea, el compositor y el enlace RFCOMM. Esta feature **no reemplaza** esas etapas: añade una clasificación CNN opcional sobre las regiones que el detector clásico ya sabe localizar, y una cadencia de avance dependiente de la señal reconocida.

> **Nota de cumplimiento académico.** El Reto 1 original prohíbe redes neuronales, aprendizaje profundo y modelos preentrenados. Esta feature pertenece a una fase posterior del curso y solo es válida si el docente autorizó explícitamente el uso de CNN en esta fase. No debe presentarse como parte de la entrega del Reto 1 original.

## Clarifications

### Session 2026-11-02

- Q: ¿La CNN reemplaza al detector clásico? → A: **No.** El detector clásico (segmentación por color + contornos) localiza la región candidata y actúa como compuerta; la CNN clasifica el **contexto del fotograma** solo cuando hay una región candidata. Se descarta clasificar todos los fotogramas porque el modelo predice `SIGA` con 60.8–95.6 % sobre fotogramas sin señal de `videos/rutaIdeal/`. Clasificar un recorte ajustado bajó la accuracy a 0.80–0.84; el contexto del fotograma conserva el dominio de entrenamiento y la compuerta evita los falsos positivos.
- Q: ¿Qué detector asigna la clase cuando la CNN está activa? → A: Con `--clasificador onnx`, la **asignación de clase la hace la CNN** y el `ExtractorCandidatos` clásico de octágonos no se ejecuta para señales; el localizador clásico de regiones sigue proponiendo las cajas. Con `--clasificador off`, el camino actual (color + octágono + `Detector`) se conserva intacto.
- Q: ¿Se ejecuta `control_cadencia.py` del proyecto de entrenamiento en paralelo? → A: **No.** El runtime es un solo proceso OptiPilot. `control_cadencia.py` es un experimento separado y no se arranca junto al robot: ambos abrirían la cámara y competirían por el mismo enlace Bluetooth.
- Q: ¿Cómo se ejecuta la CNN? → A: **ONNX Runtime en Python 3.14**. El modelo `.keras` se exporta una sola vez a `.onnx` en el proyecto de entrenamiento (Python 3.13 + TensorFlow); el runtime del robot no incorpora TensorFlow. TensorFlow 2.21 no publica wheel `cp314` para Windows.
- Q: ¿Qué se hace con ZONA ESCOLAR y VELOCIDAD 60? → A: Cambian la **cadencia de envío de `w`**; no existen comandos nuevos de velocidad ni de PWM en el protocolo `w`/`a`/`d`/`x`.
- Q: ¿Qué cadencia se usa? → A: PARE: `x` y espera de 3.0 s (FSM existente). SIGA: `w` cada 1.0 s. ZONA ESCOLAR: `w` cada 2.0 s. VELOCIDAD 60: `w` cada 0.5 s. Tras un PARE, al reanudar se vuelve a SIGA (1.0 s).
- Q: ¿Se tienen videos de la cámara del robot con las señales? → A: **No.** La validación inicial usa el dataset de `optipilot_classifier`; la validación de dominio queda como riesgo abierto y debe repetirse con la cámara montada.
- Q: ¿La cadencia aplica también a las correcciones `a`/`d`? → A: **No.** La cadencia por señal gobierna los `w` repetidos del avance. Las correcciones de línea conservan la cadencia de fotogramas existente (`fotogramas_por_orden`). Una transición desde una corrección hacia `AVANZAR` se envía de inmediato para no dejar al robot girando.
- Q: ¿Cuándo cambia el modo de marcha? → A: Cuando una clase se confirma temporalmente (3 predicciones consecutivas con confianza ≥ 0.70). El modo persiste hasta que otra clase se confirme. PARE no fija un modo de velocidad: al cumplirse los 3.0 s se reanuda en SIGA.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reconocer las cuatro señales sobre regiones localizadas clásicamente (Priority: P1)

Como robot de la nueva fase, necesito distinguir PARE, SIGA, ZONA ESCOLAR y VELOCIDAD 60 usando la CNN, pero solo sobre regiones que el detector clásico ya identificó como candidatas, para no clasificar fondos ni falsos positivos del fotograma completo.

**Why this priority**: es la funcionalidad central de la fase. Sin ella no hay señales nuevas que consumir. La localización clásica conserva el centro, el área, la ocurrencia y el cruce de señal que ya usan la FSM y las métricas.

**Independent Test**: procesar imágenes sintéticas con un octágono rojo, uno verde, un pentágono amarillo y un círculo con borde rojo; verificar que el localizador propone una región por señal y que un clasificador falso asigna la clase esperada. No requiere TensorFlow, ONNX ni robot.

**Acceptance Scenarios**:

1. **Given** un fotograma con una señal roja dentro de `roi_senales`, **When** se procesa con el clasificador habilitado, **Then** se crea una candidata con la caja de la señal y la clase que devuelve la CNN.
2. **Given** un fotograma con una señal verde, **When** se procesa, **Then** la candidata se asocia a SIGA y sigue el camino de confirmación temporal existente.
3. **Given** una señal amarilla de ZONA ESCOLAR, **When** se procesa, **Then** el localizador la propone y la CNN la clasifica como clase extra.
4. **Given** una señal de VELOCIDAD 60 (círculo blanco con borde rojo), **When** se procesa, **Then** el borde rojo permite localizarla y la CNN la clasifica como clase extra.
5. **Given** un fotograma sin ninguna región roja, verde o amarilla, **When** se procesa, **Then** no se crea ninguna candidata y no se ejecuta la CNN.
6. **Given** dos regiones solapadas para la misma señal, **When** se procesan, **Then** se conserva una sola propuesta (supresión por IoU).

---

### User Story 2 - Cadencia de marcha dependiente de la señal (Priority: P1)

Como robot autónomo, necesito que la frecuencia de envío de `w` cambie según la última señal confirmada, para ir a marcha normal, lenta o rápida, y detenerme 3.0 s ante un PARE.

**Why this priority**: es la lógica de movimiento solicitada explícitamente para esta fase y la que traduce el reconocimiento en comportamiento observable en la pista.

**Independent Test**: inyectar una secuencia de modos y tiempos en el planificador de cadencia y verificar los instantes exactos de envío de `w` y `x`, sin cámara ni robot.

**Acceptance Scenarios**:

1. **Given** modo SIGA y `t = 0`, **When** el control pide `AVANZAR`, **Then** se envía `w` y el siguiente `w` no se envía antes de `t = 1.0 s`.
2. **Given** modo ZONA ESCOLAR, **When** el control pide `AVANZAR`, **Then** los `w` se espacian 2.0 s.
3. **Given** modo VELOCIDAD 60, **When** el control pide `AVANZAR`, **Then** los `w` se espacian 0.5 s.
4. **Given** un PARE confirmado, **When** la FSM veta el movimiento, **Then** se envía `x` de inmediato, no se envía ningún `w` durante 3.0 s y al cumplirse el tiempo se reanuda en modo SIGA.
5. **Given** una corrección `a`/`d` en curso y luego una petición de `AVANZAR`, **When** cambia el comando, **Then** el primer `w` se envía de inmediato y los siguientes respetan el intervalo del modo.
6. **Given** una pérdida de línea que emite `DETENER`, **When** el control vuelve a `AVANZAR`, **Then** el primer `w` se envía de inmediato.

---

### User Story 3 - Ejecutar la CNN sin TensorFlow en el entorno actual (Priority: P2)

Como equipo, necesitamos cargar y ejecutar el modelo en el mismo Python 3.14 y venv de OptiPilot, sin migrar el proyecto ni instalar TensorFlow, para conservar la suite y el entorno reproducibles.

**Why this priority**: la integración in-process con Keras es imposible en `cp314`. ONNX Runtime tiene wheel `cp314` y mantiene el runtime ligero; sin esto, habría que migrar todo el proyecto a Python 3.13.

**Independent Test**: cargar el `.onnx` con `onnxruntime` en el venv de OptiPilot y comparar sus salidas con Keras sobre las mismas imágenes; verificar paridad numérica y top-1.

**Acceptance Scenarios**:

1. **Given** el modelo `senales_mobilenet.onnx` y su metadata, **When** se carga en el venv 3.14, **Then** la sesión inicia sin TensorFlow.
2. **Given** una imagen de prueba, **When** se ejecuta la inferencia ONNX y la de Keras, **Then** la diferencia máxima de probabilidades es < 1e-4 y la clase top-1 coincide.
3. **Given** un modelo ausente o inválido, **When** se arranca con `--clasificador onnx`, **Then** el proceso aborta con un error claro; con `--clasificador off`, el camino clásico funciona igual que hoy.

---

### User Story 4 - Evidencia visual y métricas para el póster (Priority: P3)

Como equipo, necesitamos ver en el visor y en las métricas qué clase reconoció la CNN, con qué confianza y en qué modo de marcha va el robot, para defender la solución y analizar resultados.

**Why this priority**: alimenta los criterios de comunicación y análisis de resultados; no cambia el comportamiento del robot.

**Independent Test**: procesar un video corto con `--diagnostico` y verificar que los fotogramas anotados y `metricas.json` incluyen clase, confianza, caja y modo de marcha.

**Acceptance Scenarios**:

1. **Given** una clasificación aceptada, **When** se anota el fotograma, **Then** se dibuja la caja y la etiqueta `CLASE (confianza)`.
2. **Given** una corrida, **When** se exporta `metricas.json`, **Then** incluye conteos por clase, confianza media, predicciones rechazadas por umbral y el modo final.
3. **Given** una clase extra confirmada, **When** se muestra el estado, **Then** se ve el modo ZONA ESCOLAR o VELOCIDAD 60 sin alterar la FSM.

### Edge Cases

- **Señal parcialmente fuera de la ROI**: la caja se recorta al marco; si no queda una región válida, no se clasifica.
- **Señal muy pequeña**: por debajo del área mínima relativa, se descarta antes de la CNN.
- **Dos señales del mismo color**: se generan dos propuestas; si se solapan, se conserva la de mayor área.
- **Signo con fondo de color similar** (p. ej. rojo de la pista): la morfología y el área mínima filtran; la CNN decide entre las clases aprendidas.
- **Confianza baja**: la predicción se rechaza y no cuenta para la confirmación temporal.
- **Predicciones alternas**: una secuencia PARE/SIGA/PARE no confirma ninguna clase; se requiere la misma clase durante `n_confirmacion`.
- **PARE mientras ya está detenido**: el cronómetro no se reinicia (comportamiento de la FSM existente).
- **PARE y ZONA visibles a la vez**: el veto de la FSM gana; la cadencia no se aplica mientras el robot está detenido.
- **Modelo ONNX ausente**: con `--clasificador onnx` se aborta; con `off` no se importa ni se carga.
- **Fotograma vacío o ilegible**: se devuelve el resultado degradado existente sin excepción.
- **Fuente de video vs cámara en vivo**: la cadencia usa `t_s` (índice/fps en video, reloj de pared en vivo).
- **Reinicio de corrida**: el modo vuelve a SIGA y la cadencia se reinicia.

## Requirements *(mandatory)*

### Functional Requirements

**Localización clásica de regiones**

- **FR-001**: El sistema MUST localizar regiones candidatas de señal con técnicas clásicas: conversión HSV, `cv2.inRange` para rojo, verde y amarillo, morfología de apertura/cierre, `findContours` y `approxPolyDP`.
- **FR-002**: La localización MUST restringirse a `roi_senales` y descartar regiones por área mínima relativa y relación de aspecto.
- **FR-003**: El sistema MUST convertir cada caja local a coordenadas del fotograma completo y conservar su centroide.
- **FR-004**: El sistema MUST suprimir propuestas solapadas con IoU > 0.5, conservando la de mayor área.
- **FR-005**: El localizador MUST NOT depender de la CNN: debe poder probarse con imágenes sintéticas sin modelo.
- **FR-005A**: El localizador MUST NOT exigir 8 vértices ni forma de octágono: debe aceptar el pentágono de ZONA ESCOLAR y el círculo de VELOCIDAD 60.
- **FR-005B**: La relación de aspecto del localizador MUST reutilizar `aspecto_min`/`aspecto_max` de la configuración existente, sin introducir umbrales mágicos nuevos.
- **FR-005C**: Con `--clasificador onnx`, la clase de las candidatas MUST venir de la CNN y el `ExtractorCandidatos` clásico de señales MUST NOT ejecutarse; con `off`, el camino clásico se conserva.

**Clasificación CNN**

- **FR-006**: El clasificador MUST recibir el contexto BGR del fotograma (no un recorte ajustado), redimensionarlo al tamaño de entrada del modelo y aplicar el preprocesamiento MobileNet (`RGB`, `[0,255] → [-1,1]`).
- **FR-007**: El clasificador MUST devolver la clase top-1, su confianza y la distribución completa de probabilidades.
- **FR-008**: El sistema MUST aceptar una predicción solo si su confianza es ≥ `umbral_confianza_senal` (por defecto 0.70).
- **FR-009**: El sistema MUST mapear `PARE` y `SIGA` a `ClaseSenal`; `ZONA ESCOLAR` y `VELOCIDAD 60` a `ClaseSenalExtra`.
- **FR-009A**: La clase de la CNN MUST ser coherente con la máscara que originó la región: `PARE`/`VELOCIDAD 60` ← rojo, `SIGA` ← verde, `ZONA ESCOLAR` ← amarillo.
- **FR-009B**: Además del color, el sistema MUST aplicar un filtro de forma: `PARE`/`SIGA` con 7–9 vértices (octágono de 001), `ZONA ESCOLAR` con ≥ 5 (pentágono) y `VELOCIDAD 60` con ≥ 6 (círculo). Una predicción que no cumpla se descarta y no confirma.
- **FR-010**: El sistema MUST NOT ejecutar la CNN en un fotograma sin una región candidata. La CNN solo clasifica el contexto del fotograma cuando el localizador clásico propone al menos una región; la región sigue siendo la que aporta caja y filtro de forma.
- **FR-011**: El sistema MUST cargar el modelo una sola vez por corrida y reutilizar la sesión ONNX.
- **FR-012**: El sistema MUST funcionar sin TensorFlow en el entorno de OptiPilot.

**Confirmación temporal y FSM**

- **FR-013**: Las clases PARE/SIGA MUST entrar al `Detector` existente con `n_confirmacion`, `k_tolerancia` y `x_rearme` sin cambiar su semántica.
- **FR-014**: Las clases extra MUST confirmarse con la misma ventana de `n_confirmacion` y persistir como modo de marcha hasta que otra clase se confirme.
- **FR-015**: La FSM MUST seguir siendo la única autoridad para detener por PARE; el compositor mantiene el veto `VETO_FSM`.
- **FR-016**: Un PARE MUST enviar `x`, mantener el veto durante `t_parada_s = 3.0 s` y reanudar después.
- **FR-017**: Al reanudar tras un PARE, el modo de marcha MUST volver a SIGA.

**Cadencia de marcha**

- **FR-018**: La cadencia MUST usar `t_s` (tiempo de la corrida) y no un contador de fotogramas para los intervalos en segundos.
- **FR-019**: SIGA MUST espaciar los `w` al menos 1.0 s.
- **FR-020**: ZONA ESCOLAR MUST espaciar los `w` al menos 2.0 s.
- **FR-021**: VELOCIDAD 60 MUST espaciar los `w` al menos 0.5 s.
- **FR-022**: El primer `w` tras una corrección, una pérdida de línea o una reanudación MUST enviarse de inmediato.
- **FR-023**: Las correcciones `IZQUIERDA`/`DERECHA` MUST conservar la cadencia de `fotogramas_por_orden` existente.
- **FR-024**: `DETENER` MUST tener prioridad absoluta y enviarse de inmediato; el modo no puede adelantar un `w` mientras la FSM veta.
- **FR-024A**: Con el clasificador activo, **cualquier** `DETENER` (veto de FSM, pérdida de línea o fallo seguro) MUST enviarse de inmediato; con el clasificador apagado se conserva el comportamiento actual del bucle.
- **FR-025**: Los intervalos MUST ser parámetros de configuración validados, no números mágicos.
- **FR-025A**: La cadencia por señal MUST aplicarse **solo** con `--clasificador onnx`. Con `--clasificador off`, el bucle MUST conservar la cadencia actual de `fotogramas_por_orden` para todas las órdenes y `CadenciaMarcha` no interviene, de modo que el comportamiento es idéntico al actual.

**Integración, CLI y degradación**

- **FR-026**: `PipelineVision` MUST aceptar un clasificador opcional; sin él, el comportamiento actual MUST ser idéntico.
- **FR-027**: El CLI MUST exponer `--clasificador {off,onnx}` con `off` por defecto y `--modelo-senales`/`--metadatos-senales` opcionales.
- **FR-028**: Si se pide `onnx` y el modelo no carga, el programa MUST abortar con un mensaje claro antes de abrir la fuente de video.
- **FR-029**: El paquete `src/clasificacion/` MUST ser la única frontera de E/S del modelo; `src/vision/` MUST permanecer sin dependencias de ONNX/TensorFlow.
- **FR-030**: La configuración nueva MUST validarse al cargar y rechazar valores fuera de rango con `ConfiguracionInvalidaError`.

**Exportación y paridad**

- **FR-031**: El proyecto de entrenamiento MUST incluir un script reproducible que exporte `MobileNet.keras` a ONNX y genere metadata (clases, tamaño, preproceso, hash).
- **FR-032**: La exportación MUST verificarse contra Keras en un conjunto de imágenes: diferencia máxima < 1e-4 y top-1 idéntico.
- **FR-033**: El artefacto ONNX y su metadata MUST copiarse al repositorio de runtime en una ruta configurable.

**Métricas y visualización**

- **FR-034**: El sistema MUST registrar por corrida conteos por clase, confianza media, predicciones rechazadas y modo final.
- **FR-035**: El visor MUST dibujar la caja, la clase y la confianza de cada predicción aceptada.
- **FR-036**: El modo de marcha MUST mostrarse en el estado del visor.
- **FR-037**: Las métricas existentes de línea, FSM y control MUST conservarse sin cambios de contrato.

### Key Entities

- **RegionSenal**: caja, centroide, área relativa, número de vértices y aspecto de una propuesta clásica.
- **PrediccionSenal**: clase, confianza y distribución de probabilidades devuelta por la CNN.
- **ClaseSenalExtra**: ZONA_ESCOLAR y VELOCIDAD_60, separadas de `ClaseSenal` (PARE/SIGA).
- **ModoMarcha**: SIGA, ZONA_ESCOLAR, VELOCIDAD_60; determina el intervalo de `w`.
- **CadenciaMarcha**: estado del último `w`, último comando y modo; decide si un `AVANZAR` se transmite.
- **ModeloONNX**: artefacto `.onnx` + metadata JSON con clases, tamaño, preproceso y hash.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: La CNN clasifica correctamente las 4 clases sobre el 10 % de test del dataset con accuracy top-1 ≥ 0.90.
- **SC-001A**: En las muestras del 10 % de test **en las que el localizador propone una región**, usando el contexto del fotograma como entrada de la CNN, la accuracy top-1 es ≥ 0.90 y no hay confusiones PARE↔SIGA. Medición 2026-11-02 sobre 80 imágenes: 63 con región, 61 correctas (0.968).
- **SC-001B**: La cobertura del localizador sobre el dataset de prueba se reporta por separado para no inflar SC-001A. Medición 2026-11-02: 63/80 = 0.762; la ROI está calibrada para la cámara del robot, no para las fotos de teléfono. En pista se debe medir de nuevo.
- **SC-002**: Sobre los 9 videos de `videos/rutaIdeal/` y `videos/desarrilamiento/` (sin señales), el sistema no confirma ningún PARE falso.
- **SC-003**: Un PARE confirmado produce `x` en ≤ 8 fotogramas y la reanudación ocurre a los 3.0 s ± 0.15 s en fuente en vivo.
- **SC-004**: Los intervalos medidos de `w` son 1.0 s ± 0.1 s (SIGA), 2.0 s ± 0.1 s (ZONA) y 0.5 s ± 0.1 s (VELOCIDAD) sobre una fuente de video determinista.
- **SC-005**: La paridad Keras/ONNX sobre 12 imágenes da max|Δ| < 1e-4 y 12/12 top-1 coincidentes.
- **SC-006**: La inferencia ONNX tarda ≤ 15 ms por fotograma en el portátil de desarrollo y no bloquea el bucle de visión.
- **SC-007**: Con `--clasificador off`, la suite existente pasa completa y el comportamiento es idéntico al actual.
- **SC-008**: Con `--clasificador onnx`, los tests de integración con un clasificador falso demuestran PARE, SIGA, ZONA y VELOCIDAD sin hardware.
- **SC-009**: El 100 % de las predicciones aceptadas aparecen en el visor y en `metricas.json`.

## Assumptions

- **Autorización académica**: el docente autorizó el uso de CNN en la fase actual. Esta feature no es válida para el Reto 1 original y no debe mezclarse con su entrega.
- **Modelo de entrenamiento**: el mejor modelo del experimento actual es MobileNet; se elige por latencia. Los otros modelos (VGG16/19, ResNet50, DenseNet121) no se despliegan.
- **Dominio**: el dataset son fotos de teléfono (4000×3000) con las señales sobre la pista; no hay todavía footage de la cámara del robot. La localización clásica reduce el riesgo, pero la generalización no está demostrada.
- **Firmware del robot**: se asume que cada `w` es un paso de avance y que espaciar los `w` modula la velocidad. Si el firmware mantiene el movimiento continuo, el intervalo no cambiará la velocidad; esto solo se valida en pista.
- **Protocolo**: se mantiene el enlace de un byte (`w`/`a`/`d`/`x`) de la spec 002; no hay comando de velocidad ni PWM.
- **Entorno**: OptiPilot permanece en Python 3.14; ONNX Runtime 1.31 tiene wheel `cp314` para Windows. El proyecto de entrenamiento sigue en Python 3.13 con TensorFlow/Keras.
- **PARE**: `t_parada_s = 3.0` es el valor solicitado por el usuario para esta fase; no se modifica la FSM.
- **Modo persistente**: ZONA ESCOLAR y VELOCIDAD 60 persisten hasta que otra señal se confirme; no expiran por desaparición del cartel.
- **Un solo proceso**: solo se ejecuta OptiPilot. `optipilot_classifier/control_cadencia.py` no se arranca en paralelo porque abriría la misma cámara y competiría por el enlace Bluetooth.
- **Artefacto versionado**: el `.onnx` y su metadata se copian a `assets/modelos/` y se versionan con el repositorio (≈16 MB); si el equipo decide no versionarlos, la ruta debe documentarse y el arranque con `--clasificador onnx` fallará de forma explícita.
- **Clases desconocidas**: cualquier etiqueta fuera de las 4 clases del modelo se descarta; no se crea una candidata ni un modo.

## Out of Scope

- Reentrenamiento con footage de la cámara del robot (queda como trabajo futuro).
- Clasificación del fotograma completo como detector principal.
- Comandos nuevos de velocidad, PWM o telemetría.
- Cambios en la ley de seguimiento de línea, la FSM o el compositor más allá de consumir las clases.
- Eliminar el detector clásico de PARE/SIGA: se conserva como camino por defecto (`--clasificador off`) y como referencia de comparación.
- Despliegue de TensorFlow en el runtime del robot.
- Póster y defensa oral (se alimentan con las métricas, pero no son parte de esta feature).

## Dependencias

- `specs/001-cv-sign-detection` (implementado): segmentación, candidatos, detector, FSM y métricas.
- `specs/002-control-trayectoria` (implementado): estimador de línea, control, compositor, cola y transporte RFCOMM.
- `optipilot_classifier` (proyecto externo, Python 3.13 + TensorFlow 2.21): entrenamiento y exportación del modelo.
- `onnxruntime` (runtime, wheel `cp314`).
- `videos/` (no versionado): validación de falsos positivos y cadencia.
