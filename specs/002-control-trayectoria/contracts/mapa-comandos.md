# Contrato: Mapa de Comandos (API de control hacia el robot)

**Feature**: `specs/002-control-trayectoria` | **Fecha**: 2026-09-28 | **Spec**: [spec.md](../spec.md)

Documento de frontera entre el **cerebro de visión** (este proyecto) y el **robot** (fuera del
repositorio). Define los cuatro comandos que el profesor confirmó, su semántica, su mapeo a la
máquina de estados y su representación en la evidencia visual.

> Este documento es material de **póster y defensa oral** (criterios 5, 8, 9 y 10 de la rúbrica):
> hace visible que la API es una decisión de diseño del equipo, no un detalle del firmware.

---

## 1. Los cuatro comandos

El profesor fijó el vocabulario. No hay más comandos ni menos: **no existe comando de velocidad, de
distancia, de duración de giro ni de retroceso**. Esa restricción es la razón por la que la ley de
control es bang-bang por construcción (`research.md` Decisión 2).

| Comando | Significado | Se emite cuando | Opcode SPP |
|---------|-------------|-----------------|------------|
| `AVANZAR` | El robot avanza recto siguiendo la línea | La línea está dentro de la zona muerta | `0x01` |
| `IZQUIERDA` | El robot corrige hacia la izquierda | La línea está a la izquierda del objetivo, o búsqueda por memoria hacia la izquierda | `0x02` |
| `DERECHA` | El robot corrige hacia la derecha | La línea está a la derecha del objetivo, o búsqueda por memoria hacia la derecha | `0x03` |
| `DETENER` | El robot se detiene | Pérdida de línea sin memoria, gracia agotada, veto por PARE, o fallo interno | `0x04` |

### Precisión semántica importante

`IZQUIERDA` y `DERECHA` significan **«la línea está de ese lado»**, no «el motor gira a ese lado».

Que la orden física corresponda depende del montaje: si la cámara está volteada 180° respecto al eje
del robot, `DERECHA`software se convierte en giro a la izquierda en el mundo. **Esta correspondencia
no puede validarse en software** y queda como supuesto de riesgo explícito (ver §5 y `spec.md`
Supuestos). La decisión de diseño que sí se controla aquí es que el control sea **simétrico al signo
del error**: cambiar `x_objetivo` o invertir la calibración de la cámara corrige la convención sin
tocar la lógica de control.

---

## 2. Tabla de decisión completa

Una sola tabla gobierna el comportamiento; sirve como referencia de implementación
(`api-control.md` §2), como material del póster y como oráculo de las pruebas.

| `pos.valida` | `error_norm` | Memoria | Comando | Causa |
|--------------|--------------|---------|---------|-------|
| `True` | `\|e\| <= zona_muerta − histeresis` | — | `AVANZAR` | `SEGUIMIENTO` |
| `True` | banda de histéresis | — | se mantiene | (la anterior) |
| `True` | `e >= zona_muerta + histeresis` | — | `DERECHA` | `CORRECCION_DERECHA` |
| `True` | `e <= −(zona_muerta + histeresis)` | — | `IZQUIERDA` | `CORRECCION_IZQUIERDA` |
| `False` | — | vacía | `DETENER` | `PERDIDA_SIN_MEMORIA` |
| `False` | — | con lado, `1 <= perdidos <= n_gracia` | lado memorizado | `RECUPERACION` |
| `False` | — | con lado, `perdidos > n_gracia` | `DETENER` | `GRACIA_AGOTADA` |
| — | — | — | `DETENER` | `VETO_FSM` (PARE manda) |
| — | excepción | — | `DETENER` | `FALLO_SEGURO` |

`error_norm = (x_norm − x_objetivo)`: **positivo = la línea está a la derecha del objetivo**.

---

## 3. Precedencia: qué comando gana

Dos fuentes producen un comando en cada fotograma —el control de trayectoria y la máquina de
estados— y hay un orden de precedencia estricto:

```text
 1. Veto por PARE/SIGA (FSM = NO AUTORIZADO)  ──>  DETENER
 2. Fallo seguro del control (línea perdida, gracia agotada, excepción)  ──>  DETENER
 3. En otro caso  ──>  el comando propuesto por el control
```

**`DETENER` siempre gana.** Es la regla de seguridad del proyecto y se verifica en el 100 % de los
fotogramas del estado `DETENIDO` (SC-007).

Por qué: si el control tuviera la última palabra, un PARE confirmado en el mismo fotograma podría
ser pisado por una corrección de dirección, y el robot **giraría en vez de detenerse**. Eso es un
fallo de seguridad y un «No cumple» en el criterio PARE de la rúbrica. La decisión está argumentada
en `research.md` Decisión 5.

---

## 4. Ejemplos de recorrido (para la defensa oral)

### Escenario A — seguimiento normal

| Fotograma | Observación | `error_norm` | Comando |
|-----------|-------------|--------------|---------|
| 0 | línea centrada | 0.00 | `AVANZAR` |
| 1 | línea deriva a la derecha | +0.12 | `DERECHA` |
| 2 | corrección funciona | +0.05 | `AVANZAR` |
| 3 | estabilizado | +0.02 | `AVANZAR` |

Correcciones en la corrida: **1** (el robot corrigió una vez y se estabilizó). Nivel «Cumple» del
criterio «Corrección de trayectoria».

### Escenario B — parpadeo del sensor (recuperación)

| Fotograma | Observación | Memoria | Comando | Causa |
|-----------|-------------|---------|---------|-------|
| 0 | línea a la derecha | DERECHA | `DERECHA` | `CORRECCION_DERECHA` |
| 1 | **línea perdida** | DERECHA, 0 perdidos | `DERECHA` | `RECUPERACION` |
| 2 | **línea perdida** | DERECHA, 1 perdido | `DERECHA` | `RECUPERACION` |
| 3 | línea reaparece a la derecha | — | `DERECHA` → `AVANZAR` al estabilizar | `SEGUIMIENTO` |

El robot **no se detuvo** por un parpadeo de 2 fotogramas. `recuperaciones_ok` aumenta,
`recuperaciones_fallidas` no. Es exactamente lo que puntúa «capacidad de recuperar la trayectoria».

### Escenario C — pérdida real (fallo seguro)

| Fotograma | Observación | Memoria | Comando | Causa |
|-----------|-------------|---------|---------|-------|
| 0 | línea a la izquierda | IZQUIERDA | `IZQUIERDA` | `CORRECCION_IZQUIERDA` |
| 1–5 | **línea perdida** | IZQUIERDA, 1..5 (`perdidos <= n_gracia`) | `IZQUIERDA` | `RECUPERACION` |
| 6 | **línea sigue perdida** | IZQUIERDA, 6 (`perdidos > n_gracia`) | `DETENER` | `GRACIA_AGOTADA` |

Con `n_gracia = 5` el robot busca 5 fotogramas y se detiene en el 6.º: la ventana es de N fotogramas y
el `DETENER` cae en el N+1.

Al agotarse la ventana el robot se detiene en vez de seguir girando fuera de la pista.
`recuperaciones_fallidas` aumenta y se registra como incidencia para el análisis de resultados.

### Escenario D — PARE durante una corrección (precedencia)

| Fotograma | Control propone | FSM | **Comando final** | Causa |
|-----------|-----------------|-----|-------------------|-------|
| 0 | `DERECHA` | AUTORIZADO | `DERECHA` | `CORRECCION_DERECHA` |
| 1 | `DERECHA` | **NO AUTORIZADO** (PARE) | **`DETENER`** | `VETO_FSM` |
| 2 | `AVANZAR` | NO AUTORIZADO | `DETENER` | `VETO_FSM` |

Este es el escenario que justifica la Decisión 5: sin el veto, el fotograma 1 habría enviado
`DERECHA` y el robot habría girado en vez de detenerse ante el PARE.

### Escenario E — arranque sin línea

| Fotograma | Observación | Memoria | Comando | Causa |
|-----------|-------------|---------|---------|-------|
| 0 | sin línea (robot mal posicionado) | vacía | `DETENER` | `PERDIDA_SIN_MEMORIA` |

No hay hacia dónde buscar: el robot no gira a ciegas.

---

## 5. Convenciones de calibración (riesgo abierto)

Este bloque es **deliberadamente visible**: el riesgo existe y conviene declararlo antes de que lo
pregunten en la defensa.

| # | Supuesto | Cómo se confirma | Qué se ajusta si es falso |
|---|----------|------------------|---------------------------|
| R1 | `error_norm > 0` ⟹ la línea está a la derecha ⟹ `DERECHA` produce un giro a la derecha real | Pista: colocar el robot con la línea desplazada a la derecha y observar | Invertir el mapeo en el compositor, o corregir el montaje de la cámara. **La lógica de control no cambia** (es simétrica al signo). |
| R2 | `x_objetivo = 0.5` es el punto neutro | Grabación con la cámara montada y la línea centrada | Recalibrar `x_objetivo` en `config/vision.json` |
| R3 | `zona_muerta = 0.10` evita oscilación en el robot real | Medir la tasa de correcciones en pista | Ajustar `zona_muerta` y `histeresis` |
| R4 | `n_gracia_busqueda = 5` basta para recuperar sin descarrilar | Provocar una pérdida controlada | Ajustar según la cinemática real |

**R1 es el más importante**: es el único que no puede fallar en software, y por eso la ley de control
se escribió simétrica al signo del error — para que corregirlo sea un parámetro, no un rediseño.

---

## 6. Evidencia visual por comando (material del póster)

`visualizacion.py` extiende el modo diagnóstico de 001 con, para cada fotograma:

| Elemento | Representación | Para qué sirve |
|----------|----------------|----------------|
| Máscara de línea | Superposición, como en 001 | Contexto de la detección |
| Posición estimada | Marca vertical sobre `x_px` | Ver US1 en acción |
| Objetivo | Línea vertical en `x_objetivo` | Ver la referencia de «centrado» |
| Zona muerta | Dos líneas verticales en `x_objetivo ± zona_muerta` | Ver por qué no corrige |
| Banda de histéresis | Líneas en `± histeresis` (más finas) | Ver la anti-oscilación |
| Comando emitido | Texto grande: `AVANZAR` / `IZQUIERDA` / `DERECHA` / `DETENER` | Ver la decisión |
| Causa | Texto pequeño: `SEGUIMIENTO`, `VETO_FSM`, `RECUPERACION`… | Ver **por qué** (criterio 9) |
| Memoria de lado | Indicador `último: IZQ (2)` durante la búsqueda | Ver US3 en acción |
| Velocidad de error | Gráfico de `Δx` por fotograma | Distinguir cámara en mano de desarrilamiento |

Los colores propuestos: `AVANZAR` verde, `IZQUIERDA`/`DERECHA` ámbar, `DETENER` rojo; el comando en
rojo se dibuja más grande porque es la decisión de seguridad. Con `--diagnostico` el 100 % de los
fotogramas generan esta evidencia (SC-009).

---

## 7. Trazabilidad

| Origen | Destino en este documento |
|--------|--------------------------|
| `ComandoMovimiento` (data-model §5) | §1 (los cuatro valores) |
| `CausaComando` (data-model §6) | §2 (tabla de decisión) |
| Precedencia de seguridad (`api-control.md` §3) | §3 |
| Escenarios de aceptación US2/US3 (spec.md) | §4 (escenarios A–E) |
| Opcodes SPP (`transporte-bluetooth.md` §3) | §1 (columna Opcode) |
| Riesgos abiertos (`research.md`, `spec.md` Supuestos) | §5 |
| FR-037, SC-009 (evidencia visual) | §6 |
