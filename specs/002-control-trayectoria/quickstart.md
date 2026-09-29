# Quickstart: Verificación de la Spec 002

**Feature**: `specs/002-control-trayectoria` | **Fecha**: 2026-09-28

> **Estado: implementación parcial (T001–T026 y T029).** El estimador de posición, el control, el
> compositor, el `Protocol Transporte` y `TransporteSPP` (RFCOMM de un byte) **están escritos**. La
> suite completa está en verde: **382 passed, 5 skipped** (307 unit + 75 integration). Falta la cola
> de transporte (`ColaTransporte`, `TransporteSimulado`) y todo el cableado de métricas/integración
> (T027, T028, T030–T042); los comandos que dependen de esos módulos **hoy no existen** y se marcan
> como *planificados* en cada sección.
>
> **Números reales de esta pasada (2026-09-28):** `tests/unit/test_compositor.py` → 89 passed;
> `tests/unit/test_transporte.py` → 21 passed; `tests/unit/test_configuracion.py` → 65 passed;
> suite completa → 382 passed, 5 skipped; `-m perf` → 14 passed.

## 0. Requisitos previos

```powershell
uv sync                 # instala dependencias (no hay ninguna para el transporte: `socket` es estándar)
uv run pytest -q        # suite completa
```

> **No hay que instalar nada para el canal Bluetooth**: el enlace es un socket RFCOMM de la
> biblioteca estándar, así que no existe una dependencia de terceros que instalar. El destino del
> enlace se configura con `mac_bluetooth` y `timeout_transporte_s` en `config/vision.json`.

**Footage**: los videos de práctica están en `videos/rutaIdeal/` (4) y `videos/desarrilamiento/` (5),
478×850, 2730 fotogramas. **No están versionados** (`.gitignore` ignora `videos/`). Las pruebas que los
usan se marcan con `footage` y **se omiten limpiamente** si el directorio no existe — es el mismo
patrón que ya usa `tests/integration/test_footage_linea.py`.

---

## 1. Verificable hoy: la evidencia que motivó la spec

Los experimentos de `research.md` son de solo lectura y se pueden reproducir sin implementar nada.
Este es el bloque que demuestra que las decisiones de diseño tienen base medida.

```powershell
# Bandas guía y ocupación de la ROI (soporta Decisión 3 y la recalibración de 001)
$env:OPTIPILOT_VIDEO_DIR = "videos"
uv run pytest -m footage -q
```

Si `OPTIPILOT_VIDEO_DIR` no está definido o el directorio no existe, la prueba se omite y pytest
devuelve 0 fallos. **Una omisión no es un éxito**: hay que mirar el número de tests ejecutados, no
solo el de fallos.

---

## 2. Verificación por historia de usuario

### US1 — Posición de la línea (Objetivo 3)

```powershell
uv run pytest tests/unit/test_posicion_linea.py -v
```

| Prueba | Verifica |
|--------|----------|
| Línea centrada produce `error_norm ≈ 0` | FR-004, Q4, Q5 |
| Línea a la derecha produce `error_norm > 0` | FR-004 (signo) |
| Máscara vacía ⟹ `valida=False`, `x_px=None` | FR-006, Q2 |
| Determinismo: dos llamadas, mismo resultado | FR-008, Q6 |
| Error contra `x_objetivo` **configurable**, no el centro fijo | FR-005 |
| Detecta los 3 casos de ambigüedad (dos bandas, borde, ruido) | FR-007 |

**Criterio de aceptación**: todas pasan, y `test_posicion_linea.py::test_sin_hough` verifica por
inspección del código que `posicion_linea.py` no importa `HoughLinesP` ni `fitLine` (FR-003).

### US2 — Control de trayectoria (Objetivo 4)

```powershell
uv run pytest tests/unit/test_control_trayectoria.py -v
```

| Prueba | Verifica |
|--------|----------|
| Error dentro de zona muerta ⟹ `AVANZAR` | FR-012 |
| Error > umbral ⟹ lado correcto | FR-012, FR-014 |
| Cruce del umbral por ruido **no** alterna comando | FR-012 (histéresis) |
| Error sostenido ⟹ comando sostenido, no alternancia | FR-015 |
| `DETENER` ante cualquier estado inconsistente | FR-025, Q8 |

**Criterio de aceptación**: la prueba de histéresis inyecta 50 fotogramas de error alternando entre
`0.09` y `0.11` (dentro de la banda con zona muerta 0.10 e histéresis 0.03) y verifica que el
comando **no cambia nunca**. Sin histéresis, ese test falla.

### US3 — Recuperación de línea perdida

```powershell
uv run pytest tests/unit/test_control_trayectoria.py -k recuperacion -v
```

| Prueba | Verifica |
|--------|----------|
| Pérdida de N fotogramas ⟹ busca hacia el último lado | FR-019 |
| Pérdida en el N+1 ⟹ `DETENER` + causa `GRACIA_AGOTADA` | FR-020 |
| Recuperación dentro de la ventana ⟹ mando normal | FR-021 |
| Sin memoria previa ⟹ `DETENER` inmediato | FR-022 |
| Reaparición en lado opuesto ⟹ invierte en el siguiente fotograma | FR-021 |

### US4 — Transporte Bluetooth

```powershell
uv run pytest tests/unit/test_transporte.py -v
```

> `tests/unit/test_cola_transporte.py` (T027) **todavía no existe**: la cola de transporte está
> planificada, no implementada. Las filas de la tabla marcadas con *(planificado)* no son ejecutables
> hoy.

| Prueba | Verifica |
|--------|----------|
| Los 4 comandos viajan como **un byte ASCII** según `mapa-comandos.md` §1 (`w`, `a`, `d`, `x`) | FR-035 |
| El protocolo envía exactamente 1 byte por comando, sin sufijo | FR-035 |
| `enviar` nunca lanza con una MAC inalcanzable | FR-034 |
| `enviar` no lanza en una plataforma sin `AF_BLUETOOTH` | FR-034 |
| La MAC es configurable y la conexión va al canal RFCOMM 1 | FR-028 |
| El timeout del socket se acota a `timeout_transporte_s` | FR-031 |
| La conexión es perezosa: se abre en el primer `enviar`, no en el constructor | `api-control.md` §5 (R1, R2) |
| `ColaTransporte` deduplica comandos idénticos | FR-032 *(planificado, T027)* |
| Fallo de envío deja el comando pendiente | FR-034, T13 *(planificado, T027)* |
| `cerrar` es idempotente | T6 |

**Ninguna prueba requiere hardware**: `TransporteSPP` recibe una **fábrica de sockets inyectable**, de
modo que la suite ejercita la ruta completa de envío y de fallo contra un doble. Para probar el enlace
real no existe todavía una prueba dedicada (no hay `test_transporte_enlace_real.py`); cuando la haya,
deberá tomar la MAC de `config/vision.json` (`mac_bluetooth`) y usar el canal 1 (SPP estándar), y
marcarse `footage` para omitirse sin el robot conectado. El supuesto de que se envía un byte sin salto
de línea solo se puede confirmar ahí o en pista (P3/P5).

---

## 3. Verificación de integración

> **Planificado (T033, T035, T036): todavía no ejecutable.** `tests/integration/test_control_fotogramas.py`
> no existe; el compositor se verifica hoy solo a nivel unitario (`tests/unit/test_compositor.py`, 89
> pruebas). El bucle completo `segmento → estima → decide → compone → encola` requiere además el
> cableado en `pipeline.py`/`main.py` y la cola de transporte, aún pendientes.

```powershell
uv run pytest tests/integration/test_control_fotogramas.py -v
```

Recorre el bucle completo con fotogramas sintéticos: segmento → estima → decide → compone →
encola. Verifica la precedencia de seguridad (§3 de `api-control.md`):

- Con `DecisionMovimiento(NO_AUTORIZADO)`, el comando final es `DETENER` en el **100 %** de los
  fotogramas (SC-007).
- `DecisionMovimiento` de 001 no cambia de comportamiento (FR-026).
- La cola recibe el comando final, no el propuesto por el control.

---

## 4. Verificación contra footage real

> **Planificado (T038–T041): todavía no ejecutable.** `tests/integration/test_footage_control.py` no
> existe. La recalibración de `roi_linea` de 001 sí se midió sobre footage (ver `research.md`), pero
> la verificación del control contra los 9 videos es trabajo futuro.

```powershell
$env:OPTIPILOT_VIDEO_DIR = "videos"

# Tasa de correcciones en ruta ideal (SC-001: <= 3 por corrida)
uv run pytest tests/integration/test_footage_control.py -m footage -v -k ruta_ideal

# Recuperación en desarrilamiento (SC-002)
uv run pytest tests/integration/test_footage_control.py -m footage -k desarrilamiento
```

| Métrica esperada | Fuente |
|------------------|--------|
| Correcciones por corrida en `rutaIdeal` | `MetricasControl.correcciones` |
| `recuperaciones_ok` > 0 sin `recuperaciones_fallidas` | `MetricasControl` |
| Velocidad de error: ~15–20 px (ideal) vs ~52 px (desarrilamiento) | `velocidad_error_px` |
| Nunca `CORRECCION_*` cuando `pos.valida == False` | SC-003 |

**Expectativas honestas** (deben concordar con `research.md`):

- La **tasa de correcciones** medida con cámara en mano **no** predice la del robot montado. SC-001
  es un criterio de pista, no de video. La prueba de footage verifica *estabilidad y no-alternancia*,
  no el número final de correcciones.
- La **recuperación** sí es verificable: la estructura de la memoria con timeout no depende del
  montaje.

---

## 5. Rendimiento

```powershell
uv run pytest -m perf -q
```

| Presupuesto | Objetivo | Referencia actual (001) |
|-------------|----------|--------------------------|
| Por fotograma completo (≤ 33 ms a 30 fps) | SC-005 | p95 3.88 ms sobre footage |
| Estimador de posición | < 1 ms | — (nuevo) |
| Control + compositor | < 0.1 ms | — (nuevo) |
| `encolar` (sin I/O) | O(1), < 0.01 ms | — (nuevo) |

El p95 actual de 001 es 3.88 ms, así que el presupuesto de 33 ms deja margen amplio para las etapas
nuevas. **El transporte no se mide aquí**: no está en el bucle de visión (SC-005 se verifica en
`test_cola_transporte.py` comprobando que el bucle nunca llama a `drenar`).

---

## 6. Evidencia visual (póster)

```powershell
uv run python -m src.main --fuente videos/rutaIdeal/video3.mp4 --diagnostico
```

Genera en `salidas/` un fotograma por etapa con la evidencia de US1–US4 described en
`mapa-comandos.md` §6: posición estimada, objetivo, zona muerta, banda de histéresis, comando emitido
y su causa. Con esto se construye la figura del póster para los criterios 10 y 11.

```powershell
# Correr el CLI sin hardware: el transporte por defecto es el simulado
uv run python -m src.main --fuente videos/rutaIdeal/video3.mp4 --salida salidas/demo
```

---

## 7. Checklist de salida a pista

Antes de la demostración, los puntos que **el software no puede validar** y que deben comprobarse en
la pista física (de `mapa-comandos.md` §5):

- [ ] **R1 — convención de giro**: con la línea desplazada a la derecha, ¿`DERECHA` produce un giro a
      la derecha real? Si no, invertir el mapeo (es un parámetro, no un rediseño).
- [ ] **R2 — `x_objetivo`**: con la línea centrada, ¿el comando se estabiliza en `AVANZAR`? Si
      oscila, recalibrar `x_objetivo`.
- [ ] **R3 — zona muerta**: ¿la tasa de correcciones real cumple SC-001 (≤ 3 por corrida)?
- [ ] **R4 — `n_gracia_busqueda`**: ante una pérdida controlada, ¿recupera antes de descarrilar?
- [ ] **P1–P5** (de `transporte-bluetooth.md` §8): comportamiento del receptor, heartbeat,
      confirmaciones del docente, si el receptor espera un delimitador de línea, idempotencia de
      `DETENER`, y la **MAC real del mBot de pista** (`mac_bluetooth` en `config/vision.json` es hoy
      una suposición de trabajo).

**Ninguna de estas casillas se puede marcar desde el repositorio.** Marcar checkbox
específicos de cada una requiere estar físicamente en la pista.
