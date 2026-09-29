# Research: Cálculo de Posición de Línea y Control de Trayectoria

**Feature**: `002-control-trayectoria` | **Date**: 2026-09-28 | **Spec**: [spec.md](./spec.md)

**Purpose**: Resolver las decisiones técnicas abiertas antes de diseñar. Cada decisión registra la
evidencia medida sobre el footage real, la alternativa rechazada y el motivo.

> **Nota de método**: todas las cifras de este documento provienen de experimentos ejecutados sobre
> los 9 videos de práctica (`videos/rutaIdeal/`, `videos/desarrilamiento/`, 478×850, 2730
> fotogramas) el 2026-09-28, reutilizando `Preprocesador` y `Segmentador` del pipeline existente
> (sin reimplementar segmentación). Los experimentos fueron de solo lectura: no escribieron
> artefactos en el repositorio.

---

## Decisión 1: Cómo estimar la posición lateral de la línea

### Contexto

El Reto 1 (Objetivo 3) pide *"calcular la posición de la línea respecto al centro"*. La Constitución
§II lo sitúa como etapa propia del pipeline: *«cálculo de la posición de la línea respecto al
centro»*. La entrada es `ResultadoSegmentacion.mascara_linea` (binaria, del tamaño del fotograma,
con la línea recortada dentro de `roi_linea`).

Restricción dura: el Principio I y §III de la Constitución prohíben *"cualquier algoritmo o biblioteca
que detecte automáticamente la línea"* y, explícitamente, *"las dependencias que automaticen la
detección de la línea o las señales quedan prohibidas por el Principio I, aunque sean «herramientas
de visión» convencionales"*.

### Candidatos evaluados

| Candidato | Descripción | Permitido? | Varianza medida |
|-----------|-------------|----------|-----------------|
| **A. Hough** | `cv2.HoughLinesP` sobre bordes Canny | **NO** | — |
| **B. `cv2.fitLine`** | ajuste de recta por mínimos cuadrados sobre los píxeles de la máscara | discutible | — |
| **C. Run más largo por fila** | para cada fila de la banda, el tramo horizontal más largo; su centro | sí | sd = 78.4 / 78.9 px |
| **D. Proyección de columnas** | suma de la máscara por columna; pico de masa | sí | sd = 56.4 / 72.6 px |
| **E. Centroide del pico (½)** | columnas con masa ≥ 50 % del máximo; su media ponderada | sí | **sd = 50.5 / 56.7 px** |

(Varianzas medidas sobre `rutaIdeal/video1` y `video4`; desviación estándar de `x_px` a lo largo del
video.)

### Alternativas rechazadas

**A. Transformada de Hough — RECHAZADA por norma, no por preferencia.** Es exactamente el caso que
§III prohíbe: una herramienta de visión convencional que *detecta la línea automáticamente*, sin que
el equipo implemente la lógica. Aplicarla sería un «No cumple» en el criterio «Cumplimiento de las
restricciones» de la rúbrica. No se evalúa empíricamente porque no es admisible.

**B. `cv2.fitLine` — RECHAZADA por ambigüedad normativa.** Es una primitiva geométrica de propósito
general (no un detector), pero encaja lo suficiente con el patrón prohibido como para no ser
defendible ante el docente en la defensa oral. El beneficio sobre E es marginal (E ya entrega la
posición y la confianza que el control necesita) y el riesgo de cumplimiento no es aceptable por
una ganancia de dezenas de microsegundos. Documentado aquí para que la decisión sea auditable.

**C. Run más largo por fila — RECHAZADA por varianza y coste.** Measured: sd 78.4 px frente a 50.5 px
de E, es decir **un 55 % más de dispersión** para la misma señal. Además exige un bucle Python por
fila (850 filas/video), incompatible con el presupuesto de 33 ms sin vectorizar, y su semántica
("la fila con el tramo más largo") no corresponde a la línea: el tramo más largo en una banda
inclinada suele ser una sombra o el borde de la pista, no la guía.

### Decisión

**Se adopta E: centroide del pico de la proyección de columnas.**

```text
banda      = mascara_linea[fila_anticipacion : fin_roi, x0_roi : x0_roi+w_roi]
columnas   = suma de la banda por columna            # aritmética sobre la máscara (autorizado)
pico       = argmax(columnas)
soporte    = columnas >= 0.5 * max(columnas)          # umbral de mitad de pico
x_px       = media ponderada por masa de los índices en soporte
```

Razones:

1. **Cumple la norma sin ambigüedad.** Solo usa sumas, umbrales y medias ponderadas sobre la
   máscara: operaciones aritméticas y lógicas explícitamente autorizadas. La lógica de detección es
   100 % del equipo, como exige el Principio I.
2. **Mejor estabilidad medida.** sd 50.5/56.7 px frente a 78.4/78.9 px del run más largo.
3. **Vectorizable.** `numpy` resuelve las tres operaciones sin bucles por píxel (FR-010).
4. **Da gratis la confianza.** La razón `masa_total / (pico * n_columnas)` mide qué tan dominante es
   el pico: si hay dos bandas de igual masa, la confianza baja y el módulo puede declarar la posición
   ambigua (FR-007) en vez de promediar entre modos distintos.

### Validación de la decisión: dos estimadores independientes

Para comprobar que la señal es real y no un artefacto del estimador, se compararon los candidatos C
y D sobre los mismos fotogramas:

| Video | `x` por proyección (med / sd) | `x` por run más largo (med / sd) | Correlación | Discrepancia mediana |
|-------|-------------------------------|--------------------------------|-------------|---------------------|
| `rutaIdeal/video1.mp4` | 200.0 / 56.4 | 191.2 / 78.4 | **+0.76** | 25.8 px |
| `rutaIdeal/video4.mp4` | 269.0 / 72.6 | 280.0 / 78.9 | **+0.86** | 25.0 px |

Dos estimadores estructuralmente distintos coinciden con correlación +0.76/+0.86 y discrepancia
mediana de ~25 px. **La señal de posición es genuina.** Esto se convierte en SC-006.

### Hallazgo queorcó el resto del diseño: la cámara está en la mano

La varianza de ~50 px **no es ruido del estimador**: es movimiento real de cámara. Medido
`|frame[i] − frame[i−1]|` medio = **13.0/255 y 12.8/255** en `video1` y `video4`. Un montaje fijo
en robot no produciría esa magnitud; un encuadre en mano, sí.

Consecuencias, todas incorporadas a la spec:

- Un filtro temporal (mediana de K) **no puede** eliminar este movimiento. Medido: K=9 sólo baja la
  desviación de 0.164 a 0.143. Filtrar no es la solución; la histéresis sobre el comando sí.
- Los videos sirven para validar el **estimador** y la **estabilidad del control**, pero **no** la
  cinemática real del robot.
- El objetivo `x_objetivo` no puede fijarse midiendo estos videos (ver Decisión 3).

---

## Decisión 2: Qué ley de control, dados cuatro comandos discretos

### Contexto

El profesor fijó la API: exactamente cuatro comandos — `AVANZAR`, `IZQUIERDA`, `DERECHA`,
`DETENER` — yelters: *"no nos preocupamos por el robot"*. No hay comando de velocidad, ni de duración
de giro, ni de retroceso.

### El hecho estructural

**El control es bang-bang por construcción, no por elección.** Con un conjunto de acciones
discretas sin magnitud continua, toda ley de control es un comparador con umbral:

```text
error > +umbral  ->  DERECHA
error < -umbral  ->  IZQUIERDA
en otro caso     ->  AVANZAR
```

No existe PID, ni control suave, ni amortiguamiento: **no hay grado de libertad para implementarlos**.
Esto es una consecuencia directa de la API del profesor y debe explicarse así en la defensa oral, no
presentarse como una limitación del equipo.

### El riesgo medido: oscilación

Sin histéresis, un error que cruza el umbral por ruido produce una alternancia de comandos. Medí
transiciones `AVANZAR ↔ lado` sobre footage real para distintas zonas muertas:

| K (mediana) | Zona muerta | Correcciones (video1) | Correcciones (video4) |
|-------------|-------------|------------------------|------------------------|
| 1 (sin filtro) | 0.02 | 16 | 13 |
| 1 | 0.05 | 20 | 7 |
| 3 | 0.10 | 21 | 5 |
| 5 | 0.05 | 10 | 4 |
| 9 | 0.20 | 5 | 5 |

La reducción con K grande y zona muerta ancha es moderada, y —como se explica en la Decisión 1— el
componente irreducible es el movimiento de cámara, no el ruido del estimador. Aun así, la tendencia es
monótona y la zona muerta es el parámetro de mayor efecto.

### Elección de la zona muerta por defecto

Medí qué fracción de fotogramas de `rutaIdeal` queda dentro de |error| < 0.10 del objetivo:

| Video | `x` mediana | `|error|` mediana | p90 | % dentro de zona muerta 0.10 |
|-------|------------|-------------------|-----|-------------------------------|
| `rutaIdeal/video1.mp4` | 190.0 | 0.117 | 0.210 | 40.6 % |
| `rutaIdeal/video2.mp4` | 218.8 | 0.090 | 0.139 | 68.8 % |
| `rutaIdeal/video3.mp4` | 237.8 | 0.027 | 0.129 | 82.4 % |
| `rutaIdeal/video4.mp4` | 286.5 | 0.138 | 0.219 | 40.4 % |

Con **0.10**, dos de los cuatro videos de ruta ideal pasan más de 65 % de sus fotogramas sin
corregir, y el peor caso queda en 40 %. Una zona más estrecha (0.02–0.05) forzaría correcciones
innecesarias.

**Decisión**: `zona_muerta = 0.10` como valor por defecto, más una banda de histéresis de 0.03 para
evitar la alternancia en el borde. Ambos configurables (FR-013), con validación de rango en carga
(FR: zona muerta < 0.5, si no el robot quedaría ciego a media pista).

**Calibración pendiente**: estos valores se derivaron de cámara **en mano**. Con la cámara montada
deberán recalibrarse; la spec los marca como provisionales y el plan incluye una tarea de
recalibración con footage del robot.

### Histéresis: por qué es obligatoria y no opcional

Con zona muerta pura, un error oscilando en torno a 0.10 produce alternancia. La histéresis introduce
**dos umbrales**:

```text
AVANZAR -> LADO   solo si |error| >  zona_muerta + histeresis
LADO    -> AVANZAR solo si |error| <  zona_muerta - histeresis
```

La pertenencia en el borde se define inclusiva por dentro y exclusiva por fuera (edge case en spec)
para que el conmutador sea determinista. Con zona muerta 0.10 e histéresis 0.03, el umbral de
salida es 0.13 y el de retorno 0.07: una banda de 0.06 de error libre de conmutación.

### Precedencia de la detección de pérdida

La pérdida de línea **no** se decide en el estimador sino en el control, porque requiere memoria
temporal (Decisión 4). El estimador solo reporta `valida` y `confianza`; el control decide si esa
evidencia es suficiente.

---

## Decisión 3: Por qué `x_objetivo` es un parámetro, no el centro del fotograma

### Contexto

El enunciado del Reto dice *"respecto al centro"*, lo que sugiere el centro geométrico del fotograma
como referencia. La Constitución §II repite la fórmula. Pero el Reto también exige que el sistema
funcione **en pista**, y el objetivo correcto depende del montaje físico de la cámara.

### Evidencia

Medí la posición mediana de la línea por video (fotogramas 478 px de ancho, centro geométrico
239.0):

| Video | `x` mediana | `error` mediano (normalizado) |
|-------|------------|------------------------------|
| `rutaIdeal/video1.mp4` | 190.0 | −0.103 |
| `rutaIdeal/video2.mp4` | 218.8 | −0.042 |
| `rutaIdeal/video3.mp4` | 237.8 | −0.003 |
| `rutaIdeal/video4.mp4` | 286.5 | **+0.099** |
| `desarrilamiento/noReconoceIzquierda3.mp4` | 195.0 | −0.092 |

El rango de medianas es **190.0 → 286.5 px**, un desvío de ±0.1 respecto al centro en videos
consecutivos de la misma pista. Sólo `video3` coincide con el centro (237.8 ≈ 239).

### Interpretación

Esto **no** significa que la cámara esté mal montada —el montaje es del robot, no de estos videos—.
Significa que el objetivo efectivo depende de (a) la posición de la cámara respecto al eje del
robot, (b) su inclinación, y (c) la óptica. Ninguna de las tres es un parámetro de software
derivable del fotograma.

La lectura ingenua de *"respecto al centro"* como constante produce un **sesgo sistemático**: con
`video4` el robot creería estar 0.099 a la derecha del objetivo y corregiría hacia una línea
perfectamente centrada, en bucle.

**Decisión**: `x_objetivo` es un parámetro de configuración normalizado, por defecto **0.5**
(centro), validado en [0, 1] (FR-005), y recalibrado con footage del robot montado. El valor 0.5 es un
*punto de partida* que coincide con la letra del Reto, no una verdad calibrada. La spec lo marca como
provisional en Supuestos.

Consecuencia de explicabilidad: en la defensa oral hay que poder decir *"el objetivo es configurable
porque depende del montaje, y lo calibramos contra footage propio; medimos que el centro geométrico
se desviaba hasta 0.1 del objetivo real en videos de la misma pista"*. Eso es un argumento de
ingeniería, no una excusa.

---

## Decisión 4: Estrategia de línea perdida (memoria del último lado)

### Contexto

Decisión tomada por el equipo: **memoria temporal del último lado conocido con ventana de gracia**,
y `DETENER` al agotarla. Las alternativas eran detenerse de inmediato o buscar hacia el lado
memerizado; se eligió un híbrido acotado.

### Por qué no `DETENER` inmediato

`DETENER` inmediato es la opción más segura pero penaliza directamente la rúbrica: cada parada
involuntaria cuenta como pérdida de tiempo (criterio «Tiempo de recorrido») y como
falta de recuperación (criterio «capacidad de recuperar la trayectoria»). Con un sensor ruidoso
—demostrado: la máscara tiene 15–17 % de ocupación y el pico varía— los parpadeos serían frecuentes.

### Por qué no buscar indefinidamente

Buscar sin límite de tiempo es peor: un giro prolongado fuera de la pista produce el
**descarrilamiento**, que la rúbrica penaliza directamente, y puede dejar al robot girando en
dirección contraria cuando la línea ya no está en el campo de visión.

### Por qué memoria con timeout

La memoria con ventana de gracia es el punto intermedio: aprovecha los parpadeos (que son
breves), recupera la trayectoria (criterio de recuperación), y corta antes de salir de pista
(DESCARRILAMIENTO = 0 es el objetivo). El timeout en **fotogramas** y no en segundos hace el
comportamiento independiente de la tasa de fotogramas real de la cámara.

Parámetro: `n_gracia_busqueda = 5` por defecto. Consecuencia medida que lo respalda: los videos
`desarrilamiento` muestran transiciones de posición mucho más rápidas que `rutaIdeal` —
`noReconoceIzquierda3` tiene desviación de velocidad de **52.1 px/fotograma** frente a 14.5–20.0 px
en `rutaIdeal`. Es decir, una pérdida en un caso real de desarrilamiento se resuelve en pocos
fotogramas: una ventana de 5 es suficiente para los parpadeos y demasiado corta para permitir un giro
prolongado fuera de pista.

**Velocidad de error como métrica de diagnóstico**: la desviación estándar de la velocidad de error
distingue el corpus (`desarrilamiento` ~52 px vs `rutaIdeal` ~15–20 px). Se incorpora como métrica
en `MetricasControl` porque separa «la cámara se movió» de «el robot se desvió», que es
exactamente la distinción que el póster necesita.

### Caso límite: nunca se detectó línea

Si el proceso arranca y el primer fotograma no tiene línea, no hay memoria. El control emite
`DETENER` (FR-022): no se gira a ciegas. La memoria se vacía al arrancar el proceso (FR-023) para no
arrastrar estado entre corridas.

---

## Decisión 5: Arquitectura de composición y por qué el control no manda

### El problema

La Constitución §II enumera el pipeline así: ... *segmentación → contornos → **posición de la línea**
→ **control de trayectoria** → señales → **máquina de estados** → métricas*.

Leída como orden de ejecución, el control de trayectoria se ejecutaría **antes** de la FSM. Pero si
el control emite su comando final directamente, un PARE confirmado en el mismo fotograma podría ser
pisado por una corrección de dirección, y el robot **giraría en vez de detenerse**: un fallo de
seguridad directo y un «No cumple» en el criterio PARE.

La Constitución describe **etapas**, no un **árbitro**. La lectura segura es que ambas ramas
(posición→control y señales→FSM) convergen en un punto de composición donde la FSM tiene voto de
veto.

### Alternativas evaluadas

| Opción | Descripción | Veredicto |
|--------|-------------|-----------|
| A. El control manda | El control emite el comando final; la FSM solo se consulta después | **RECHAZADA**: un PARE puede ser pisado por una corrección (fallo de seguridad) |
| B. Modificar `DecisionMovimiento` | Añadir un campo de dirección al dataclass de 001 | **RECHAZADA**: rompe el contrato ya probado por 167 tests y mezcla dos responsabilidades (permiso de seguridad y dirección) |
| C. Composición explícita | El control **propone**, la FSM **veta**, un compositor decide y registra la causa | **ADOPTADA** |

### Decisión

Se adopta **C**. `DecisionMovimiento` **no se toca** (FR-026): la FSM conserva su semántica binaria
AUTORIZADO / NO AUTORIZADO y sus 167 tests siguen siendo válidos. El compositor aplica la precedencia:

```text
si FSM.NO_AUTORIZADO          -> DETENER   (veto por señal)
si control.propone DETENER    -> DETENER   (pérdida de línea / fallo seguro)
si no                          -> control.propuesto             (AVANZAR | IZQUIERDA | DERECHA)
```

La **causa** de cada comando final queda registrada (FR-027), lo que convierte la precedencia en algo
auditable: en el póster y en la defensa se puede demostrar que PARE siempre ganó.

### Justificación constitucional

Esto **no** es una violación del §II. El principio exige que cada etapa tenga «una única
responsabilidad» y un «contrato de entrada/salida claro», no que el orden de la enumeración sea un
orden de precedencia de seguridad. El compositor es un punto de arbitraje explícito y auditable, y la
FSM conserva su rol. Se registra en el Constitution Check de `plan.md` para que la decisión sea
revisable.

---

## Decisión 6: Dónde y cómo aislar el transporte

> **⚠️ PARCIALMENTE SUPERADA (2026-09-28).** Ver la Decisión 7. Lo que **sigue vigente** es el
> aislamiento: `src/transporte/` fuera de `src/vision/`, el `Protocol` mínimo, el simulado para
> pruebas headless y el desacople por `ColaTransporte`. Lo que **queda superado** es la elección de
> dependencia: se pasa de `pyserial` a `socket` de la biblioteca estándar. El razonamiento original
> se conserva sin reescribir, porque explica por qué el aislamiento era necesario.

### Contexto

Bluetooth es E/S. `src/vision/` es, por diseño de 001, lógica pura sin I/O (conftest, CLI y tests lo
asumen). Poner `pyserial` dentro de `src/vision/` rompería esa separación y haría las pruebas
dependientes de hardware.

### Alternativas

| Opción | Veredicto |
|--------|-----------|
| A. `src/vision/transporte.py` | RECHAZADA: mezcla E/S en el paquete puro de visión; rompe el patrón de 001 |
| B. `src/services/` (carpeta vacía existente) | RECHAZADA: el §II exige justificar la estructura por el pipeline, no por nombres de carpetas; «services» no describe una responsabilidad de pipeline |
| C. `src/models/` (carpeta vacía existente) | RECHAZADA: no modela una etapa del pipeline |
| **D. `src/transporte/` nuevo** | **ADOPTADA**: nombre que describe la responsabilidad real; las carpetas vacías siguen vacías |

### Diseño del aislamiento

- `Transporte` es un **Protocol** con el mínimo: `enviar(comando)`, `cerrar()`, `conectado`.
- `TransporteSPP` implementa SPP/RFCOMM con `pyserial`.
- `TransporteSimulado` registra los comandos en memoria; **es el que usan todas las pruebas** y el
  que permite validar el protocolo entero en headless (FR-033, Principio V).
- `ColaTransporte` desacopla: el bucle de visión **encola** y sigue; la transmisión ocurre aparte
  (FR-031). Deduplica comandos idénticos consecutivos (FR-032), porque a 30 fps la decisión cambia
  mucho más rápido que la utilidad de transmitirla.

### Sobre el nombre de la dependencia

> **SUPERADA (2026-09-28).** `pyserial` fue la opción original, elegida por ser un transporte de
> propósito general (no observa imágenes ni decide nada de la detección) y por encajar con los
> módulos Bluetooth de la familia HC-05/HC-06 sobre un microcontrolador ATmega. **El profesor
> confirmó que el protocolo real es un byte ASCII por comando sobre un socket RFCOMM**, con lo que el
> puerto COM y su velocidad nunca existen: `pyserial` no tenía uso. Se retiró de `pyproject.toml` y
> de `uv.lock`, y la decisión vigente es la Decisión 7.

---

## Decisión 7: El protocolo es un byte ASCII sobre RFCOMM

> **⚠️ SUPERADA (2026-09-28) la decisión de formato de trama.** Este bloque **sustituye** el
> protocolo de 4 bytes con cabecera `0xA5` y checksum XOR que los contratos de esta feature
> definieron originalmente. Ese diseño estaba en `contracts/transporte-bluetooth.md`,
> `contracts/mapa-comandos.md` y `contracts/api-control.md` §6; los contratos se reescribieron el
> mismo día. El diseño anterior se conserva aquí solo como registro de lo que se decidió y por qué,
> **no** como especificación vigente.

### Qué decía el diseño anterior

| Aspecto | Diseño anterior (ya superado) |
|---------|-------------------------------|
| Tamaño | 4 bytes fijos |
| Cabecera | `0xA5`, para resincronizar el flujo |
| Opcode | `0x01` = `AVANZAR`, `0x02` = `IZQUIERDA`, `0x03` = `DERECHA`, `0x04` = `DETENER` |
| Payload | Reservado, `0x00` en v1 |
| Checksum | XOR de los 3 bytes anteriores |
| Transporte | Puerto COM del módulo Bluetooth, abierto con `pyserial` |
| Configuración | `puerto_serial` + `baudrate` (9600) |

**Por qué se eligió así**: una trama con cabecera y checksum es la forma habitual de hacer un enlace
de bytes robusto, y el argumento era que un receptor que lee un flujo continuo necesita saber dónde
empieza cada mensaje y detectar corrupción. Sobre esa base se justificó `baudrate = 9600` como
suficiente para 4 bytes, y de ahí la regla de validación `baudrate >= 1200` (V5).

### Qué cambió y por qué

El profesor envió el código de ejemplo del mBot y confirmó el canal. Tres hechos desmintieron el
diseño anterior:

1. **No hay puerto COM.** El enlace es un socket RFCOMM; no existe una velocidad de enlace que
   configurar. `baudrate` y `puerto_serial` desaparecen, y con ellos la regla V5 y la constante
   `9600`.
2. **No hay trama.** Cada comando es **un byte ASCII**: `w` = `AVANZAR`, `a` = `IZQUIERDA`,
   `d` = `DERECHA`, `x` = `DETENER`. Sin cabecera, sin payload, sin checksum, sin endianness y sin
   delimitador.
3. **No hace falta dependencia.** El socket se abre con `socket.AF_BLUETOOTH` + `SOCK_STREAM` +
   `socket.BTPROTO_RFCOMM` contra el canal 1 (SPP estándar) de la `mac_bluetooth`, y se escribe con
   `sendall()`. `socket` es de la biblioteca estándar, así que el transporte pasa a tener **cero
   dependencias de terceros**: no hay nada que declarar en `pyproject.toml` ni en `uv.lock`.

### Decisión

Se adopta el **byte único** sobre RFCOMM, con la tabla de mapeo del profesor como frontera
verificable entre el software de este equipo y el firmware del robot. Contrato normativo:
`contracts/transporte-bluetooth.md` §2–§4.

**Consecuencia colateral favorable**: al no haber trama, desaparecen de un plumazo toda una clase de
problemas que el diseño anterior tenía que resolver —resincronización del flujo, checksum,
receptor desfasado—, y no se pierde nada: con un solo byte no hay corrupción multi-byte que detectar.
El enlace queda **auto-sincronizable por construcción**: un byte perdido pierde un comando, nunca la
alineación.

**Configuración**: `puerto_serial` + `baudrate` → `mac_bluetooth` (string, default
`00:1B:10:21:2C:1B`) + `timeout_transporte_s` (0.20). El timeout pasa de ser la cota de un puerto
serie a ser la cota de una escritura bloqueada en el socket, con la misma razón: que un enlace
caído no congele el proceso. La validación V5 pasa a exigir el formato de MAC
(`XX:XX:XX:XX:XX:XX`), para que una MAC mal escrita falle al arrancar y no en el primer `connect`,
ya en pista.

**Supuesto declarado, no verificado**: se envía **exactamente un byte, sin salto de línea**, porque así
funciona un receptor que lee un byte por comando. El `Robot.py` del profesor **no está en este
repositorio**, así que el supuesto no pudo comprobarse contra la fuente. Si su receptor esperase un
terminador de línea, el cambio es la constante `SUFIJO` de `src/transporte/spp.py`. Queda registrado
como P3/P5 en `transporte-bluetooth.md` §8.

---

## Resumen de decisiones

| # | Decisión | Alternativa rechazada | Base de la evidencia |
|---|----------|----------------------|----------------------|
| 1 | Centroide del pico de proyección de columnas | Hough (norma), `fitLine` (riesgo normativo), run más largo (sd +55 %) | sd 50.5 vs 78.4 px; correlación cruzada +0.76/+0.86 |
| 2 | Bang-bang con zona muerta 0.10 + histéresis 0.03 | PID / control suave (imposible: la API no da magnitud) | % de fotogramas dentro de zona muerta por video |
| 3 | `x_objetivo` configurable (def. 0.5) | centro del fotograma como constante | medianas 190.0–286.5 px vs centro 239 |
| 4 | Memoria del último lado con `n_gracia = 5` | `DETENER` inmediato (penaliza tiempo), giro indefinido (descarrila) | vel. de error 52.1 px en desarrilamiento vs 15–20 en ideal |
| 5 | Composición con veto de la FSM | control manda (fallo de seguridad), tocar `DecisionMovimiento` (rompe 167 tests) | Precedencia de seguridad del Reto |
| 6 | `src/transporte/` + mock (**aislamiento vigente**; la dependencia queda superada) | `src/services/`/`src/models/` (§II) | Constitución §II sobre estructura |
| 7 | Byte único ASCII sobre socket RFCOMM, sin dependencia de terceros | Trama de 4 bytes con cabecera `0xA5` y checksum XOR (SUPERADA 2026-09-28); `pyserial` sobre COM | Protocolo confirmado por el profesor junto con su código de ejemplo del mBot |

## Riesgos abiertos

| Riesgo | Impacto | Mitigación en esta spec |
|--------|---------|--------------------------|
| **Signo del giro no validable en software** | Alto: si `error > 0` no significa «girar a la derecha», el robot invierte la corrección | Marcado como supuesto de riesgo en spec.md; `x_objetivo` y el signo se recalibran en pista |
| Zona muerta calibrada con cámara en mano | Medio: valores subóptimos en el robot | Marcado provisional; tarea de recalibración con footage propio |
| La máscara de línea es «cualquier píxel oscuro» (`v_max: 110`, H/S completo) | Medio: 15–17 % de ocupación; sombras contaminan | Fuera de alcance (corregido en cambio previo a nivel de ROI, no de rango); el estimador es tolerante por peakedness |
| `roi_linea` anidada dentro de `roi_senales` | Bajo: un píxel rojo oscuro (`v` 90–110) cae en ambas máscaras | Documentado en spec.md Dependencias; no afecta a US1 (solo usa `mascara_linea`) |
| `t_parada_s = 3.0` provisional | Bajo para esta spec | Fuera de alcance explícito (decisión del equipo) |
| **Supuesto de un byte sin salto de línea no verificado** | Alto si es falso: el receptor descartaría o acumularía bytes y el robot no obedecería | Declarado en Decisión 7 y en `transporte-bluetooth.md` §2; registrado como P3/P5. El `Robot.py` del profesor no está en el repositorio. El ajuste, si hace falta, es la constante `SUFIJO` |
