# Quickstart: Verificación de la Spec 002

**Feature**: `specs/002-control-trayectoria` | **Fecha**: 2026-09-28

> **Estado: la implementación aún no existe.** Este documento describe cómo se verificará cuando se
> implemente. Los comandos marcados como *esperados* fallan hoy porque los módulos no están escritos.
> La sección 1 sí es ejecutable ahora.

## 0. Requisitos previos

```powershell
uv sync                 # instala dependencias (incluye pyserial tras el cambio)
uv run pytest -q        # suite completa: 167 passed, 5 skipped (estado actual de 001)
```

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
uv run pytest tests/unit/test_transporte.py tests/unit/test_cola_transporte.py -v
```

| Prueba | Verifica |
|--------|----------|
| Los 4 comandos serializan a las tramas de `mapa-comandos.md` §1 | FR-035 |
| Checksum XOR correcto en las 4 tramas | FR-035 |
| `enviar` nunca lanza con puerto inexistente | FR-034 |
| `ColaTransporte` deduplica comandos idénticos | FR-032 |
| Fallo de envío deja el comando pendiente | FR-034, T13 |
| Reconexión reanuda sin duplicar | FR-008 del contrato |
| `cerrar` es idempotente | T6 |

**Ninguna prueba requiere hardware**: todas usan `TransporteSimulado`. Para probar el SPP real:

```powershell
# Solo con un módulo BT conectado; no es parte de la suite
$env:OPTIPILOT_PUERTO = "COM5"
uv run pytest tests/unit/test_transporte_spp_real.py -v --manual
```

Esa prueba está **marcada `footage`** y se omite sin la variable.

---

## 3. Verificación de integración

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
- [ ] **P1–P4** (de `transporte-bluetooth.md` §8): comportamiento del receptor, heartbeat,
      baudrate suficiente, idempotencia de `DETENER`.

**Ninguna de estas casillas se puede marcar desde el repositorio.** Marcar checkbox
específicos de cada una requiere estar físicamente en la pista.
