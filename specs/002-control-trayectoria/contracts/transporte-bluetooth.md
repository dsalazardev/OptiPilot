# Contrato: Transporte de Comandos por Bluetooth Classic (SPP/RFCOMM)

**Feature**: `specs/002-control-trayectoria` | **Fecha**: 2026-09-28 | **Spec**: [spec.md](../spec.md)

Contrato del canal de comunicación entre el cerebro de visión (nuestra PC) y el robot
(microcontrolador con módulo Bluetooth Classic tipo HC-05/HC-06). Define el **formato de trama**,
el comportamiento del enlace y la condición de fallo seguro.

> **Alcance del canal**: es **unidireccional**. Solo enviamos comandos; no leemos sensores, no
> pedimos acuses y no hay telemetría de retorno (decisión de equipo, ver `spec.md` US4).

---

## 1. Justificación de la elección técnica

| Decisión | Elección | Alternativas descartadas |
|----------|----------|--------------------------|
| Perfil Bluetooth | **Classic (SPP/RFCOMM)** | BLE/GATT (`bleak`): el microcontrolador no expone un servicio GATT definido por el equipo |
| Librería | **`pyserial`** | APIs nativas de Windows: más frágiles y menos portables |
| Capa física | Puerto serie virtual (COM en Windows) | — |
| Baudrate | **9600** (configurable) | Tasa alta: más bytes por trama sin beneficio; 9600 basta para 4 bytes |

`pyserial` es un transporte de **propósito general**: no observa imágenes ni toma decisiones de
detección. Su encaje en el Principio III es directo y se documenta en `plan.md`.

**Estructura de la decisión (Principio I / §II)**: la interfaz `Transporte` es propia del equipo y
define la lógica; `pyserial` solo mueve bytes. El microcontrolador receptor implementa la decodificación
de tramas por su cuenta (fuera de este repositorio).

---

## 2. Formato de trama

Longitud fija de **4 bytes**. No hay endianness que considerar: son bytes discretos con un orden fijo,
no campos numéricos multi-byte.

```text
 ┌─────────┬─────────┬─────────┬───────────┐
 │ Header  │ Opcode  │ Payload │ Checksum  │
 │ 0xA5    │ 1 byte  │ 1 byte  │ 1 byte    │
 └─────────┴─────────┴─────────┴───────────┘
```

| Campo | Bytes | Valor | Propósito |
|-------|-------|-------|-----------|
| `Header` | 1 | `0xA5` fijo | Marca de inicio. Permite al receptor resincronizar si pierde el hilo del flujo. |
| `Opcode` | 1 | ver tabla §3 | Identifica el comando. |
| `Payload` | 1 | `0x00` reservado | Espacio a futuro sin cambiar el tamaño de trama. |
| `Checksum` | 1 | XOR de los 3 bytes previos | Detecta corrupción de un solo byte; una trama con checksum incorrecto se descarta. |

**Trama válida** = 4 bytes donde `Header==0xA5` y `Checksum == (Header ^ Opcode ^ Payload)`.

### Reglas de decodificación (receptor)

1. Descartar cualquier byte hasta encontrar `0xA5`.
2. Leer los 3 bytes siguientes como `Opcode`, `Payload`, `Checksum`.
3. Si `Checksum` no valida, descartar la trama y volver a buscar `Header` (resincronización).
4. Si `Opcode` no está en la tabla, descartar.
5. Ejecutar el comando.

Estas reglas hacen que el protocolo sea **auto-sincronizable**: una pérdida de bytes no deja al
receptor ejecutando comandos desfasados.

---

## 3. Tabla de opcodes (mapa de comandos)

| Comando | `Opcode` | Trama completa (hex) | Significado para el robot |
|---------|----------|----------------------|--------------------------|
| `AVANZAR` | `0x01` | `A5 01 00 A4` | Avanza recto |
| `IZQUIERDA` | `0x02` | `A5 02 00 A7` | Corrige hacia la izquierda |
| `DERECHA` | `0x03` | `A5 03 00 A6` | Corrige hacia la derecha |
| `DETENER` | `0x04` | `A5 04 00 A1` | Detiene (incluye parada de seguridad) |

Los cuatro checksums se han verificado como `Header ^ Opcode ^ Payload`:
`0xA5^0x01^0x00 = 0xA4`, `0xA5^0x02^0x00 = 0xA7`, `0xA5^0x03^0x00 = 0xA6`, `0xA5^0x04^0x00 = 0xA1`.

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
| T1 | Serializa el comando a 4 bytes y los entrega al transporte. |
| T2 | Devuelve `True` si se encoló/aceptó; `False` si el transporte está cerrado o desconectado. |
| T3 | **Nunca** lanza excepción por desconexión, timeout o puerto inexistente (FR-034). Cualquier fallo se captura, se registra en `ultimo_error` y se devuelve `False`. |
| T4 | Es idempotente con el mismo comando consecutively a nivel de `ColaTransporte` (no aquí): la deduplicación vive en la cola, no en el transporte. |

### Semántica de `cerrar`

| # | Regla |
|---|------|
| T5 | Cierra el puerto serie y libera el recurso. |
| T6 | Es **idempotente**: llamarla dos veces no falla. |
| T7 | Tras cerrar, `enviar` devuelve `False` sin lanzar. |

### Semántica de `conectado` / `ultimo_error`

| # | Regla |
|---|------|
| T8 | `conectado` es consultable en cualquier momento sin excepción. |
| T9 | `ultimo_error` devuelve `None` si no hay fallo pendiente, o un mensaje legible. |

### Comportamiento de `TransporteSPP` (implementación real)

| Aspecto | Comportamiento |
|---------|----------------|
| Puerto | `params.puerto_serial` (p. ej. `"COM5"`), o `None` ⟹ el transporte queda desconectado pero funcional (devuelve `False`, no lanza) |
| Apertura | `serial.Serial(puerto, baudrate, timeout=params.timeout_serial_s)` en `__init__` o perezosamente en el primer `enviar` |
| Timeout | `timeout_serial_s` (0.2 s por defecto) para que una escritura bloqueada no congele el proceso |
| Fallo de apertura | Puerto inexistente o sin permiso: se captura, se registra, `conectado()` queda `False`, `enviar()` devuelve `False` |
| Reconexión | Tras una desconexión, un `enviar` puede intentar reabrir el puerto (best-effort); si falla, sigue devolviendo `False` sin lanzar |
| `pyserial` | Se importa **solo** en `src/transporte/spp.py` |

**Por qué el timeout importa**: sin él, un módulo BT desconectado puede bloquear el `write` durante
segundos. Con `timeout_serial_s=0.2`, el peor caso acotado es compatible con el presupuesto de
tiempo real, y de todos modos la escritura ocurre **fuera** del bucle de visión (`ColaTransporte`).

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
dirección dura varios fotogramas. Enviar la misma trama 30 veces no aporta nada y consume el enlace.
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
| Puerto no existe | `enviar → False`, `ultimo_error` registrado, bucle sigue | El último comando sigue vigente en el robot (se mantiene hasta nuevo comando) |
| Módulo BT desconectado | Igual que arriba; se intenta reabrir en el siguiente envío | Sin cambio |
| `write` falla a mitad de trama | Trama incompleta; el receptor la descarta por checksum y resincroniza | Sin cambio parcial |
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
| P2 | ¿Se envía alguna trama de "listo" al arrancar? | El robot podría necesitar un heartbeat para no dormir | Equipo + firmware |
| P3 | ¿9600 baudios es suficiente para la respuesta mecánica del robot? | Si el giro es lento, la trama de dirección podría llegar tarde | Docente (cinemática) |
| P4 | ¿Cómo se comporta el robot si recibe `DETENER` repetido? | ¿Idempotente (parar es parar) o re-dispara? | Firmware |

Estas preguntas se registran en `AGENTS.md` §27 (vacíos dependientes del docente) según el Principio VI.

---

## 9. Trazabilidad FR ↔ contrato de transporte

| FR | Sección |
|----|---------|
| FR-028 (SPP/RFCOMM con `pyserial`) | §1, §4 (`TransporteSPP`) |
| FR-029 (declarar en `pyproject.toml`) | §1, `plan.md` |
| FR-030 (interfaz delgada) | §4 (`Transporte` Protocol) |
| FR-031 (no bloqueante) | §5 (`ColaTransporte`), T10, T14 |
| FR-032 (deduplicar) | §5, T11 |
| FR-033 (mock para pruebas) | §6 (`TransporteSimulado`) |
| FR-034 (fallo sin excepción, sin cambiar decisión) | §4 (T3), §7 |
| FR-035 (documentar trama) | §2, §3 |
| FR-024 (DETENER por veto) | §7, y `api-control.md` §3 |
| SC-005 (no bloquea el bucle) | §5, T14 |
| SC-007 (veto siempre DETENER) | §7 |
| SC-008 (pruebas headless del protocolo) | §6 |
