# Checklist de Plan Técnico: Cálculo de Posición de Línea y Control de Trayectoria

**Feature**: `specs/002-control-trayectoria` | **Fecha**: 2026-09-28 | **Spec**: [spec.md](./spec.md)

Trazabilidad de cada requisito y criterio de éxito hacia su artefacto de diseño, su tarea de
implementación y su evidencia de verificación. Marca el estado de la **especificación** (no de la
implementación, que aún no existe).

Leyenda: ✅ artifact existe y trazable · ⬜ pendiente de implementar

---

## A. Requisitos funcionales

| FR | Descripción | Artefacto | Tarea | Verificación | Estado |
|----|-------------|-----------|-------|--------------|--------|
| FR-001 | Posición lateral desde la máscara, sin reprocesar | `api-control.md` §1 | T013 | `test_posicion_linea.py` | ⬜ |
| FR-002 | Solo aritmética/lógica autorizada | `research.md` Dec. 1 | T013 | T012 (test de Hough) | ⬜ |
| FR-003 | Prohibido Hough / `fitLine` / auto-detección | `research.md` Dec. 1 | T012 | T012 + T047 | ⬜ |
| FR-004 | `x_px`, `x_norm`, `error_norm` vs objetivo configurable | `data-model.md` §2 | T013 | T010 | ⬜ |
| FR-005 | `x_objetivo` validado en [0,1] | `esquema-configuracion.md` §3.1 | T006, T007 | T008 | ⬜ |
| FR-006 | `valida` / `confianza` sin inventar posición | `api-control.md` Q2 | T014 | T010, T011 | ⬜ |
| FR-007 | Confianza penaliza ambigüedad y borde | `research.md` Dec. 1 | T014 | T011 | ⬜ |
| FR-008 | Determinismo sin azar | `api-control.md` Q6 | T015 | T010 | ⬜ |
| FR-009 | Pérdida temporal sin excepción, con último lado | `api-control.md` Q1 | T013, T022 | T020 | ⬜ |
| FR-010 | Dentro de 33 ms, vectorizado | `plan.md` Performance | T015, T042 | `-m perf` | ⬜ |
| FR-011 | Exactamente 4 comandos | `mapa-comandos.md` §1 | T004, T021 | T016, T026 | ⬜ |
| FR-012 | Zona muerta + histéresis | `api-control.md` §2 | T021 | T016, T017 | ⬜ |
| FR-013 | Umbrales configurables, no mágicos | `esquema-configuracion.md` §3.1 | T006 | T008 | ⬜ |
| FR-014 | Signo mapeado al lado de la línea | `mapa-comandos.md` §1 | T021 | T016 | ⬜ |
| FR-015 | Estable ante ruido, sin alternancia | `api-control.md` Q15 | T021 | T018 | ⬜ |
| FR-016 | Sin heurísticas ajenas al error | `api-control.md` §2 | T021 | T016 | ⬜ |
| FR-017 | Tasa de corrección registrada | `data-model.md` §10 | T032 | T038 | ⬜ |
| FR-018 | Memoria del último lado | `data-model.md` §3 | T022 | T020 | ⬜ |
| FR-019 | Búsqueda durante N fotogramas | `research.md` Dec. 4 | T022 | T020 | ⬜ |
| FR-020 | `DETENER` al agotar la gracia | `mapa-comandos.md` §2 | T022 | T020 | ⬜ |
| FR-021 | Recuperación restaura el mando | `mapa-comandos.md` Escen. B | T022 | T020 | ⬜ |
| FR-022 | Sin memoria ⟹ `DETENER` inmediato | `mapa-comandos.md` Escen. E | T022 | T020 | ⬜ |
| FR-023 | Memoria se vacía al arrancar | `api-control.md` Q13 | T023 | T020 | ⬜ |
| FR-024 | FSM veta ⟹ `DETENER` | `api-control.md` §3 | T025 | T024, T036 | ⬜ |
| FR-025 | `DETENER` es el fallo seguro por defecto | `api-control.md` Q8 | T021 | T019 | ⬜ |
| FR-026 | `DecisionMovimiento` sin modificar | `research.md` Dec. 5 | T025 | T024 + suite 001 | ⬜ |
| FR-027 | Causa registrada en cada comando | `data-model.md` §6 | T025 | T024 | ⬜ |
| FR-028 | Bluetooth Classic SPP por socket RFCOMM de la estándar, canal 1 | `transporte-bluetooth.md` §1, §4 | T029 | T026 | ⬜ |
| FR-029 | Sin dependencia de terceros para el transporte | `plan.md` Impacto; `research.md` Dec. 7 | T002 | T047 | ⬜ |
| FR-030 | Interfaz de transporte delgada | `transporte-bluetooth.md` §4 | T009 | T026 | ⬜ |
| FR-031 | Envío no bloqueante | `transporte-bluetooth.md` §5 | T030, T031 | T031 | ⬜ |
| FR-032 | Deduplicación de comandos idénticos | `transporte-bluetooth.md` T11 | T030 | T027 | ⬜ |
| FR-033 | Simulador para pruebas headless | `transporte-bluetooth.md` §6 | T028 | T026, T027 | ⬜ |
| FR-034 | Fallo sin excepción ni cambio de decisión | `transporte-bluetooth.md` §7 | T029 | T026, T027 | ⬜ |
| FR-035 | Byte único y tabla de bytes documentados | `mapa-comandos.md` §1; `transporte-bluetooth.md` §2, §3 | T029 | T026 | ⬜ |
| FR-036 | Métricas por corrida | `data-model.md` §10 | T032 | T038 | ⬜ |
| FR-037 | Evidencia visual por comando | `mapa-comandos.md` §6 | T034 | `quickstart.md` §6 | ⬜ |
| FR-038 | Parámetros centralizados y documentados | `esquema-configuracion.md` §1 | T006 | T008 | ⬜ |

## B. Criterios de éxito

| SC | Descripción | Tarea | Cómo se verifica | Honestidad del criterio |
|----|-------------|-------|------------------|-------------------------|
| SC-001 | ≤ 3 correcciones por corrida en `rutaIdeal` | T038 | `MetricasControl.correcciones` | ⚠️ **Criterio de pista.** Los videos son de cámara en mano y no predicen la tasa real. La prueba verifica estructura, no el número. Declarado en `quickstart.md` §4 |
| SC-002 | Recuperación en `desarrilamiento` sin `DETENER` | T038 | `recuperaciones_ok` / `recuperaciones_fallidas` | ✅ Verificable: la memoria con timeout no depende del montaje |
| SC-003 | Nunca corrección con `valida=False` | T041 | `causa != CORRECCION_*` | ✅ Verificable en footage |
| SC-004 | Decisión ≤ 8 fotogramas | T032, T042 | `latencia_decision_ms` ≤ 267 ms | ✅ Verificable |
| SC-005 | ≤ 33 ms/fotograma; el transporte no bloquea | T042, T031 | `-m perf` + test de no-bloqueo | ✅ Verificable |
| SC-006 | Estimador estable, correlación ≥ 0.7 | T039 | Dos estimadores sobre footage | ✅ Verificable (referencia: +0.76/+0.86) |
| SC-007 | Veto de FSM ⟹ `DETENER` siempre | T024, T036 | 100 % de fotogramas DETENIDO | ✅ Verificable |
| SC-008 | Protocolo pasa headless, 0 excepciones | T026, T027 | Suite con `TransporteSimulado` | ✅ Verificable |
| SC-009 | Evidencia visual por fotograma | T034 | `--diagnostico` | ✅ Verificable |

## C. Gates constitucionales

| Principio | Verificado en | Estado |
|-----------|---------------|--------|
| I. Visión clásica, sin auto-detección | `plan.md` Constitution Check; `research.md` Dec. 1 | ✅ PASS (T012, T047 verifican en código) |
| II. Pipeline por etapas, sin capas especulativas | `plan.md` Structure Decision | ✅ PASS — `src/transporte/` con responsabilidad real; `src/models/` y `src/services/` **siguen vacíos** |
| III. Dependencias declaradas y reproducibles | `plan.md` Impacto; `research.md` Dec. 7 | ✅ PASS — el transporte no añade dependencia alguna: `socket` es de la biblioteca estándar, así que no hay nada que declarar (T002 quedó superada) |
| IV. Tiempo real y determinista | `research.md` Dec. 2 y 6 | ✅ PASS — vectorizado, sin azar, envío desacoplado |
| V. Calidad verificable y evidencia medible | `quickstart.md`; `data-model.md` §10 | ✅ PASS (todas las historias probables sin hardware) |
| VI. Trazabilidad Spec Kit | Este documento; `plan.md` | ✅ PASS (artefactos en `specs/002-…`, sin uso de OpenSpec) |

**Decisión del §II sobre el orden** (control antes de FSM): documentada en `plan.md` Constitution
Check y argumentada en `research.md` Decisión 5. Se interpreta que el §II enumera **etapas**, no un
**árbitro de seguridad**; el compositor resuelve la precedencia sin alterar el contrato de 001.
**Sujeto a revisión en la revisión de cumplimiento.**

## D. Decisiones con evidencia medida

| Decisión | Evidencia | Artefacto |
|----------|-----------|-----------|
| Centroide del pico de columnas | sd 50.5/56.7 px vs 78.4/78.9 px del run más largo | `research.md` Dec. 1 |
| La señal es genuina | Correlación +0.76/+0.86 entre estimadores independientes | `research.md` Dec. 1 |
| La cámara está en la mano | 13.0/255 de movimiento medio inter-fotograma | `research.md` Dec. 1 |
| Zona muerta 0.10 | 40–82 % de fotogramas sin corregir en `rutaIdeal` | `research.md` Dec. 2 |
| `x_objetivo` configurable | Medianas 190.0–286.5 px vs centro 239 | `research.md` Dec. 3 |
| `n_gracia_busqueda = 5` | Velocidad de error 52.1 px en desarrilamiento vs 15–20 px en ideal | `research.md` Dec. 4 |
| Composición con veto de FSM | Un PARE pisado = fallo de seguridad | `research.md` Dec. 5 |
| `src/transporte/` | §II: la estructura se justifica por el pipeline, no por nombres | `research.md` Dec. 6 |
| Byte único sobre RFCOMM, sin dependencia de terceros | El profesor confirmó el protocolo junto con su código de ejemplo; desmentía la trama de 4 bytes y el puerto COM | `research.md` Dec. 7 |

## E. Riesgos abiertos (no cerrables en software)

| # | Riesgo | Dónde se registra | Tarea de cierre |
|---|--------|--------------------|-----------------|
| R1 | **Convención de giro** (línea a la derecha ⟹ giro a la derecha real) | `spec.md` Supuestos; `mapa-comandos.md` §5 | En pista. El control es simétrico al signo: corregirlo es un parámetro |
| R2 | `x_objetivo = 0.5` provisional | `esquema-configuracion.md` §6 | Recalibrar con footage del robot montado |
| R3 | Zona muerta calibrada con cámara en mano | `research.md` Dec. 2 | Recalibrar en pista; verificar SC-001 |
| R4 | `n_gracia_busqueda = 5` sin cinemática del robot | `research.md` Dec. 4 | Ajustar según el tiempo de giro real |
| P1–P5 | 5 preguntas abiertas del receptor BT, incluida la **MAC real del mBot** | `transporte-bluetooth.md` §8; `AGENTS.md` §27 | Con el docente y el firmware |
| — | Supuesto de un byte sin salto de línea **no verificado** (el `Robot.py` del profesor no está en el repo) | `research.md` Dec. 7; `transporte-bluetooth.md` §2 | En pista o con el robot conectado; si falla, es la constante `SUFIJO` |
| — | `t_parada_s = 3.0` provisional | Fuera de alcance (decisión del equipo) | Cambio separado |
| — | `data-model.md` de 001 documenta `roi_linea.y = 0.55` (obsoleto desde `7f0990c`) | T045 | Registrar el conflicto; no editar 001 aquí |
| — | `roi_linea` anidada dentro de `roi_senales` | `plan.md` Riesgos | No afecta a esta spec (solo usa `mascara_linea`) |

## F. Cierre de CHK035 (de 001)

| Ítem | Estado |
|------|--------|
| CHK035 — la máscara de línea no tiene consumidor | **Cerrada con 002**: T013 (`EstimadorLinea`) es el primer consumidor funcional. Se actualiza `checklists/plan-tecnico.md` de 001 en T044 |

---

**Resumen**: 38/38 FR trazados a diseño, tarea y verificación · 9/9 SC trazados, con SC-001 marcado
como **criterio de pista** y no de video · 6/6 gates constitucionales en PASS · 9 riesgos abiertos
declarados, ninguno cerrado de forma silenciosa.
