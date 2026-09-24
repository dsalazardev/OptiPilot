# Feature Specification: Módulo de Procesamiento de Imagen y Detección de Señales PARE/SIGA

**Feature Branch**: N/A (sin rama dedicada; trabajo en `main`)

**Created**: 2026-09-24

**Status**: Draft

**Input**: User description: "Definir los requerimientos para el módulo de procesamiento de imagen y detección de señales del Reto 1. Debe detallar la segmentación por visión clásica, los criterios de aceptación para las métricas de detección y el comportamiento de la máquina de estados PARE/SIGA."

## Clarifications

### Session 2026-09-24

- Q: Cuando el PARE y el SIGA son visibles casi al mismo tiempo, ¿ese SIGA cuenta como condición para reanudar una vez cumplido T, o se exige un SIGA confirmado después de iniciar la detención? → A: Cuenta cualquier SIGA en estado confirmado durante la detención, incluido el ya visible al detenerse; el robot reanuda al cumplir T (no se exige un SIGA nuevo).
- Q: ¿A partir de qué instante debe contarse la latencia de decisión de SC-006 (cuándo está la señal «plenamente visible»)? → A: Desde el primer fotograma en que la señal está completamente dentro de la ROI y su área alcanza el mínimo configurado.
- Q: Para las métricas de detección (SC-001 a SC-003), ¿qué define una «ocurrencia»? → A: Cada señal física de la pista en la corrida, según la anotación de referencia; el registro del módulo se compara contra esa anotación.
- Q: Si se confirma un PARE nuevo (otra señal roja o una nueva detección de una ya vista) mientras el robot ya está DETENIDO, ¿cómo debe afectar al cronómetro T y a un SIGA ya armado? → A: No afecta: se registra el evento y el robot sigue detenido con la misma condición (T no se reinicia y un SIGA armado se conserva).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Detección y clasificación de señales octogonales (Priority: P1)

Como cerebro visual del robot, necesito identificar correctamente los octágonos rojos (PARE) y verdes
(SIGA) en el flujo de la cámara, para que la decisión de detenerse o continuar se base en la señal
correcta y en ningún otro elemento de la pista.

**Why this priority**: es la base de los criterios «Reconocimiento de la señal PARE» y «Reconocimiento
de la señal SIGA» de la rúbrica. Sin detección fiable no existe comportamiento posible y se incurre
en «No cumple».

**Independent Test**: reproducir el corpus de videos de validación (con ocurrencias anotadas) y
verificar que el módulo emite exactamente una detección confirmada por ocurrencia, con la clase
correcta y sin falsos positivos.

**Acceptance Scenarios**:

1. **Given** un fotograma con un octágono rojo plenamente visible en la región de interés, **When**
   se procesa, **Then** en ≤ 3 fotogramas consecutivos el módulo confirma una detección PARE con
   clase, centro y área relativa.
2. **Given** un octágono verde plenamente visible, **When** se procesa, **Then** el módulo confirma
   una detección SIGA con la misma calidad que el caso anterior.
3. **Given** una secuencia de fotogramas sin señales, **When** se procesa, **Then** no se confirma
   ninguna detección y la decisión de movimiento permanece AUTORIZADO.
4. **Given** un fotograma con objetos rojos o verdes que no son octágonos, **When** se procesa,
   **Then** no se confirman detecciones.
5. **Given** un fotograma con los octágonos rojo y verde visibles a la vez, **When** se procesa,
   **Then** ambos se clasifican según su color, sin confusión.

---

### User Story 2 - Máquina de estados de parada y reanudación PARE/SIGA (Priority: P2)

Como robot de competencia, necesito detenerme ante PARE durante el tiempo definido por el docente y
reanudar mi recorrido según la regla acordada, para cumplir las señales y minimizar el tiempo total
sin intervención humana.

**Why this priority**: es el comportamiento evaluado en pista y alimenta los criterios «PARE»,
«SIGA», «Intervenciones humanas» y «Tiempo de recorrido» de la rúbrica.

**Independent Test**: inyectar secuencias de eventos de detección (sintéticas y grabadas) en la
máquina de estados y verificar transiciones, cronómetros y ausencia de re-disparos; luego validar en
pista.

**Acceptance Scenarios**:

1. **Given** estado EN MARCHA y una detección PARE confirmada, **When** se recibe el evento, **Then**
   la decisión cambia a NO AUTORIZADO dentro del presupuesto de latencia y el estado pasa a DETENIDO
   con registro de la transición.
2. **Given** estado DETENIDO y la señal PARE aún visible, **When** transcurren fotogramas, **Then**
   no se reinicia el cronómetro ni se duplica la detención.
3. **Given** estado DETENIDO con T cumplido y un SIGA confirmado, **When** se evalúa, **Then** la
   decisión vuelve a AUTORIZADO, el estado pasa a EN MARCHA y se registra la reanudación.
4. **Given** estado DETENIDO y un SIGA confirmado antes de cumplirse T, **When** T se cumple,
   **Then** el robot reanuda en ese momento (el SIGA no se pierde por salir de vista).
5. **Given** estado EN MARCHA y una detección SIGA confirmada sin PARE activo, **When** se recibe el
   evento, **Then** el robot continúa sin detenerse y se registra el evento.
6. **Given** estado DETENIDO con T cumplido y sin SIGA confirmado, **When** transcurren fotogramas,
   **Then** el robot permanece detenido a la espera de SIGA (no reanuda por tiempo).
7. **Given** una pérdida momentánea de la señal (≤ 2 fotogramas) durante la detención, **When** se
   recupera la visibilidad, **Then** el estado y el cronómetro no se ven afectados.
8. **Given** estado EN MARCHA con PARE y SIGA confirmados a la vez, **When** se procesa, **Then** el
   robot se detiene (prevalece PARE) y el SIGA queda armado, de modo que al cumplirse T reanuda sin
   exigir un SIGA nuevo.
9. **Given** estado DETENIDO con T en curso y un SIGA armado, **When** se confirma un PARE nuevo,
   **Then** el estado, T y el SIGA armado no cambian y el evento se registra.

---

### User Story 3 - Segmentación reutilizable de la línea guía (Priority: P3)

Como módulo de seguimiento de línea, necesito que el procesamiento de imagen entregue una máscara de
la línea guía robusta y estable, para calcular la posición de la línea y corregir la trayectoria sin
volver a procesar la imagen.

**Why this priority**: habilita «Corrección de trayectoria» y el «Uso de técnicas de visión
artificial»; separa responsabilidades entre segmentación (este módulo) y control (módulo de
seguimiento).

**Independent Test**: reproducir videos de práctica y verificar que la máscara aísla la línea
(IoU promedio ≥ 0.60 en el subconjunto anotado) y que el módulo reporta «no detectado» sin error
cuando no hay línea.

**Acceptance Scenarios**:

1. **Given** un fotograma con línea visible, **When** se procesa, **Then** la máscara de línea se
   produce y se expone al consumidor.
2. **Given** fotogramas con sombras, reflejos o cambio de iluminación, **When** se procesa,
   **Then** la máscara sigue aislando la línea en el subconjunto validado (IoU promedio ≥ 0.60).
3. **Given** un fotograma sin línea visible, **When** se procesa, **Then** la máscara queda vacía y
   el módulo reporta «no detectado» sin excepción.

---

### User Story 4 - Evidencia visual y métricas de ejecución (Priority: P3)

Como equipo, necesitamos salidas visuales por etapa y un resumen de métricas por corrida, para
sustentar el póster, el análisis de resultados y la defensa oral.

**Why this priority**: alimenta los criterios «Póster o presentación visual», «Análisis de
resultados» y «Comunicación verbal»; convierte la operación del módulo en evidencia explicable.

**Independent Test**: ejecutar una corrida sobre footage con el modo diagnóstico activo y verificar
que se generan imágenes anotadas por etapa y un resumen con los contadores esperados.

**Acceptance Scenarios**:

1. **Given** el modo diagnóstico activo, **When** se procesa un video, **Then** se generan
   fotogramas anotados con máscara, contorno y clasificación por etapa.
2. **Given** una corrida finalizada, **When** se cierra la sesión, **Then** se produce un resumen
   con ocurrencias, detecciones correctas, confusiones, falsos positivos, latencias y duraciones de
   parada.

---

### Edge Cases

- Octágono parcialmente ocluido, rotado o en perspectiva: se clasifica si alcanza la visibilidad y
  forma mínimas; si no, no se confirma.
- Señal visible por muy pocos fotogramas: no se confirma (protección contra falsos positivos); se
  asume que las señales del reto permanecen visibles el tiempo suficiente.
- Objetos rojos o verdes no octogonales (ropa, avisos, cintas): suprimidos por forma, área y
  confirmación temporal.
- PARE y SIGA visibles simultáneamente: prevalece PARE para la detención; el SIGA ya confirmado
  arma la reanudación, que ocurre al cumplirse T.
- PARE permanece a la vista después de detenerse: sin re-disparo; la detección se re-arma tras X
  fotogramas sin verla.
- T cumplido sin SIGA visible (o con SIGA no detectado): el robot permanece detenido (fallo seguro);
  se registra como incidencia para el análisis de resultados.
- PARE nuevo (otra señal o nueva detección) durante la detención: se registra; no reinicia T ni
  invalida el SIGA armado.
- Pérdida de cámara, fotogramas vacíos o negros: sin excepción; se mantiene la última decisión y se
  registra la incidencia.
- Cambios bruscos de iluminación o sombras: degradación controlada de las máscaras; nunca debe
  generar falsos positivos de señal.
- Señal en el borde de la región de interés: la detección es estable solo dentro de la zona útil;
  la ROI debe parametrizarse para cubrir la zona de aparición esperada.
- Dos ocurrencias de PARE consecutivas en puntos distintos: el re-armado habilita una nueva
  detención por ocurrencia.
- Línea guía con color similar al de una señal (si la pista lo permitiera): se asume contraste;
  validar en pista y ajustar rangos de color.

## Requirements *(mandatory)*

### Functional Requirements

**Segmentación por visión clásica (preprocesamiento y máscaras)**

- **FR-001**: El módulo MUST implementar la segmentación y la detección exclusivamente con las
  técnicas autorizadas del Reto 1 (operaciones lógicas/aritméticas, espacios de color, ROI,
  umbralización, segmentación por color, K-Means básico, morfología, suavizado, Canny, contornos,
  formas geométricas simples y propiedades de contorno), sin aprendizaje profundo, modelos
  preentrenados, cascadas Haar ni bibliotecas que automaticen la detección.
- **FR-002**: El módulo MUST procesar cada fotograma del flujo de cámara dentro del presupuesto de
  tiempo real, sin bloquear el bucle de decisión.
- **FR-003**: El módulo MUST aplicar suavizado/reducción de ruido y conversión de espacio de color
  antes de segmentar, para estabilizar las máscaras ante ruido del sensor.
- **FR-004**: El módulo MUST restringir el procesamiento a regiones de interés configurables: zona
  de línea y zona de señales, para reducir cómputo y falsos positivos.
- **FR-005**: El módulo MUST segmentar por color la línea guía y producir una máscara binaria estable
  ante variaciones de iluminación del entorno de la pista.
- **FR-006**: El módulo MUST segmentar por color las señales roja y verde en máscaras independientes,
  con rangos de color configurables y separación inequívoca entre ambas.
- **FR-007**: El módulo MUST aplicar operaciones morfológicas (apertura y cierre) para eliminar ruido
  y consolidar regiones, con parámetros configurables.
- **FR-008**: El módulo MUST descartar regiones por debajo de un área mínima configurable antes de
  analizar candidatos.
- **FR-009**: El módulo MUST validar cada candidato como octágono mediante análisis de contorno,
  aproximación poligonal (8 vértices) y propiedades de forma (área, perímetro, relación de aspecto),
  con tolerancias configurables.
- **FR-010**: El módulo MUST clasificar los octágonos en dos únicas clases — rojo = PARE, verde =
  SIGA — y ninguna otra forma o color produce detección.
- **FR-011**: El módulo MUST confirmar una señal solo tras observarla en N fotogramas consecutivos
  (N configurable, por defecto 3) y MUST tolerar pérdidas de hasta K fotogramas (K configurable, por
  defecto 2) sin revocar la confirmación.
- **FR-012**: Una escena sin señales MUST NOT producir detecciones confirmadas; los falsos positivos
  se suprimen por área mínima, forma y confirmación temporal.
- **FR-013**: El módulo MUST exponer por fotograma las máscaras (línea y señales), las señales
  confirmadas (clase, centro, área relativa y momento) y una representación visual anotada
  conmutable (máscara, contorno, clasificación) para inspección y para el póster.
- **FR-014**: Si no hay línea visible o no hay candidatos, el módulo MUST continuar sin error,
  reportando «no detectado» y manteniendo la última decisión válida hacia el consumidor.

**Máquina de estados PARE/SIGA**

- **FR-015**: La máquina de estados MUST ser explícita y determinista, con al menos los estados
  EN MARCHA y DETENIDO (por PARE), y MUST emitir a la capa de control una decisión de movimiento:
  AUTORIZADO o NO AUTORIZADO. El estado DETENIDO MUST distinguir la fase de parada mínima (T en
  curso) de la fase de espera de SIGA (T cumplido), para diagnóstico y métricas.
- **FR-016**: Al confirmar PARE en EN MARCHA, el módulo MUST emitir NO AUTORIZADO dentro del
  presupuesto de latencia y registrar el evento de detección.
- **FR-017**: En DETENIDO, el módulo MUST mantener NO AUTORIZADO durante el tiempo T definido por el
  docente y MUST NOT reanudar por el solo cumplimiento de T. La reanudación exige un SIGA confirmado:
  T se interpreta como parada mínima. Un SIGA confirmado durante la detención antes de cumplirse T
  queda armado y no se pierde si la señal sale de vista; el robot reanuda cuando T se cumple y existe
  un SIGA armado, o de inmediato si el SIGA se confirma con T ya cumplido. T MUST ser un parámetro
  configurable y confirmado con el docente (no un valor asumido).
- **FR-018**: Al confirmar SIGA mientras está DETENIDO, el módulo MUST armar la condición de
  reanudación y MUST reanudar de inmediato si T ya se cumplió; si T no se ha cumplido, MUST esperar a
  que se cumpla. Un SIGA ya confirmado en el instante de entrar en DETENIDO MUST considerarse armado.
  Cada evento de SIGA durante la detención MUST registrarse.
- **FR-019**: Al confirmar SIGA en EN MARCHA (sin PARE activo), el módulo MUST NOT detenerse; solo
  registra el evento (el verde nunca provoca parada).
- **FR-020**: Si PARE y SIGA se confirman simultáneamente, MUST prevalecer PARE (el robot se
  detiene); el SIGA confirmado en ese instante queda vigente para armar la reanudación conforme a
  FR-018.
- **FR-021**: La misma ocurrencia de PARE MUST NOT re-disparar la detención mientras siga visible;
  la detección se re-arma solo tras X fotogramas sin verla (X configurable, por defecto 5). Un PARE
  nuevo confirmado durante DETENIDO MUST registrarse sin reiniciar T ni invalidar un SIGA ya armado.
- **FR-022**: La pérdida momentánea de una señal durante la detención (≤ K fotogramas) MUST NOT
  reanudar la marcha ni reiniciar el cronómetro. Un SIGA ya armado MUST permanecer vigente aunque la
  señal no esté visible en el momento en que T se cumple.
- **FR-023**: El módulo MUST registrar cada transición de estado (origen, destino, causa y momento)
  para diagnóstico y métricas.
- **FR-024**: Todos los parámetros (T, N, K, X, área mínima, ROI, rangos de color y presupuesto de
  latencia) MUST estar centralizados, documentados y ser modificables sin cambiar la lógica.

**Métricas y evidencia**

- **FR-025**: El módulo MUST registrar por corrida las ocurrencias de PARE y SIGA, las detecciones
  correctas, las confusiones rojo↔verde, los falsos positivos, la latencia de decisión por
  ocurrencia y las duraciones de parada, y MUST exportar un resumen legible para el análisis de
  resultados y el póster. Las ocurrencias se cuentan una por cada señal física anotada en la pista
  (anotación de referencia); el análisis alinea los eventos del módulo contra esa anotación.

### Key Entities *(include if feature involves data)*

- **Fotograma**: imagen capturada con su marca de tiempo; entrada del módulo.
- **ResultadoSegmentación**: máscara de línea, máscara roja, máscara verde y ROI usada en el
  fotograma.
- **CandidatoSeñal**: región detectada antes de confirmar (color, centro, área relativa, número de
  vértices, caja envolvente y relación de aspecto).
- **SeñalConfirmada**: octágono validado y clasificado (clase PARE/SIGA, centro, área relativa,
  marca de tiempo y ocurrencia asociada).
- **Ocurrencia**: cada señal física colocada en la pista (una por anotación de referencia, con
  inicio, fin y resultado de detección); es el denominador de las métricas y el registro del módulo
  se alinea por tiempo contra ella.
- **EstadoRobótico**: estado de la máquina (EN MARCHA / DETENIDO), cronómetro de parada y señal
  activa.
- **DecisiónMovimiento**: orden booleana AUTORIZADO / NO AUTORIZADO emitida a la capa de control.
- **TransiciónEstado**: cambio registrado (origen, destino, causa y momento).
- **ParámetrosConfiguración**: T, N, K, X, área mínima, ROI, rangos de color y presupuesto de
  latencia.
- **MétricasCorrida**: contadores y tiempos agregados por corrida (ocurrencias, aciertos,
  confusiones, falsos positivos, latencias y paradas).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: En cada corrida de evaluación, el 100 % de las apariciones de PARE son detectadas y
  clasificadas correctamente (nivel «Cumple» de la rúbrica; 0 no-detecciones).
- **SC-002**: En cada corrida de evaluación, el 100 % de las apariciones de SIGA son detectadas y
  clasificadas correctamente (0 no-detecciones).
- **SC-003**: 0 confusiones PARE↔SIGA en todo el corpus de validación (el rojo nunca se clasifica
  como verde ni viceversa).
- **SC-004**: 0 falsos positivos que provoquen detenciones o reanudaciones indebidas; una corrida
  sin señales produce 0 detecciones confirmadas.
- **SC-005**: Cada señal se confirma en ≥ 3 fotogramas consecutivos y tolera pérdidas de hasta 2
  fotogramas sin perder la confirmación ni reiniciar cronómetros.
- **SC-006**: La decisión (detener/continuar) se emite ≤ 8 fotogramas (≈ 267 ms a 30 fps) contados
  desde el primer fotograma en que la señal está completamente dentro de la región de interés y su
  área alcanza el mínimo configurado; el robot se detiene antes de la señal con margen > 0 en el
  100 % de las ocurrencias.
- **SC-007**: El procesamiento por fotograma no excede un periodo de cuadro objetivo (≤ 33 ms a
  30 fps en la máquina de referencia), sin bloquear el bucle.
- **SC-008**: En el 100 % de las paradas por PARE, el robot permanece detenido al menos T (± 0.3 s)
  y no reanuda sin un SIGA confirmado; el retardo adicional tras T por la espera del SIGA se registra
  como métrica de la corrida.
- **SC-009**: Tras cumplirse la condición de reanudación (T cumplido y SIGA armado), el robot
  reanuda en ≤ 5 fotogramas (≈ 167 ms a 30 fps), sin intervención humana.
- **SC-010**: En el subconjunto anotado del corpus, la máscara de la línea guía alcanza un IoU
  promedio ≥ 0.60 y nunca queda vacía en fotogramas con línea claramente visible.
- **SC-011**: 0 intervenciones humanas atribuibles a errores de detección o de la máquina de estados
  por corrida de evaluación.
- **SC-012**: Con el modo diagnóstico activo, el 100 % de los fotogramas procesados generan
  evidencia visual por etapa (máscara, contorno y clasificación) utilizable en el póster y el
  análisis.

## Assumptions

- La cámara es a color y a bordo del robot; se asume disponible un flujo de fotogramas (resolución
  ≥ 640×480 y ≥ 15 fps; objetivo 30 fps). El modelo y la interfaz se definirán en el cambio de
  integración de hardware.
- El canal de comunicación con el robot no está definido en el repositorio; este módulo entrega
  decisiones a la capa de control y su transporte se decide en el cambio correspondiente.
- El corpus principal de validación son los videos de práctica del reto (enlace externo de la
  sección de ayudas de Reto 1) más grabaciones propias de la pista; se anotará un subconjunto para
  las métricas de IoU y la delimitación de ocurrencias (señales físicas por corrida).
- La pista tiene una línea guía de color contrastante; las señales son octágonos sólidos rojo y
  verde; elementos rojos o verdes ajenos a las señales son la excepción y se controlan por forma y
  área.
- La duración T es definida por el docente; queda como parámetro configurable con un valor
  provisional documentado, pendiente de confirmación (ver FR-017).
- La reanudación depende de un SIGA confirmado: si el SIGA no se detecta, el robot permanece
  detenido (fallo seguro). El riesgo para el tiempo de recorrido se mitiga con SC-002 (100 % de
  detecciones) y se analiza en los resultados.
- La cinemática del robot (velocidad y distancia de frenado) no está definida; se asume que el
  presupuesto de latencia de SC-006 permite detenerse antes de la señal y se validará en pista.
- Fuera de alcance de este módulo: cálculo de la posición de la línea respecto al centro y control de
  trayectoria/velocidad (módulo de seguimiento), captura de cámara específica, transporte de las
  decisiones hacia los actuadores, y póster o presentación finales.
- Iluminación de interior/aula típica; condiciones extremas (sol directo severo, oscuridad) quedan
  fuera de alcance.
- Una sola cámara y procesamiento monocular.
