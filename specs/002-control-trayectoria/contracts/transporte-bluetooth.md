# Contrato: Transporte de Comandos por Bluetooth Classic (SPP/RFCOMM)

**Feature**: `specs/002-control-trayectoria` | **Fecha**: 2026-09-28 | **Spec**: [spec.md](../spec.md)

Contrato del canal de comunicación entre el cerebro de visión (nuestra PC) y el robot
(microcontrolador con módulo Bluetooth Classic tipo HC-05/HC-06). Define el **formato del mensaje**,
el comportamiento del enlace y la condición de fallo seguro.

> **Alcance del canal**: es **unidireccional**. Solo enviamos comandos; no leemos sensores, no
> pedimos acuses y no hay telemetría de retorno (decisión de equipo, ver `spec.md` US4).

---

## 1. Justificación de la elección técnica

> **Revisión 2026-09-28 (cambio de protocolo).** El profesor envió el código de ejemplo del mBot
> (`Robot.py`) y confirmó el canal. Este contrato se reescribió por completo: antes definía una trama
> de 4 bytes con checksum sobre `pyserial` y un puerto COM; **ninguna de las dos cosas existe ya**.
> El protocolo real es un byte ASCII por comando sobre un socket RFCOMM.

| Decisión | Elección | Alternativas descartadas |
|----------|----------|--------------------------|
| Perfil Bluetooth | **Classic (SPP/RFCOMM)** | BLE/GATT (`bleak`): el microcontrolador no expone un servicio GATT definido por el equipo |
| Mecanismo | **`socket.AF_BLUETOOTH` + `SOCK_STREAM` + `BTPROTO_RFCOMM`** (biblioteca estándar) | `pyserial` sobre un puerto COM virtual: era la suposición inicial del equipo y queda desmentida por el código del profesor |
| Capa física | Enlace RFCOMM directo a la MAC del mBot, canal 1 | — |
| Baudrate | **No aplica**: no hay puerto serie | — |
| Dependencias | **Ninguna de terceros**: `socket` viene en la estándar | `pyserial`, retirada de `pyproject.toml` y de `uv.lock` |

`socket` es un transporte de **propósito general**: no observa imágenes ni toma decisiones de
detección. Su encaje en el Principio III es directo y se documenta en `plan.md`.

**Ventaja colateral de la revisión**: al no haber trama, desaparece toda una clase de problemas que
el diseño anterior tenía que resolver (resincronización, checksum, receptor desfasado). El protocolo
es más pequeño **y** más seguro, porque el estado interno del enlace no puede desfasarse respecto a
la posición del flujo de bytes.

**Estructura de la decisión (Principio I / §II)**: la interfaz `Transporte` y el mapeo de comandos son
propios del equipo y definen la lógica; `socket` solo mueve bytes. El microcontrolador receptor
interpreta las letras por su cuenta (fuera de este repositorio).

---

## 2. Formato del mensaje

**Un byte por comando.** No hay trama, ni cabecera, ni longitud, ni payload, ni checksum, ni endianness.

| Elemento | Valor | Notas |
|----------|-------|-------|
| Tamaño | **1 byte** | Longitud fija de 1, sin campos multi-byte |
| Contenido | Carácter ASCII del comando | Ver tabla §3 |
| Delimitador | **Ninguno** | Cada `sendall()` es un comando completo y autónomo |
| Checksum | **Ninguno** | Con un solo byte no hay corrupción multi-byte que detectar |

### Reglas de decodificación (receptor)

1. Leer un byte.
2. Compararlo con la tabla §3.
3. Si no coincide, descartarlo.
4. Ejecutar el comando.

El enlace es **auto-sincronizable por construcción**: como cada mensaje es un byte completo e
independiente, no existe estado interno que pueda quedar desfasado. Un byte perdido se pierde un
comando, nunca la alineación del flujo.

**Supuesto declarado (no verificado).** Se envía **exactamente un byte, sin salto de línea**, porque
así funciona un receptor que lee `recv(1)` por comando. El código `Robot.py` del profesor **no está en
este repositorio**, de modo que esta suposición no pudo comprobarse contra la fuente; si su receptor
esperase un terminador de línea, el cambio es una constante (`SUFIJO` en `src/transporte/spp.py`) y
afecta a una sola línea del proyecto. Queda registrado como pregunta abierta P5 (§7).

---

## 3. Tabla de comandos (mapa de bytes)

| Comando | Byte | Hex | Significado para el robot |
|---------|------|-----|--------------------------|
| `AVANZAR` | `w` | `77` | Avanza recto |
| `IZQUIERDA` | `a` | `61` | Corrige hacia la izquierda |
| `DERECHA` | `d` | `64` | Corrige hacia la derecha |
| `DETENER` | `x` | `78` | Detiene (incluye parada de seguridad) |

Los cuatro bytes son distintos y ninguno es un valor de control ni un espacio: no hay ambigüedad
posible con la configuración del enlace. `DETENER` usa `x` y no `w`, de modo que una parada nunca puede
confundirse con un avance.

**Tabla ↔ dominio**: esta tabla es la frontera verificable entre la decisión de software y el
firmware del robot. El póster puede mostrar la tabla completa como "nuestra API hacia el robot"
(criterio 9 de la rúbrica: explicar la decisión).

---

## 4. Contrato de la interfaz `Transporte`

```python
class Transporte(Protocol):
    def enviar(self, comando: ComandoMovimiento) -> bool: ...
    def cerrar(self) -> None: ...
    def conectado(self) -> bool: ...
    def ultimo_error(self) -> str | None: ...
```

### Semántica de `enviar`

| # | Regla |
|---|------|
| T1 | Serializa el comando a **1 byte ASCII** y lo entrega con `sendall()`. |
| T2 | Devuelve `True` si el socket aceptó el envío; `False` si el enlace está caído o no se pudo abrir. |
| T3 | **Nunca** lanza excepción por desconexión, timeout o MAC inalcanzable (FR-034). Cualquier fallo se captura, se registra en `ultimo_error` y se devuelve `False`. |
| T4 | Es idempotente con el mismo comando consecutive a nivel de `ColaTransporte` (no aquí): la deduplicación vive en la cola, no en el transporte. |

### Semántica de `cerrar`

| # | Regla |
|---|------|
| T5 | Cierra el socket y libera el recurso. |
| T6 | Es **idempotente**: llamarla dos veces no falla. |
| T7 | Tras cerrar, `enviar` devuelve `False` sin lanzar. |

### Semántica de `conectado` / `ultimo_error`

| # | Regla |
|---|------|
| T8 | `conectado()` es consultable en cualquier momento sin excepción. |
| T9 | `ultimo_error()` devuelve `None` si no hay fallo pendiente, o un mensaje legible. |

### Comportamiento de `TransporteSPP` (implementación real)

| Aspecto | Comportamiento |
|---------|----------------|
| Destino | `params.mac_bluetooth` (p. ej. `"00:1B:10:21:2C:1B"`), canal RFCOMM 1 |
| Apertura | `socket(familia, SOCK_STREAM, BTPROTO_RFCOMM)` + `connect((mac, 1))`, **perezosamente en el primer `enviar`**, nunca en `__init__` |
| Timeout | `params.timeout_transporte_s` (0.2 s por defecto) para que una escritura bloqueada no congele el proceso |
| Fallo de apertura | MAC inalcanzable o sin pairing: se captura, se registra, `conectado()` queda `False`, `enviar()` devuelve `False` |
| Reconexión | Tras una desconexión, el siguiente `enviar` reabre best-effort una vez; si falla, sigue devolviendo `False` sin lanzar |
| Sin Bluetooth en el SO | Si `socket.AF_BLUETOOTH` no existe (plataforma sin proveedor de Bluetooth), se registra el motivo y `enviar()` devuelve `False`. **No** es una excepción: la suite debe correr en cualquier máquina |
| Fábrica de sockets | Inyectable, para que los tests ejerciten envío y fallo sin hardware |
| `serial` | **No se importa en ningún módulo**: el enlace es RFCOMM puro |

**Por qué el timeout importa**: sin él, un enlace caído puede bloquear el `sendall` durante segundos.
Con `timeout_transporte_s=0.2`, el peor caso acotado es compatible con el presupuesto de tiempo real, y
de todos modos la escritura ocurre **fuera** del bucle de visión (`ColaTransporte`).

**Por qué la apertura es perezosa**: abrir en `__init__` ataría el fallo de conexión al arranque del
proceso, y el CLI debe poder arrancar y validar el pipeline **sin** robot. La conexión se hace
efectivamente en el primer envío.

---

## 5. Comportamiento de `ColaTransporte` (desacople)

`ColaTransporte` es el puente entre el bucle de visión y la radio.

```text
  bucle de visión (tiempo real)          hilo de transporte (no bloqueante para el anterior)
  ─────────────────────────────          ──────────────────────────────────────────────
  decision = control.decidir(pos)  ──>  cola.encolar(decision.comando)      [O(1), sin I/O]
  decision = compositor.componer(...) ──> cola.encolar(...)  (o descarta si idéntico)
                                           │
                                           └──> cola.drenar(transporte)  [hace el write real]
```

| # | Regla |
|---|------|
| T10 | `encolar` **nunca** hace I/O y es O(1). |
| T11 | Si el comando es idéntico al último enviado y no hay nada pendiente, `encolar` lo **descarta** (deduplicación, FR-032). Esto evita saturar la radio con repeticiones a 30 fps. |
| T12 | `drenar` transmite en **FIFO**. |
| T13 | Si el envío falla, el comando **permanece en la cola** para reintento; `ultimo_error` se registra (FR-034). |
| T14 | El bucle de visión **nunca** llama a `drenar`; esa separación es lo que garantiza SC-005. |
| T15 | `pendientes()` permite observar la salud del enlace como métrica (un backlog que crece indica un problema de radio). |

**¿Por qué deduplicar?** El bucle de visión corre a ~30 fps, pero la utilidad de una corrección de
dirección dura varios fotogramas. Enviar el mismo byte 30 veces no aporta nada y consume el enlace.
La deduplicación transmite **solo transiciones de estado**, que es la información útil para el robot.

---

## 6. Contrato de `TransporteSimulado` (para pruebas headless)

| # | Regla |
|---|------|
| T16 | Implementa la misma interfaz sin hardware. |
| T17 | Registra cada comando recibido en una lista consultable (`historial()`). |
| T18 | Permite inyectar fallos (`fallar_con(n)`: los siguientes `n` envíos devuelven `False`) para probar la reconexión y la persistencia en cola. |
| T19 | Es el transporte por defecto de **todas** las pruebas de control y de protocolo (FR-033, Principio V). |

Con `TransporteSimulado` se puede demostrar el protocolo entero —secuencia, deduplicación,
desconexión, reconexión, precedencia del veto— sin robot, en CI, en headless.

---

## 7. Condiciones de fallo y comportamiento de seguridad

| Fallo | Comportamiento del software | Comando en la radio |
|-------|------------------------------|---------------------|
| MAC inalcanzable o sin pairing | `enviar → False`, `ultimo_error` registrado, bucle sigue | El último comando sigue vigente en el robot (se mantiene hasta nuevo comando) |
| Módulo BT desconectado | Igual que arriba; se intenta reabrir en el siguiente envío | Sin cambio |
| `sendall` falla a mitad | El comando se pierde entero; como no hay estado interno en el protocolo, el receptor no queda desfasado: el siguiente byte es un comando completo | Sin cambio parcial |
| Escena sin línea y sin memoria | `DETENER` se encola y se transmite | Robot se detiene (fallo seguro) |
| PARE confirmado | `DETENER` por `VETO_FSM`; ninguna corrección se transmite (SC-007) | Robot se detiene |
| Excepción interna en el control | `DETENER` + `FALLO_SEGURO` (FR-025) | Robot se detiene |

**Principio rector**: un fallo de transporte **nunca cambia la decisión de control** (FR-034). Si la
radio falla, el control sigue decidiendo igual; lo que se pierde es la entrega, no la seguridad. Y
`DETENER` es el único comando cuyo envío es prioritario: ante cualquier duda, detener.

---

## 8. Preguntas abiertas para el docente / el firmware del receptor

Estas no bloquean la implementación del lado de software (el `TransporteSimulado` y el contrato son
suficientes), pero deben resolverse antes de la demostración en pista:

| # | Pregunta | Por qué importa | Quién decide |
|---|----------|-----------------|--------------|
| P1 | ¿El receptor reintenta o el software reintenta? | Afecta a la lógica de `ColaTransporte.drenar` | Equipo + firmware |
| P2 | ¿Se envía algún byte de "listo" al arrancar? | El robot podría necesitar un heartbeat para no dormir | Equipo + firmware |
| P3 | ¿El receptor lee `recv(1)` por comando o lee hasta un delimitador? | Si espera un terminador de línea, hay que enviar `SUFIJO` además del byte | Firmware |
| P4 | ¿Cómo se comporta el robot si recibe `DETENER` repetido? | ¿Idempotente (parar es parar) o re-dispara? | Firmware |
| P5 | ¿Cuál es la MAC exacta del mBot de pista? | El valor por defecto es una suposición de trabajo, no un dato del docente | Docente |

Sobre **P3**: el código `Robot.py` del profesor no está en este repositorio, así que el supuesto
"un byte, sin delimitador" no pudo verificarse contra la fuente. El cambio, si hiciera falta, es una
constante en `src/transporte/spp.py` y no altera el resto del diseño.

Estas preguntas se registran en `AGENTS.md` §27 (vacíos dependientes del docente) según el Principio VI.

---

## 9. Trazabilidad FR ↔ contrato de transporte

| FR | Sección |
|----|---------|
| FR-028 (SPP/RFCOMM con `socket` de la estándar) | §1, §4 (`TransporteSPP`) |
| FR-029 (**sin dependencia de terceros**; nada que declarar) | §1, `plan.md` |
| FR-030 (interfaz delgada) | §4 (`Transporte` Protocol) |
| FR-031 (no bloqueante) | §5 (`ColaTransporte`), T10, T14 |
| FR-032 (deduplicar) | §5, T11 |
| FR-033 (mock para pruebas) | §6 (`TransporteSimulado`) |
| FR-034 (fallo sin excepción, sin cambiar decisión) | §4 (T3), §7 |
| FR-035 (documentar el formato del mensaje) | §2, §3 |
| FR-024 (DETENER por veto) | §7, y `api-control.md` §3 |
| SC-005 (no bloquea el bucle) | §5, T14 |
| SC-007 (veto siempre DETENER) | §7 |
| SC-008 (pruebas headless del protocolo) | §6 |
