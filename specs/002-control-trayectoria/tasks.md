---
description: "Task list template for feature implementation"
---

# Tasks: Cálculo de Posición de Línea y Control de Trayectoria

**Input**: Documentos de diseño en `/specs/002-control-trayectoria/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Sí, incluidos. El Principio V de la Constitución exige que *toda lógica determinista
(«cálculo de posición, control y transiciones») MUST poder probarse sin hardware* — las pruebas no
son opcionales en este cambio.

**Organization**: Tareas agrupadas por historia de usuario, para permitir implementación y prueba
independientes. Cada historia tiene su propio checkpoint.

**Input del equipo (decisiones tomadas 2026-09-28)**: Bluetooth Classic SPP con `pyserial`; Spec Kit
en vez de OpenSpec; `t_parada_s` intacto; transporte en `src/transporte/`; recuperación por memoria
del último lado con `n_gracia_busqueda`; `x_objetivo` configurable; riesgo de convención de giro
declarado.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ejecutarse en paralelo (archivos distintos, sin dependencias)
- **[Story]**: US1–US4, o `FOUND` para infraestructura compartida

---

## Phase 1: Setup

- [X] T001 Crear `src/transporte/` con `__init__.py` (paquete nuevo, fuera de `src/vision/`)
- [X] T002 Declarar `pyserial` en `dependencies` de `pyproject.toml` y ejecutar `uv sync` para
      actualizar `uv.lock` (Principio III: declarar antes de importar)
- [X] T003 [P] Verificar que la suite de 001 sigue verde antes de tocar nada:
      `uv run pytest -q` (baseline: 167 passed, 5 skipped)

**Checkpoint**: entorno reproducible y línea base registrada. Si T003 falla, el problema es previo a
este cambio.

---

## Phase 2: Foundational (bloquea todas las historias)

**⚠️ CRITICAL**: ninguna historia puede empezar antes de que esta fase esté completa, porque las
cuatro dependen de las entidades y los parámetros nuevos.

- [X] T004 [FOUND] Añadir a `src/vision/modelos.py`: `ComandoMovimiento` (StrEnum de 4 valores),
      `Lado` (IZQUIERDA/DERECHA), `CausaComando` (8 valores, data-model §6) y `PosicionLinea`
      (frozen, con las invariantes de data-model §2) — **sin modificar** las entidades existentes
- [X] T005 [FOUND] Añadir a `modelos.py`: `LadoConocido` (frozen), `DecisionControl` (frozen) y
      `DecisionCompuesta` (frozen, con la invariante `VETO_FSM ⟹ DETENER`)
- [X] T006 [FOUND] Añadir a `src/vision/configuracion.py` los 10 parámetros de control con sus
      defaults (`x_objetivo` 0.5, `frac_anticipacion` 0.40, `frac_pico` 0.50,
      `umbral_confianza` 0.35, `zona_muerta` 0.10, `histeresis` 0.03, `n_gracia_busqueda` 5,
      `puerto_serial` null, `baudrate` 9600, `timeout_serial_s` 0.20) leyendo de
      `config/vision.json` (no un archivo nuevo — ver contrato §1)
- [X] T007 [FOUND] Implementar en `configuracion.py` las 6 reglas de validación cruzada V1–V6
      (contracts/esquema-configuracion.md §4), lanzando `ConfiguracionInvalidaError(campo, motivo)`
- [X] T008 [FOUND] [P] Escribir `tests/unit/test_configuracion.py` para los 10 parámetros: rango
      válido, default, y cada regla V1–V6 rechazando con el campo correcto
- [X] T009 [FOUND] Crear `src/transporte/base.py` con el `Protocol Transporte` (sin I/O:
      `enviar`/`cerrar`/`conectado`/`ultimo_error`)

**Checkpoint**: entidades, parámetros y validación disponibles. Las 4 historias ya pueden empezar.

---

## Phase 3: User Story 1 — Posición de la línea (Priority: P1) 🎯 MVP

**Objetivo del Reto 1: calcular la posición de la línea respecto al centro.**

**Goal**: estimar la posición lateral de la guía por fotograma mediante el centroide del pico de la
proyección de columnas, con error contra un `x_objetivo` configurable y un indicador de confianza.

**Independent Test**: `uv run pytest tests/unit/test_posicion_linea.py -v` — se verifica con máscaras
sintéticas, sin cámara ni robot.

### Tests for User Story 1 ⚠️ (escribir primero, deben fallar)

- [X] T010 [P] [US1] Tests unitarios de `EstimadorLinea` en
      `tests/unit/test_posicion_linea.py`: línea centrada / desplazada a ambos lados; máscara vacía
      ⟹ `valida=False`; determinismo (dos llamadas, mismo resultado); `error_norm` contra
      `x_objetivo` configurable; error calculado contra el objetivo y **no** contra el centro fijo
- [X] T011 [P] [US1] Tests de los tres casos de pérdida de confianza en el mismo archivo: dos bandas
      de masa comparable (ambigüedad), pico en el borde de la ROI, y ruido con pico débil —
      todos deben dar `valida=False` o confianza baja
- [X] T012 [P] [US1] Test de cumplimiento normativo en `test_posicion_linea.py`: leer el código de
      `src/vision/posicion_linea.py` y fallar si aparece `HoughLinesP`, `fitLine` o `HoughLines`
      (FR-003, Principio I y §III)

### Implementation for User Story 1

- [X] T013 [US1] Crear `src/vision/posicion_linea.py` con `EstimadorLinea.aplicar(seg)`:
      recortar la banda de lectura con `frac_anticipacion`, sumar la máscara por columna, localizar
      `argmax`, definir el soporte con `frac_pico` y calcular la media ponderada → `x_px`, `x_norm`,
      `error_norm`, `ancho_banda_px`, `confianza`, `valida`
- [X] T014 [US1] Implementar `confianza`: dominancia del pico (masa total vs. pico × nº de columnas),
      penalización por ambigüedad y por proximidad al borde; `valida = confianza >= umbral_confianza`
      **y** pico no pegado al borde (postcondiciones Q1–Q7 del contrato)
- [X] T015 [US1] Verificar el determinismo (FR-008) y que no hay bucles por píxel: la implementación
      debe vectorizarse con NumPy para cumplir el presupuesto de 33 ms (FR-010)

**Checkpoint**: US1 verificable por sí sola. Ya cierra el primer consumidor de `mascara_linea`
(contribución parcial a CHK035).

---

## Phase 4: User Story 2 — Control de trayectoria (Priority: P1)

**Objetivo del Reto 1: generar acciones de control para corregir la trayectoria.**

**Goal**: convertir `PosicionLinea` en uno de los cuatro comandos con zona muerta, histéresis y
memoria del último lado, sin oscilar.

**Independent Test**: `uv run pytest tests/unit/test_control_trayectoria.py -v` — se verifica
inyectando secuencias sintéticas de `error_norm`, sin cámara.

### Tests for User Story 2 ⚠️ (escribir primero)

- [X] T016 [P] [US2] Tests de la tabla de decisión en `tests/unit/test_control_trayectoria.py`:
      |error| dentro de zona muerta ⟹ `AVANZAR`; error fuera ⟹ lado correcto según el signo;
      borde de la zona muerta con pertenencia inclusiva por dentro / exclusiva por fuera
- [X] T017 [P] [US2] Test de **histéresis**: 50 fotogramas con error alternando entre 0.09 y 0.11
      (banda entre `zona_muerta − h` y `zona_muerta + h`) deben producir **cero** cambios de
      comando. Este test es el que falla si se implementa sin histéresis
- [X] T018 [P] [US2] Test de **sostenimiento**: error grande y constante durante N fotogramas ⟹ un
      único comando de corrección, sin alternancia entre lados (FR-015)
- [X] T019 [P] [US2] Test de **fallo seguro**: `decidir` nunca devuelve `None` y nunca propaga
      excepción; un estado inconsistente ⟹ `DETENER` con causa `FALLO_SEGURO` (FR-025, Q8/Q9)
- [X] T020 [P] [US2] Tests de **recuperación** (US3, mismo módulo): pérdida de N fotogramas ⟹ busca
      hacia el último lado con causa `RECUPERACION` en los N; pérdida en el N+1 ⟹ `DETENER` con
      `GRACIA_AGOTADA`; reaparición ⟹ mando normal y memoria actualizada; sin memoria previa ⟹
      `DETENER` inmediato; reaparición en lado opuesto ⟹ invierte en el siguiente fotograma

### Implementation for User Story 2

- [X] T021 [US2] Crear `src/vision/control_trayectoria.py` con `ControlTrayectoria.decidir(pos)`:
      implementar los dos umbrales de la histéresis (salida a corrección si
      `|e| >= zona_muerta + histeresis`; retorno a `AVANZAR` si `|e| <= zona_muerta − histeresis`;
      en la banda intermedia, mantener el comando anterior) — técnica autorizada: comparación de
      umbral con histéresis
- [X] T022 [US2] Implementar la memoria del último lado en `ControlTrayectoria`: actualizar `LadoConocido`
      en cada fotograma válido (reiniciando `fotogramas_perdidos`), incrementarlo en cada fotograma
      inválido sin descartar la memoria, y vaciarla en `reiniciar()` (FR-018–FR-023, Q10/Q11/Q13)
- [X] T023 [US2] Implementar `reiniciar()` para que la memoria no sobreviva entre corridas (FR-023)

**Checkpoint**: US2 y US3 verificables juntas (comparten módulo). El control ya produce comandos
correctos sobre secuencias sintéticas.

---

## Phase 5: User Story 3 — Composición y precedencia de seguridad (transversal, P1)

> US3 en la spec es «Recuperación de línea perdida», implementada en T020/T022 dentro de US2 porque
> comparte módulo. **Esta fase es el compositor**, que la spec exige como punto de arbitraje y que
> no se había asignado a ninguna historia: sin él, un PARE puede ser pisado por una corrección.

- [ ] T024 [P] [US2] Tests del compositor en `tests/unit/test_compositor.py`: con
      `DecisionMovimiento(NO_AUTORIZADO)` el comando final es `DETENER` en el 100 % de los casos
      (SC-007); con `AUTORIZADO` el comando final es el propuesto por el control; la causa del veto
      es `VETO_FSM`; `DecisionMovimiento` de 001 no cambia (FR-026)
- [ ] T025 [US2] Crear `src/vision/compositor.py` con la precedencia de tres niveles de
      `api-control.md` §3: (1) veto por FSM ⟹ `DETENER`; (2) el control propone `DETENER` ⟹
      `DETENER`; (3) en otro caso ⟹ el comando propuesto. Registrar siempre la causa (FR-027)

**Checkpoint**: la composición es segura por construcción. Un PARE confirmado produce `DETENER`
independientemente de lo que proponga el control.

---

## Phase 6: User Story 4 — Transporte Bluetooth Classic SPP (Priority: P2)

- [ ] T026 [P] [US4] Tests del protocolo en `tests/unit/test_transporte.py`: los 4 comandos
      serializan exactamente a las tramas de `mapa-comandos.md` §1 (`A5 01 00 A4`, `A5 02 00 A7`,
      `A5 03 00 A6`, `A5 04 00 A1`); checksum XOR correcto; `enviar` no lanza con puerto inexistente;
      `cerrar` es idempotente; `conectado` y `ultimo_error` consultables sin excepción
- [ ] T027 [P] [US4] Tests de `ColaTransporte` en `tests/unit/test_cola_transporte.py`: `encolar`
      deduplica comandos idénticos consecutivos; FIFO en `drenar`; un fallo de envío deja el comando
      pendiente y registra `ultimo_error`; la reconexión reanuda sin duplicar; `pendientes()` refleja
      el backlog
- [ ] T028 [US4] Crear `src/transporte/simulado.py` con `TransporteSimulado`: registra el historial,
      permite inyectar fallos (`fallar_con(n)`) para probar reconexión (T18 del contrato)
- [ ] T029 [US4] Crear `src/transporte/spp.py` con `TransporteSPP` — **el único archivo del proyecto
      que importa `serial`** — con `timeout_serial_s` acotado, captura de fallos de apertura,
      `cerrar` idempotente y reintento best-effort de reapertura
- [ ] T030 [US4] Crear `src/transporte/cola.py` con `ColaTransporte`: `encolar` O(1) sin I/O
      (FR-031), deduplicación (FR-032), `drenar` FIFO con reintento de pendientes, y la garantía de
      que el bucle de visión **nunca** la invoca
- [ ] T031 [US4] Test de no-bloqueo: verificar que el bucle de visión invoca `encolar` y **no**
      `drenar` en ningún camino de código (SC-005, T14 del contrato)

**Checkpoint**: US4 verificable por completo sin hardware. El canal hacia el robot existe y es
auditable.

---

## Phase 7: Integración en el pipeline y métricas

- [ ] T032 [P] [US1] Añadir `MetricasControl` a `src/vision/metricas.py`: `correcciones`
      (transiciones `AVANZAR ↔ lado`, proxy de SC-001), fotogramas por comando, `perdidas_linea`,
      `recuperaciones_ok`, `recuperaciones_fallidas`, `velocidad_error_px` y `latencia_decision_ms`
      — **sin modificar** `MetricasCorrida` de 001
- [ ] T033 [US1] Integrar en `src/vision/pipeline.py`: estimador → control → compositor, y exponer
      la `DecisionCompuesta` por fotograma sin alterar la firma pública existente
- [ ] T034 [US1] Extender `src/vision/visualizacion.py` con la evidencia de `mapa-comandos.md` §6:
      posición estimada, objetivo, zona muerta, banda de histéresis, comando y causa, indicador de
      memoria de lado y gráfico de velocidad de error (FR-037, SC-009)
- [ ] T035 [US4] Cablear en `src/main.py`: construir `ColaTransporte` e inyectar el transporte
      según un flag `--transporte {simulado,spp}`; **`simulado` es el default** para que el CLI
      funcione sin hardware (reutilizando la máscara vacía como transporte por defecto)
- [ ] T036 [P] [US1] Tests de integración en `tests/integration/test_control_fotogramas.py`:
      recorrido completo segmento → estima → decide → compone → encola, con verificación de la
      precedencia de seguridad sobre una secuencia completa
- [ ] T037 [P] [US1] Ampliar `tests/fixtures/generador_sintetico.py`: línea desplazada
      paramétricamente, línea con hueco (para US3) y línea en el borde de la ROI (para pérdida de
      confianza)

**Checkpoint**: pipeline completo con las tres etapas nuevas operativas.

---

## Phase 8: Validación con footage real (Principio V: antes de integrar)

- [ ] T038 [US1] Crear `tests/integration/test_footage_control.py` marcado `footage`: reproduccir
      `videos/rutaIdeal/` y `videos/desarrilamiento/` y registrar `MetricasControl`. Debe omitirse
      limpiamente sin `OPTIPILOT_VIDEO_DIR` (mismo patrón que `test_footage_linea.py`)
- [ ] T039 [US1] Verificar la **estabilidad** del estimador contra footage: correlación ≥ 0.7 entre
      dos estimadores independientes (SC-006, dato de referencia: +0.76/+0.86 medido el 2026-09-28)
- [ ] T040 [US1] Verificar que la velocidad de error discrimina los dos corpus: ~15–20 px en
      `rutaIdeal` frente a ~52 px en `desarrilamiento`
- [ ] T041 [US2] Verificar sobre footage que **nunca** se emite `CORRECCION_*` cuando
      `pos.valida == False` (SC-003)
- [ ] T042 [US1] Extender `tests/integration/test_rendimiento.py` (marcador `perf`): estimador < 1 ms,
      control + compositor < 0.1 ms, `encolar` O(1); pipeline completo ≤ 33 ms (SC-005)

**Nota de honestidad**: SC-001 (≤ 3 correcciones) es un criterio de **pista**. Los videos de práctica
están grabados con cámara en mano y **no predicen** la tasa de correcciones del robot montado. Las
pruebas de footage verifican estructura y estabilidad, no el número final. Registrar los resultados
reales sin embellecerlos (Principio V).

---

## Phase 9: Documentación y cierre (Principio VI)

- [ ] T043 [P] Actualizar `AGENTS.md`: estado real del cambio (nuevo paquete `src/transporte/`,
      módulos nuevos, `pyserial` en dependencias, comandos verificados), y §27 con los vacíos
      abiertos: convención de giro pendiente de pista, `x_objetivo`/`zona_muerta` provisionales,
      y las 4 preguntas P1–P4 del receptor Bluetooth
- [ ] T044 [P] Marcar **CHK035 como cerrada** en `specs/001-cv-sign-detection/checklists/plan-tecnico.md`
      con referencia a `specs/002-control-trayectoria/`
- [ ] T045 [P] Registrar en `AGENTS.md` §27 la inconsistencia detectada: `data-model.md` de 001
      documenta `roi_linea.y = 0.55`, obsoleto desde la recalibración a `0.10` (commit `7f0990c`).
      **No** editar 001 en este cambio: registrar el conflicto, como exige el Principio VI
- [ ] T046 Ejecutar la verificación completa de `quickstart.md` §2–§5 y registrar los números
      reales obtenidos en este cambio (sin dejar placeholders)
- [ ] T047 [P] Revisar cumplimiento constitucional: confirmar que `import serial` aparece
      **únicamente** en `src/transporte/spp.py`, y que no hay Hough ni `fitLine` en ningún módulo

**Checkpoint**: el cambio está completo, documentado y auditable contra la Constitución.

---

## Dependencias y orden de ejecución

### Dependencias por fase

| Fase | Depende de | Bloquea |
|------|-----------|---------|
| 1 Setup | — | 2 |
| 2 Foundational | 1 | **3, 4, 5, 6** (todas) |
| 3 US1 (posición) | 2 | 7 |
| 4 US2 (control + US3 recuperación) | 2 | 5, 7 |
| 5 Compositor | 4 | 7 |
| 6 US4 (transporte) | 2 (T009) | 7 |
| 7 Integración | 3, 5, 6 | 8 |
| 8 Footage + perf | 7 | 9 |
| 9 Documentación | 7 | — |

### Dependencias entre historias

- **US1** (posición): sin dependencias. Entregable por sí sola.
- **US2** (control): sin dependencias de US1 en el código — recibe `PosicionLinea` como dato, así que
  se puede probar con objetos construidos a mano.
- **US3** (recuperación): implementada dentro de US2 (T020/T022) porque comparte módulo; se verifica
  como historia propia.
- **US4** (transporte): independiente de US1–US3; solo necesita el `Protocol` de T009.
- **Compositor (Phase 5)**: necesita US2 (control) para consumir su propuesta.

### Oportunidades de paralelismo

- T008, T010–T012, T016–T020, T024, T026–T027: **todas las pruebas**, en paralelo (archivos
  distintos).
- T026–T027 y T028–T030: transporte, en paralelo con US1/US2 (no comparten archivos).
- T032, T037: en paralelo con el resto de Phase 7.
- T043–T045, T047: documentación, al final y en paralelo entre sí.

### Dentro de cada historia

- **Las pruebas se escriben PRIMERO y deben fallar** antes de implementar (Principio V).
- T004–T005 (modelos) antes que T013, T021, T025 (lógica).
- T006–T007 (configuración) antes que T013 (el estimador lee parámetros).
- T028 (simulado) antes que T026–T027 pasan: el simulador es el doble de prueba.

---

## Estrategia de implementación

### MVP (User Story 1 solamente)

1. Phase 1 + Phase 2 (setup y fundacionales)
2. Phase 3 (US1: posición de línea)
3. **PARAR y VALIDAR**: `uv run pytest tests/unit/test_posicion_linea.py -v`
4. Entregable: el estimador por sí solo ya consume `mascara_linea` y es el primer cierre parcial de
   CHK035. Es demostrable en video con `visualizacion.py`.

### Entrega incremental

1. Setup + Foundational ⟶ base lista
2. US1 (posición) ⟶ probar sola ⟶ *el error de posición es observable*
3. US2 + US3 (control y recuperación) ⟶ probar ⟶ *los comandos se pueden contar sobre footage*
4. Compositor ⟶ probar ⟶ *la precedencia de seguridad es demostrable*
5. US4 (transporte) ⟶ probar ⟶ *el canal existe y es auditable*
6. Integración + métricas ⟶ *la evidencia del póster es generable*
7. Footage + rendimiento ⟶ *SC medibles*
8. Documentación ⟶ *trazabilidad completa*

### Orden mínimo para una demo funcional

Fases 1 → 2 → 3 → 4 → 5 → 7 parcial (T033, T035). US4 puede posponerse: el robot puede recibir
comandos por otro medio en una primera demostración, siempre que la precedencia de seguridad del
compositor esté en su lugar (Phase 5, que es P1).

---

## Notas

- **[P]** = tareas paralelizables.
- **[USn]** = historia para trazabilidad; `FOUND` = infraestructura compartida.
- **Riesgo abierto principal** (R1, convención de giro): no se puede cerrar en software. La ley de
  control se escribió simétrica al signo del error para que corregirlo sea cambiar un parámetro
  (`x_objetivo`) o invertir el mapeo en el compositor, nunca reescribir el control.
- **No tocar** `src/vision/maquina_estados.py` ni la semántica de `DecisionMovimiento`: 167 pruebas
  dependen de ese contrato (FR-026).
- **No tocar** `t_parada_s` (decisión del equipo, fuera de alcance).
- Registrar resultados **reales**, incluidos los que no alcancen el objetivo (Principio V: *«MUST NOT
  documentarse como implementado nada que no exista ni maquillarse resultados»*).
