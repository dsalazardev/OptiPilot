# Contrato: API de Control de Trayectoria

**Feature**: `specs/002-control-trayectoria` | **Fecha**: 2026-09-28 | **Spec**: [spec.md](../spec.md)

Contrato entre las etapas `posicion_linea` → `control_trayectoria` → compositor → transporte. Define
los tipos públicos, sus invariantes y los errores que **no** deben ocurrir.

---

## 1. `EstimadorLinea` — etapa de posición de línea (Objetivo 3)

**Módulo**: `src/vision/posicion_linea.py` | **Técnica autorizada**: operaciones aritméticas y
lógicas sobre la máscara binaria (suma por columna, umbral de medio pico, media ponderada).

```python
class EstimadorLinea:
    def __init__(self, params: ParametrosConfiguracion) -> None: ...

    def aplicar(self, seg: ResultadoSegmentacion) -> PosicionLinea: ...
```

**Precondiciones**

| # | Precondición |
|---|---------------|
| P1 | `seg.mascara_linea` es un array 2D `uint8` con la misma forma que `mascara_roja`. |
| P2 | `seg.roi_linea` es un rectángulo de píxeles válido dentro del fotograma. |
| P3 | `params.frac_anticipacion in [0, 1)` y `params.frac_pico in (0, 1]`. |

**Postcondiciones**

| # | Postcondición |
|---|---------------|
| Q1 | Nunca lanza excepción por contenido de la máscara (vacía, negra, ruidosa). |
| Q2 | Si la máscara de la banda no tiene píxeles, devuelve `valida=False`, `x_px=None`, `confianza=0.0`. |
| Q3 | Si hay un pico dominante y `confianza >= umbral_confianza` y el pico no toca el borde, devuelve `valida=True`. |
| Q4 | `x_px` siempre en `[0, ancho]`. `x_norm = x_px / ancho` en `[0, 1]`. |
| Q5 | `error_norm = x_norm - params.x_objetivo` (con signo). |
| Q6 | Determinista: misma máscara ⟹ mismo resultado. |
| Q7 | Coste O(ancho × alto_banda) con operaciones vectorizadas; sin bucles por píxel. |

**Errores permitidos**

| Situación | Comportamiento requerido |
|------------|--------------------------|
| ROI de ancho o alto 0 | Rechazado en **carga de configuración** (`ConfiguracionInvalidaError`), no aquí. |
| Máscara vacía | `valida=False` (Q2). Sin excepción. |
| Varios picos de masa comparable | `confianza` baja por ambigüedad; si cae bajo el umbral, `valida=False`. **Nunca** promediar entre modos distintos. |
| Pico pegado al borde de la ROI | `confianza` penalizada; si no alcanza el umbral, `valida=False` (se trata como pérdida, no como posición en el borde). |

**Ejemplo de contrato** (no es un test, es la forma del resultado)

```python
# Banda con pico dominante centrado en x=200 de 478 px de ancho
pos = estimador.aplicar(seg)
pos.valida       # True
pos.x_px         # ~200.0
pos.x_norm       # ~0.418
pos.error_norm   # ~-0.082  (x_objetivo=0.5)  → línea a la izquierda
pos.confianza    # ~0.9
pos.ancho_banda_px  # anchura del soporte del pico
```

---

## 2. `ControlTrayectoria` — ley de control (Objetivo 4)

**Módulo**: `src/vision/control_trayectoria.py` | **Técnica autorizada**: comparación de umbral
con histéresis (lógica booleana), conteo de fotogramas.

```python
class ControlTrayectoria:
    def __init__(self, params: ParametrosConfiguracion) -> None: ...

    def decidir(self, pos: PosicionLinea) -> DecisionControl: ...
    def reiniciar(self) -> None: ...
```

`DecisionControl` es un `dataclass` frozen con:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `comando` | `ComandoMovimiento` | Propuesta de este fotograma |
| `causa` | `CausaComando` | Por qué se propuso (auditable) |
| `lateral` | `LadoConocido \| None` | Estado de la memoria de recuperación |

**Tabla de decisión completa** (especificación normativa)

| `pos.valida` | `error_norm` | Memoria | Comando | Causa |
|--------------|--------------|---------|---------|-------|
| `True` | `\|e\| < z - h` o `= z - h` | — | `AVANZAR` | `SEGUIMIENTO` |
| `True` | `z - h < \|e\| < z + h` | — | *(se mantiene el comando anterior; ver histéresis)* | *(la del comando anterior)* |
| `True` | `\|e\| >= z + h` y `e > 0` | — | `DERECHA` | `CORRECCION_DERECHA` |
| `True` | `\|e\| >= z + h` y `e < 0` | — | `IZQUIERDA` | `CORRECCION_IZQUIERDA` |
| `False` | — | vacía | `DETENER` | `PERDIDA_SIN_MEMORIA` |
| `False` | — | con lado, `1 <= perdidos <= n` | lado memorizado | `RECUPERACION` |
| `False` | — | con lado, `perdidos > n` | `DETENER` | `GRACIA_AGOTADA` |
| excepción interna | — | — | `DETENER` | `FALLO_SEGURO` |

**Postcondiciones**

| # | Postcondición |
|---|---------------|
| Q8 | `decidir` **nunca** lanza excepción al consumidor: cualquier fallo interno ⟹ `DETENER` + `FALLO_SEGURO` (FR-025). |
| Q9 | Nunca devuelve `None`. |
| Q10 | Con `pos.valida=True`, la memoria `lateral` se actualiza a `IZQUIERDA` si `e<0`, `DERECHA` si `e>0`, y se reinicia `fotogramas_perdidos=0`. |
| Q11 | Con `pos.valida=False`, `fotogramas_perdidos` se incrementa en 1; la memoria **no** se descarta. |
| Q12 | La histéresis usa dos umbrales: salida de `AVANZAR` a corrección solo si `\|e\| >= z + h`; retorno a `AVANZAR` solo si `\|e\| <= z - h`. En la banda intermedia el comando **se mantiene** (memoria del último comando del control). |
| Q13 | `reiniciar()` vacía la memoria del último lado (FR-023). |

**Nota sobre `e == 0` exactamente**: con `e = 0` se cumple `|e| < z - h` (porque `z - h = 0.07 > 0`),
así que el comando es `AVANZAR`. No hay ambigüedad en el origen.

---

## 3. Compositor — arbitraje de seguridad (FR-024–FR-027)

**Módulo**: `src/vision/compositor.py` (o función en `pipeline.py`) |

```python
def componer(
    decision: DecisionControl,
    movimiento: DecisionMovimiento,
    posicion: PosicionLinea,
) -> DecisionCompuesta: ...
```

> **Corrección 2026-09-28 (T025).** La firma original era
> `componer(decision, movimiento)`, que **no podía construir el resultado**:
> `DecisionCompuesta` exige además `posicion` y `permitido`. Se añadió `posicion`
> como tercer parámetro; `permitido` se toma de `movimiento.veredicto` y no
> necesita entrar. El fallo se detectó al escribir T024, no en revisión.

**Precedencia (normativa, en este orden)**

| # | Condición | Comando final | Causa |
|---|-----------|---------------|-------|
| 1 | `movimiento.veredicto == NO_AUTORIZADO` | `DETENER` | `VETO_FSM` |
| 2 | `decision.comando == DETENER` | `DETENER` | la causa de `decision` |
| 3 | en otro caso | `decision.comando` | la causa de `decision` |

**Reservado: `CausaComando.VETO_FSM`**. El control de trayectoria **no puede**
proponer `VETO_FSM`: describe una decisión del compositor, no suya. El modelo lo
hace cumplir, porque `DecisionCompuesta` rechaza construir una decisión con
`VETO_FSM` y un comando distinto de `DETENER`. La consecuencia observable es que
las dos paradas del sistema quedan distinguibles por su causa: «el control perdió
la línea» (`PERDIDA_SIN_MEMORIA`, `GRACIA_AGOTADA`, `FALLO_SEGURO`) frente a «el
PARE paró al robot» (`VETO_FSM`). Sin esa distinción, SC-007 no sería
demostrable en las métricas.

**Postcondiciones**

| # | Postcondición |
|---|---------------|
| Q14 | Si la FSM veta, el comando final es `DETENER` **siempre**, sin excepción (SC-007). |
| Q15 | `DecisionMovimiento` de 001 **no se modifica**: ni campos, ni semántica, ni valores. Las 167 pruebas existentes siguen válidas (FR-026). |
| Q16 | La causa del comando final queda registrada (FR-027). |
| Q17 | El compositor no inventa comandos: si `decision` es válida, la salida es `decision.comando` o `DETENER` por veto. |

**Por qué la FSM gana (justificación para la defensa)**: si el control ganara, un PARE confirmado en
el mismo fotograma podría ser pisado por una corrección de dirección y el robot **giraría en vez de
detenerse** — un fallo de seguridad directo y un «No cumple» en el criterio PARE de la rúbrica.

---

## 4. `ColaTransporte` — desacople (FR-031, FR-032)

**Módulo**: `src/transporte/cola.py`

```python
class ColaTransporte:
    def encolar(self, comando: ComandoMovimiento) -> bool: ...
    def drenar(self, transporte: Transporte) -> int: ...   # devuelve cuántos se transmitieron
    def pendientes(self) -> int: ...
    def ultimo_enviado(self) -> ComandoMovimiento | None: ...
```

**Postcondiciones**

| # | Postcondición |
|---|---------------|
| Q18 | `encolar` es O(1) y **no** hace I/O (FR-031). |
| Q19 | Si el comando es idéntico al último enviado y no hay pendientes, `encolar` lo **descarta** y devuelve `False` (deduplicación, FR-032). |
| Q20 | `drenar` transmite en orden FIFO. |
| Q21 | Si el envío falla, el comando **permanece en la cola** y se registra `ultimo_error`; no se pierde el estado (FR-034). |
| Q22 | `drenar` nunca lanza excepción al llamador, aunque el transporte esté desconectado. |
| Q23 | El bucle de visión invoca `encolar` **nunca** `drenar` (SC-005). |

---

## 5. Interfaz `Transporte` (FR-030)

**Módulo**: `src/transporte/base.py` | **Definición sin I/O**; las implementaciones sí hacen I/O.

```python
class Transporte(Protocol):
    def enviar(self, comando: ComandoMovimiento) -> bool: ...
    def cerrar(self) -> None: ...
    def conectado(self) -> bool: ...
    def ultimo_error(self) -> str | None: ...
```

| Implementación | Módulo | Enlace | Usada en |
|----------------|--------|---------|----------|
| `TransporteSimulado` | `src/transporte/simulado.py` | ninguno (memoria) | **Todas las pruebas** (FR-033) |
| `TransporteSPP` | `src/transporte/spp.py` | socket RFCOMM de la estándar | Integración real, fuera de `src/vision/` |

**Postcondiciones**

| # | Postcondición |
|---|--------------|
| Q24 | `enviar` devuelve `bool`; **nunca** lanza por desconexión, timeout o MAC inalcanzable (FR-034). |
| Q25 | `cerrar` es idempotente (múltiples llamadas no fallan). |
| Q26 | `conectado` es consultable sin excepción en cualquier momento. |
| Q27 | `ultimo_error` devuelve `None` si no hay fallo pendiente. |

**Conexión perezosa de `TransporteSPP`** (comportamiento normativo)

| # | Regla |
|---|------|
| R1 | El socket **no** se abre en el constructor: `__init__` solo guarda `mac_bluetooth`, `timeout_transporte_s` y la fábrica inyectable. |
| R2 | La apertura ocurre en el **primer `enviar`**: `socket(AF_BLUETOOTH, SOCK_STREAM, BTPROTO_RFCOMM)`, `settimeout(timeout_transporte_s)`, `connect((mac_bluetooth, 1))`. |
| R3 | Canal fijo **1** (SPP estándar); no se configura. |
| R4 | La fábrica de sockets es **inyectable**: las pruebas ejercitan envío y fallo contra un doble, sin hardware y sin proveedor de Bluetooth en el SO. |
| R5 | Si `AF_BLUETOOTH` o `BTPROTO_RFCOMM` no existen en la plataforma, se registra el motivo y `enviar` devuelve `False`; **no** es una excepción. |
| R6 | Un envío posterior a una desconexión reabre el enlace best-effort una vez; si falla, sigue devolviendo `False` sin lanzar. |

**Por qué la apertura es perezosa**: abrir en el constructor ataría el fallo de conexión al arranque
del proceso, y el CLI debe poder arrancar y validar el pipeline **sin** robot. La conexión se hace
efectivamente en el primer envío.

---

## 6. Formato del mensaje del protocolo (ver `transporte-bluetooth.md`)

Resumen; el formato completo vive en su propio contrato.

```text
  mensaje = Byte(1) = carácter ASCII del comando
```

| Elemento | Valor |
|----------|-------|
| Tamaño | **1 byte**, longitud fija |
| Contenido | `w` = `AVANZAR`, `a` = `IZQUIERDA`, `d` = `DERECHA`, `x` = `DETENER` |
| Trama / cabecera / payload | **No existen** |
| Checksum / endianness / delimitador | **No existen** |

Se escribe con `sendall(serializar(comando))`. El enlace es **auto-sincronizable por construcción**:
como cada mensaje es un byte completo e independiente, un byte perdido pierde un comando, nunca la
alineación del flujo.

**Supuesto declarado (no verificado)**: se envía exactamente un byte, **sin salto de línea**, porque
así funciona un receptor que lee un byte por comando. El `Robot.py` del profesor no está en este
repositorio, así que el supuesto no pudo comprobarse contra la fuente. Queda registrado como pregunta
abierta P3/P5 (`transporte-bluetooth.md` §8).

---

## 7. Errores que el contrato prohíbe explícitamente

| Prohibido | Por qué |
|-----------|---------|
| Excepciones por contenido de imagen (máscara vacía, negro, ruidosa) | El bucle de tiempo real no puede detenerse (Principio IV, Q1/Q2) |
| `None` como resultado de `decidir` | El consumidor quedaría sin comando; `DETENER` es el valor seguro (Q9) |
| Que la FSM sea consultada **después** de emitir el comando | Un PARE podría ser pisado por una corrección (fallo de seguridad) |
| Modificar `DecisionMovimiento` o `ResultadoSegmentacion` de 001 | Rompe 167 pruebas y mezcla responsabilidades (FR-026) |
| Llamadas de escritura bloqueantes en el bucle de visión | Rompe SC-005 y el Principio IV («sin operaciones bloqueantes») |
| Usar `HoughLinesP` o `fitLine` | Principio I y §III: detección automática de la línea (FR-003) |
| `x_objetivo` fijo en el código | Depende del montaje físico; debe ser parámetro (FR-005) |
| Git-tracked `.venv`, secretos o una MAC de destino hardcodeada en el código | Principio III; la MAC es un parámetro de configuración (`mac_bluetooth`) |

---

## 8. Trazabilidad FR ↔ contrato

| FR | Sección del contrato |
|----|----------------------|
| FR-001..FR-010 | §1 `EstimadorLinea` (Q1–Q7) |
| FR-011..FR-017 | §2 `ControlTrayectoria` (Q8–Q13) |
| FR-018..FR-023 | §2 (Q10, Q11, Q13) + `LadoConocido` en data-model |
| FR-024..FR-027 | §3 Compositor (Q14–Q17) |
| FR-028..FR-035 | §5 `Transporte` (Q24–Q27) + `transporte-bluetooth.md` |
| FR-031, FR-032 | §4 `ColaTransporte` (Q18–Q23) |
| FR-036, FR-037 | `MetricasControl` y `EventoControl` en data-model |

| SC | Cómo se verifica |
|----|------------------|
| SC-001 | `MetricasControl.correcciones <= 3` sobre `videos/rutaIdeal/` |
| SC-002 | `recuperaciones_ok > 0`, `recuperaciones_fallidas == 0` sobre `videos/desarrilamiento/` con huecos ≤ N |
| SC-003 | `causa != CORRECCION_*` cuando `pos.valida == False` |
| SC-004 | `MetricasControl.latencia_decision_ms` ≤ 267 ms |
| SC-005 | Benchmark de `encolar` con `TransporteSimulado`; latencia del bucle sin `drenar` |
| SC-006 | Correlación cruzada ≥ 0.7 entre dos estimadores sobre el footage |
| SC-007 | `causa == VETO_FSM ⟹ comando == DETENER` en el 100 % de fotogramas DETENIDO |
| SC-008 | Suite de protocolo con `TransporteSimulado`, 0 excepciones no capturadas |
| SC-009 | `EventoControl` renderizado en `visualizacion.py` |
