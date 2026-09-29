# Feature Specification: Cálculo de Posición de Línea y Control de Trayectoria

**Feature Branch**: `feature/002-control-trayectoria`

**Created**: 2026-09-28

**Status**: Draft

**Input**: User description: "Definir los requerimientos para completar los Objetivos 3 y 4 del Reto 1: calcular la posición de la línea guía respecto al centro y generar comandos de control de trayectoria hacia el robot. El profesor confirmó un canal Bluetooth Classic (SPP/RFCOMM) con un API de comandos de cuatro valores: AVANZAR, IZQUIERDA, DERECHA y DETENER. Estrategia de línea perdida: memoria temporal del último lado conocido con ventana de gracia, y DETENER por seguridad al agotarla."

**Contexto heredado**: `specs/001-cv-sign-detection/spec.md` (Fases 1–7, 31/31 tareas) declaró explícitamente fuera de alcance *"cálculo de la posición de la línea respecto al centro y control de trayectoria/velocidad (módulo de seguimiento)"* (línea 320 de su spec) y su FR-015 ya emitía `DecisiónMovimiento` *"a la capa de control"*. Esta spec implementa esa capa y cierra CHK035 de `checklists/plan-tecnico.md` (la máscara de línea no tenía consumidor funcional).

## Clarifications

### Session 2026-09-28

- Q: ¿Qué canal de comunicación con el robot? → A: **Bluetooth Classic (SPP/RFCOMM)**, implementado con un socket RFCOMM de la biblioteca estándar (`socket.AF_BLUETOOTH` + `SOCK_STREAM` + `BTPROTO_RFCOMM`) contra el canal 1 del mBot. Es el estándar directo para módulos Bluetooth con microcontroladores ATmega/Arduino, habituales en prototipos académicos de robots. Se descarta BLE/GATT (`bleak`): el microcontrolador receptor no expone un perfil de servicio que el equipo haya definido.
- Q: ¿Cada comando viaja en una trama o en un byte suelto? → A: **Un byte ASCII por comando**, sin trama, cabecera, payload, checksum ni delimitador. El profesor confirmó el mapeo junto con su código de ejemplo: `AVANZAR` = `w` (0x77), `IZQUIERDA` = `a` (0x61), `DERECHA` = `d` (0x64), `DETENER` = `x` (0x78). Ver `contracts/transporte-bluetooth.md` §2–§3.
- Q: ¿Se toca la duración de parada PARE (`t_parada_s`, hoy 3.0 provisional)? → A: **No.** Queda fuera del alcance de esta spec y se trata por separado como parámetro pendiente de confirmar con el docente.
- Q: ¿Dónde vive el código de transporte? → A: En un paquete nuevo y explícito `src/transporte/`, **fuera** de `src/vision/`. `src/models/` y `src/services/` permanecen vacíos: la Constitución §II exige justificar la estructura por el pipeline, no por nombres de carpetas.
- Q: ¿Ante una pérdida momentánea de la línea, el robot se detiene o busca? → A: **Memoria temporal del último lado conocido con timeout.** Durante una ventana de gracia de N fotogramas el robot gira suavemente hacia el último lado donde se detectó la línea; si la línea no reaparece, emite `DETENER` por seguridad. Esto puntúa «capacidad de recuperar la trayectoria» sin arriesgar un giro infinito ni una salida de pista.
- Q: ¿Cuál es la posición objetivo de la línea? → A: **Un parámetro configurable `x_objetivo`**, nunca el centro geométrico del fotograma como constante. Medición sobre el footage real (2026-09-28): la mediana de `x` por video varía entre 190.0 y 286.5 px en un cuadro de 478 px; el objetivo geométrico (239) no es el objetivo real de ninguna forma fija de cámara.
- Q: ¿Puede un agente validar en software el signo del giro? → A: **No.** La convención «línea a la derecha ⇒ DERECHA» depende del montaje físico de la cámara y los motores, y los videos de práctica son grabados con cámara **en mano** (movimiento medio inter-fotograma de 13/255). Queda como supuesto de riesgo pendiente de validación en pista (ver Supuestos).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Posición de la línea respecto al objetivo (Priority: P1)

Como módulo de seguimiento, necesito conocer en qué posición lateral está la línea guía respecto a
un objetivo configurable, en cada fotograma, para que el control de trayectoria tenga una señal de
error fiable en lugar de improvisar sobre la imagen cruda.

**Why this priority**: es el **Objetivo 3** del Reto 1 y el insumo literal de P1 del pipeline en la
Constitución §II (*«cálculo de la posición de la línea respecto al centro»*). Sin una señal de error
medible no existe control de trayectoria, y el criterio «Corrección de trayectoria» de la rúbrica
queda sin base objetiva.

**Independent Test**: procesar el footage de `videos/rutaIdeal/` y `videos/desarrilamiento/` y
verificar que la posición estimada es continua frame a frame, que dos estimadores independientes
coinciden y que la señal es estable; no requiere hardware ni robot.

**Acceptance Scenarios**:

1. **Given** un fotograma con la línea visible dentro de la ROI, **When** se procesa, **Then** el
   módulo emite una posición con `x_px`, `x_norm` y `error_norm` calculado contra `x_objetivo`.
2. **Given** una línea descentrada a la derecha del objetivo, **When** se procesa, **Then**
   `error_norm` es positivo y su magnitud es proporcional al desplazamiento.
3. **Given** un fotograma sin línea visible (escena vacía, sombra o piso), **When** se procesa,
   **Then** el módulo emite `valida = false` con `confianza = 0.0` y **no** inventa una posición.
4. **Given** una línea válida en fotogramas consecutivos, **When** se varyan la iluminación y el
   ruido, **Then** el salto de posición entre fotogramas permanece por debajo del umbral de
   confianza configurado.
5. **Given** la misma imagen de entrada, **When** se procesa dos veces, **Then** la posición es
   idéntica (determinismo, sin azar).

---

### User Story 2 - Control de trayectoria con zona muerta e histéresis (Priority: P1)

Como robot de competencia, necesito convertir la posición de la línea en uno de los cuatro comandos
disponibles sin oscilar, para seguir la línea de forma estable y no acumular correcciones
incorrectas.

**Why this priority**: es el **Objetivo 4** del Reto 1 y ataca directamente el criterio
«Corrección de trayectoria» de la rúbrica, que califica como «No cumple» más de tres correcciones
incorrectas. Con solo cuatro comandos discretos (sin velocidad ni duración de giro) el control es
bang-bang por construcción: sin histéresis el robot oscila.

**Independent Test**: inyectar secuencias sintéticas de `error_norm` (rampa, escalón, ruido gaussiano,
oscilación) en el controlador y verificar la secuencia de comandos resultante, contando
transiciones `AVANZAR ↔ {IZQUIERDA, DERECHA}` sin cámara ni robot.

**Acceptance Scenarios**:

1. **Given** `|error_norm|` dentro de la zona muerta, **When** se evalúa el control, **Then** el
   comando es `AVANZAR`.
2. **Given** `error_norm` por encima de la zona muerta hacia la derecha, **When** se evalúa, **Then**
   el comando es `DERECHA` (corrige hacia el lado donde está la línea).
3. **Given** `error_norm` por encima de la zona muerta hacia la izquierda, **When** se evalúa,
   **Then** el comando es `IZQUIERDA`.
4. **Given** un error que cruza la zona muerta de ida y vuelta por ruido, **When** se evalúan
   fotogramas consecutivos, **Then** la histéresis impide que el comando alterne en cada fluctuación.
5. **Given** un error grande y sostenido, **When** se evalúan N fotogramas, **Then** el comando de
   corrección se mantiene (no se alterna entre lados).

---

### User Story 3 - Recuperación de línea perdida con memoria del último lado (Priority: P2)

Como robot de competencia, necesito recuperar la trayectoria cuando la línea se pierde momentáneamente
y detenerme con seguridad si no la encuentro, para cumplir el criterio «capacidad de recuperar la
trazabilidad» sin descarrilarme ni intervención humana.

**Why this priority**: alimenta los criterios «número de descarrilamientos» y «capacidad de recuperar
la trayectoria» de la rúbrica, y es la diferencia entre un robot que se rinde al primer parpadeo del
sensor y uno que completa la pista. Se ubica en P2 porque el robot sí completa la pista sin ella
—simplemente se detiene—; su valor aparece bajo interferencia.

**Independent Test**: inyectar secuencias de `PosicionLinea` con huecos de N−1, N, N+1 y N+N
fotogramas y verificar que el robot gira hacia el último lado conocido durante los N fotogramas de
gracia y emite `DETENER` en el N+1, sin cambiar de lado ni reiniciar la cuenta.

**Acceptance Scenarios**:

1. **Given** la línea detectada a la derecha y luego una pérdida de N fotogramas, **When** se
   procesa, **Then** el robot emite `DERECHA` (búsqueda hacia el último lado conocido) durante toda
   la ventana de gracia.
2. **Given** una pérdida que se prolonga al fotograma N+1, **When** se agota la ventana, **Then**
   el robot emite `DETENER` y registra el evento como intento de recuperación fallido.
3. **Given** la línea reaparición dentro de la ventana de gracia, **When** se procesa, **Then** el
   robot retoma el control normal y la memoria del último lado se actualiza.
4. **Given** que la línea se pierde desde el arranque (nunca se detectó un lado), **When** se
   procesa, **Then** el robot emite `DETENER` (no hay hacia dónde buscar).
5. **Given** una recuperación en curso, **When** la línea reaparece en el lado **opuesto** al
   memorizado, **Then** el robot invierte la corrección en el siguiente fotograma (memoria
   actualizada, no inercia).

---

### User Story 4 - Transporte de comandos por Bluetooth Classic SPP (Priority: P2)

Como equipo, necesitamos enviar los cuatro comandos al robot por un canal Bluetooth Classic (SPP /
RFCOMM) con una interfaz delgada, asíncrona y verificable sin hardware, para que la integración con
el actuador sea real sin bloquear el bucle de visión.

**Why this priority**: cierra la frontera robot/actuador que `specs/001` dejó abierta y convierte
`DecisionMovimiento` en una orden que sale del sistema. Se ubica en P2 porque el control de
trayectoria es demostrable en video sin él; el transporte aporta valor en la integración real y es
condición para la demostración en pista.

**Independent Test**: validar el protocolo completo contra un transporte simulado (mock) en
headless —secuencia de comandos, codificación de bytes, manejo de desconexión y confirmación de
no-bloqueo del bucle— sin requerir módulo Bluetooth ni robot.

**Acceptance Scenarios**:

1. **Given** un comando emitido por el control, **When** se envía al transporte, **Then** llega
   codificado según el protocolo definido a un destino identificable.
2. **Given** un transporte Bluetooth no conectado, **When** se intenta enviar, **Then** el envío
   falla de forma controlada (sin excepción, con registro) y el bucle de visión **no** se bloquea.
3. **Given** el mismo comando repetido en fotogramas consecutivos, **When** se procesa la cola,
   **Then** solo se transmite **un** cambio de comando (el transporte deduplica estados idénticos).
4. **Given** un fotograma con `DETENER` y un comando de corrección previo, **When** se compone la
   decisión, **Then** el `DETENER` prevalece y es lo único que se transmite.
5. **Given** una desconexión durante una corrida, **When** se reconecta, **Then** el transporte
   reanuda el envío del último comando válido sin duplicar bytes.

### Edge Cases

- **Línea fuera de la ROI**: la proyección de columnas devuelve una posición en el borde; el
  confianza baja proporcionalmente y el control trata el caso como pérdida si cae bajo el
  umbral.
- **Más de un pico de igual intensidad** en la proyección (dos bandas oscuras): se toma el pico de
  mayor masa y se penaliza la confianza por ambigüedad; nunca se promedia entre modos distintos.
- **Máscara completamente vacía** (fotograma negro, o `roi_linea` mal calibrada): `valida = false`,
  sin división por cero, sin excepción; se conserva la última posición válida para diagnóstico.
- **ROI degenerada** (ancho o alto 0 por calibración inválida): se rechaza en carga de configuración
  con `ConfiguracionInvalidaError`, no en tiempo de ejecución.
- **Error exactamente en el borde de la zona muerta**: la histéresis define la pertenencia
  (inclusiva por dentro, exclusiva por fuera) para evitar ambigüedad en el conmutador.
- **Línea perdida durante una detención por PARE**: `DETENER` por FSM ya prevalece; la memoria del
  último lado se congela y no emite correcciones.
- **Reinicio del robot / del proceso**: la memoria del último lado arranca vacía; sin historial
  heredado, el primer frame con línea perdida emite `DETENER`.
- **`x_objetivo` fuera de [0, 1]**: rechazado en carga de configuración.
- **Zona muerta ≥ 0.5**: se rechaza en carga (dejaría al robot ciego a la mitad de la pista).
- **Comando de corrección con línea simultáneamente válida y centrada**: nunca ambos a la vez;
  `AVANZAR` y un lado son mutuamente excluyentes por construcción.
- **Desconexión durante una corrección**: el estado del control no cambia; solo el envío falla y se
  registra, para no crear una divergencia entre decisión y transmisión.
- **Pico de proyección en el borde exacto de la ROI** (línea saliendo del encuadre): se marca como
  pérdida, no como posición válida en el borde.

## Requirements *(mandatory)*

### Functional Requirements

**Posición de la línea (Objetivo 3)**

- **FR-001**: El módulo MUST calcular la posición lateral de la línea guía por fotograma a partir de
  la máscara binaria produced por la segmentación (001), sin reprocesar la imagen.
- **FR-002**: El cálculo MUST realizarse **exclusivamente** con técnicas autorizadas por el Reto 1
  (operaciones aritméticas y lógicas sobre la máscara, sumas por columna y ponderación de índices).
- **FR-003**: El módulo MUST NOT usar transformada de Hough (`HoughLinesP`), ajuste de recta
  (`fitLine`) ni ninguna biblioteca que detecte la línea automáticamente, conforme al Principio I y
  §III de la Constitución, que prohíbe explícitamente las dependencias que automaticen la detección
  aunque sean «herramientas de visión» convencionales.
- **FR-004**: La posición MUST expresarse en píxeles (`x_px`) y en fracción normalizada del ancho
  (`x_norm` en [0, 1]), y el error MUST calcularse contra un objetivo configurable `x_objetivo`
  (fracción normalizada), **nunca** contra el centro geométrico del fotograma como constante.
- **FR-005**: `x_objetivo` MUST ser un parámetro de configuración validado en el rango [0, 1] y
  ajustable sin modificar código, porque la posición objetivo depende del montaje físico de la
  cámara.
- **FR-006**: El módulo MUST reportar un indicador de validez y una confianza: `valida = false` y
  `confianza = 0.0` cuando no hay evidencia suficiente de línea (máscara vacía, sin pico dominante,
  o pico en el borde de la ROI).
- **FR-007**: La confianza MUST penalizar la ambigüedad (varios picos de masa comparable) y la
  proximidad al borde de la ROI, de modo que una posición dudosa se distinga de una firme.
- **FR-008**: El módulo MUST ser determinista: la misma entrada produce la misma posición, sin
  fuentes de azar.
- **FR-009**: Ante una pérdida temporal de la línea, el módulo MUST NOT lanzar excepción y MUST
  reportar `valida = false`, informando además el último lado conocido para el control.
- **FR-010**: El cálculo MUST ejecutarse dentro del presupuesto de tiempo real por fotograma
  (≤ 33 ms a 30 fps) usando operaciones vectorizadas sobre la máscara, sin bucles por píxel.

**Control de trayectoria (Objetivo 4)**

- **FR-011**: El módulo MUST convertir la posición de la línea en exactamente uno de cuatro
  comandos: `AVANZAR`, `IZQUIERDA`, `DERECHA`, `DETENER`.
- **FR-012**: La decisión MUST usar una **zona muerta** (umbral de error) por debajo de la cual el
  comando es `AVANZAR`, y una **banda de histéresis** que evite la alternancia de comandos ante
  fluctuaciones del error alrededor del umbral.
- **FR-013**: La zona muerta, la histéresis y cualquier umbral MUST ser parámetros de configuración
  validados y documentados, nunca números mágicos en el código.
- **FR-014**: El signo del error MUST mapearse al lado donde se **encuentra la línea** (error
  positivo = línea a la derecha ⇒ corregir a la derecha), lo que hace la ley de control simétrica al
  signo del montaje de la cámara.
- **FR-015**: El control MUST ser estable ante ruido: una secuencia de N fotogramas con error
  sostenido MUST producir un comando de corrección sostenido, no una alternancia entre lados.
- **FR-016**: El módulo MUST NOT decidir la dirección de giro a partir de información distinta de la
  posición de la línea y su error (no usar heurísticas de color, tamaño ni posición absoluta del
  píxel).
- **FR-017**: La tasa de corrección (transiciones entre `AVANZAR` y un lado) MUST registrarse como
  métrica por corrida para evaluar el criterio «Corrección de trayectoria».

**Recuperación de línea perdida**

- **FR-018**: El módulo MUST mantener una memoria del último lado conocido en que se detectó la
  línea, actualizándola en cada fotograma con línea válida.
- **FR-019**: Ante `valida = false` con memoria disponible, el módulo MUST emitir el comando de
  corrección hacia ese último lado durante una ventana de gracia de N fotogramas (N configurable), y
  MUST emitir `DETENER` en el fotograma N+1 si la línea sigue perdida.
- **FR-020**: Al agotarse la ventana de gracia sin recuperar la línea, el módulo MUST emitir
  `DETENER` y registrar el intento fallido como métrica.
- **FR-021**: Si la línea se recupera dentro de la ventana, el control MUST retomar el mando normal y
  la memoria MUST actualizarse con el nuevo lado detectado.
- **FR-022**: Si nunca se detectó línea (memoria vacía), el módulo MUST emitir `DETENER`
  inmediatamente, sin girar a ciegas.
- **FR-023**: La memoria del último lado MUST reiniciarse (vaciarse) al arrancar el proceso, sin
  arrastrar estado entre corridas.

**Composición y precedencia de seguridad**

- **FR-024**: La decisión final del robot MUST componer el control de trayectoria con la máquina de
  estados: si la FSM emite `NO_AUTORIZADO` (PARE confirmado o espera), el comando final MUST ser
  `DETENER` y MUST prevalecer sobre cualquier corrección de dirección.
- **FR-025**: `DETENER` MUST ser el valor de fallo seguro por defecto ante cualquier error interno
  del control (posición inválida, excepción, estado inconsistente).
- **FR-026**: La composición MUST preservar la semántica de `DecisionMovimiento` de 001
  (AUTORIZADO / NO AUTORIZADO) sin modificarla, de modo que las pruebas existentes sigan siendo
  válidas.
- **FR-027**: La composición MUST ser un punto de arbitraje explícito y auditable, con la razón de
  cada comando final registrada (tracking, zona muerta, recuperación, veto por FSM, fallo seguro).

**Transporte Bluetooth (SPP/RFCOMM)**

- **FR-028**: El envío de comandos al robot MUST implementarse sobre Bluetooth Classic (SPP/RFCOMM)
  con un socket de la biblioteca estándar —`socket.AF_BLUETOOTH`, `SOCK_STREAM`,
  `socket.BTPROTO_RFCOMM`—, conectado al canal RFCOMM 1 de la `mac_bluetooth` de configuración, y la
  escritura MUST hacerse con `sendall()`.
- **FR-029**: El transporte MUST NOT introducir ninguna dependencia de terceros: el enlace se
  implementa únicamente con el módulo `socket` de la biblioteca estándar, de modo que no hay nada que
  declarar en `pyproject.toml` (Principio III). Cualquier alternativa que requiera un driver externo
  queda descartada.
- **FR-030**: La interfaz de transporte MUST ser delgada y definir un contrato mínimo (enviar comando,
  cerrar, estado de conexión) sin depender de detalles de Bluetooth en la lógica de control.
- **FR-031**: El envío MUST ser no bloqueante para el bucle de visión: el comando MUST encolarse y
  la transmisión MUST ejecutarse de forma desacoplada, de modo que el procesamiento por fotograma
  MUST NOT esperar a la radio (no debe existir una llamada de escritura bloqueante en el camino
  crítico).
- **FR-032**: El transporte MUST deduplicar comandos idénticos consecutivos, transmitiendo solo los
  cambios de estado (el bucle de visión es más rápido que la cadencia útil de transmisión).
- **FR-033**: El módulo MUST proporcionar un transporte simulado (mock) que registre los comandos sin
  hardware, para que la prueba headless del protocolo sea completa (Principio V).
- **FR-034**: Una desconexión o fallo de envío MUST registrarse sin lanzar excepción al bucle de
  visión ni alterar la decisión de control; el fallo del transporte no puede cambiar el
  comportamiento de seguridad.
- **FR-035**: El formato del mensaje MUST documentarse en un contrato verificable: un byte ASCII por
  comando, la tabla completa de mapeo a bytes, y la ausencia de trama, cabecera, payload, checksum y
  delimitador, de modo que el receptor del robot pueda implementarlo de forma independiente.

**Métricas y evidencia**

- **FR-036**: El módulo MUST registrar por corrida el número de correcciones (transiciones
  `AVANZAR ↔ lado`), el tiempo en cada comando, los eventos de línea perdida y recuperación, y la
  latencia de decisión.
- **FR-037**: Con el modo diagnóstico activo, el módulo MUST producir evidencia visual de la
  posición estimada, el objetivo, la zona muerta y el comando emitido, utilizable en el póster.
- **FR-038**: Todos los parámetros nuevos (objetivo, zona muerta, histéresis, ventana de gracia,
  umbral de confianza, y los de transporte) MUST estar centralizados, documentados y ser
  modificables sin cambiar la lógica.

### Key Entities

- **PosicionLinea**: resultado por fotograma de US1 (x_px, x_norm, error_norm, ancho de banda,
  confianza, valida, ultimo_lado_conocido).
- **ComandoMovimiento**: enumeración de cuatro valores (`AVANZAR`, `IZQUIERDA`, `DERECHA`,
  `DETENER`) emitida por el control; es la orden de alto nivel que consumirá el transporte.
- **LadoConocido**: memoria del último lado (izquierda/derecha) en que se vio la línea, con su
  antigüedad; se usa para la recuperación (US3).
- **DecisionCompuesta**: comando final tras componer control y FSM, con su causa (arbitraje de
  seguridad).
- **Transporte**: interfaz delgada (`enviar`/`cerrar`/`conectado`/`ultimo_error`) y su implementación
  SPP real (`TransporteSPP`); la implementación simulada para pruebas headless sigue pendiente
  (T028).
- **MetricasControl**: correcciones por corrida, tiempo por comando, pérdidas y recuperaciones,
  latencia.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Sobre el footage de `videos/rutaIdeal/`, el control emite **≤ 3 correcciones por
  corrida** (transiciones `AVANZAR ↔ {IZQUIERDA, DERECHA}`) con la zona muerta por defecto; nivel
  «Cumple» del criterio «Corrección de trayectoria» de la rúbrica.
- **SC-002**: Sobre el footage de `videos/desarrilamiento/`, ante una pérdida de línea de ≤ N
  fotogramas, el robot **recupera** (vuelve a `AVANZAR` o corrección coherente) sin llegar a
  `DETENER`; solo se detiene si la pérdida excede la ventana de gracia.
- **SC-003**: 0 transiciones que coloquen al robot fuera de la ventana de confianza de la línea
  (un comando de corrección nunca se emite cuando `valida = false` y no hay memoria de lado).
- **SC-004**: La decisión (comando final) se emite ≤ 8 fotogramas (≈ 267 ms a 30 fps) desde que la
  línea alcanza su posición visible, sin bloquear el bucle.
- **SC-005**: El cálculo de posición más el control no excede 33 ms por fotograma a 30 fps; el
  transporte **no** añade latencia al bucle (verificado con el mock).
- **SC-006**: El estimator de posición es **estable**: el salto medio entre fotogramas consecutivos
  de `x_px` es menor que el ancho de la banda, y dos estimadores independientes coinciden (correlación
  ≥ 0.7). Medición de referencia 2026-09-28: correlación +0.76/+0.86 entre proyección de columnas y
  run más largo.
- **SC-007**: Con un PARE confirmado, el comando final es `DETENER` en el 100 % de los fotogramas
  del estado DETENIDO, y ninguna corrección de dirección se transmite (prevalencia de FSM).
- **SC-008**: El protocolo de transporte supera las pruebas headless completas contra el mock
  (secuencia, deduplicación, desconexión, reconexión) con 0 excepciones no capturadas.
- **SC-009**: Con el modo diagnóstico, el 100 % de los fotogramas generan evidencia visual de
  posición, objetivo y comando, utilizable en el póster y el análisis.

## Assumptions

- **Riesgo abierto — convención de giro (validación en pista)**: que «error positivo ⇒ girar a la
  derecha» corresponda a un giro **real** a la derecha depende del montaje físico de la cámara y de
  los motores, y **no** puede validarse en software. Los videos de práctica están grabados con cámara
  **en mano** (movimiento medio inter-fotograma medido de 13/255), no montada en el robot, por lo que
  solo validan el *estimador* y la *estabilidad del control*, **no** el signo del giro. Este supuesto
  queda explícitamente pendiente de validación en pista física y se registra como riesgo en
  `plan.md` y en `AGENTS.md` §27.
- El transporte será Bluetooth Classic SPP hacia un módulo tipo HC-05/HC-06 con microcontrolador
  receptor; se asume que el equipo receptor implementará el protocolo definido en el contrato, ya que
  «no nos preocupamos por el robot» (el cerebro es nuestro).
- La comunicación es **de ida** (solo enviamos comandos); no se implementa lectura de sensores,
  telemetría ni confirmaciones del robot en esta spec.
- La zona muerta por defecto se calibra con evidencia del footage real (los videos `rutaIdeal` pasan
  entre 40 % y 82 % de sus fotogramas dentro de |error| < 0.10 del objetivo), pero **deberá
  recalibrarse** con la cámara montada.
- El objetivo `x_objetivo` se deja en el centro (0.5) como valor por defecto, marcado como
  *provisional*, y se recalibrará con footage del robot montado; no se fija el valor definitivo hasta
  entonces.
- La duración de parada PARE (`t_parada_s`, hoy 3.0) **no** se modifica en esta spec; su confirmación
  con el docente se trata por separado.
- El formato del mensaje del transporte se define en esta spec como contrato, pero la implementación
  del receptor es del firmware del robot y queda fuera del alcance del repositorio. Se asume que se
  envía **exactamente un byte sin salto de línea** (`transporte-bluetooth.md` §2, P3/P5): el
  `Robot.py` del profesor no está en este repositorio, así que el supuesto no pudo comprobarse.
- La pista tiene una línea guía de ancho y contraste constantes; el detector asume una banda
  contigua única. Pistas con dos bandas o bifurcaciones quedan fuera de alcance.
- No se implementa control de velocidad ni duración de giro: la API del profesor expone solo cuatro
  comandos discretos, por lo que la ley de control es bang-bang por construcción.

## Out of Scope

- Modificación de `t_parada_s` o de la semántica de la máquina de estados de 001.
- Detección de señales PARE/SIGA (ya implementado en 001) más allá de su consumición como veto.
- Implementación del firmware del receptor Bluetooth (vive en el microcontrolador del robot).
- Telemetría, lectura de sensores,bidireccionalidad o confirmaciones del robot.
- Póster, presentación final y defensa oral.
- Recalibración de `roi_linea`/`roi_senales` (cerrada en el cambio previo con evidencia de footage).

## Dependencias

- **specs/001-cv-sign-detection** (implementado): provee `ResultadoSegmentacion.mascara_linea`,
  `MaquinaEstados.decision` (`DecisionMovimiento`) y el bucle de `PipelineVision`.
- La máscara de línea de 001 es actualmente «cualquier píxel oscuro» (`v_max: 110` con rango H/S
  completo, ocupación 15–17 % en footage). US1 **no** corrige esa calibración — está fuera de
  alcance —; se apoya en la separación de modos por proyección de columnas. La corrección de la
  máscara (p. ej. exigir anchura o rango S mínimo) queda como mejora futura.
- **Transporte**: el canal hacia el robot no añade ninguna dependencia. `TransporteSPP` usa solo
  `socket` de la biblioteca estándar (FR-028, FR-029); el destino es la `mac_bluetooth` y el timeout
  `timeout_transporte_s` que viven en `config/vision.json`, y la fábrica de sockets es inyectable
  para que las pruebas corran sin hardware.
