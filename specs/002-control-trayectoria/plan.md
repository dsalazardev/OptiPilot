# Implementation Plan: Cálculo de Posición de Línea y Control de Trayectoria

**Branch**: `feature/002-control-trayectoria` (base: `dev` en `7f0990c`) | **Date**: 2026-09-28 | **Spec**: [spec.md](./spec.md)

**Input**: Especificación de la feature en `/specs/002-control-trayectoria/spec.md`

## Summary

Implementar las dos etapas que `specs/001-cv-sign-detection` declaró fuera de alcance y que cierran
CHK035 (la máscara de línea no tenía consumidor funcional):

1. **Posición de la línea** (Objetivo 3): estimar la posición lateral de la guía por fotograma a
   partir de la máscara, mediante el centroide del pico de la proyección de columnas.
2. **Control de trayectoria** (Objetivo 4): convertir esa posición en uno de cuatro comandos
   (`AVANZAR`, `IZQUIERDA`, `DERECHA`, `DETENER`) con zona muerta, histéresis y recuperación por
   memoria del último lado conocido.
3. **Transporte Bluetooth Classic SPP**: interfaz delgada, asíncrona y con simulador, para enviar
   los comandos al robot sin bloquear el bucle de visión.

Enfoque técnico: módulos Python puros en `src/vision/` siguiendo el patrón de etapas de 001;
lógica determinista e inyectable para pruebas headless; todo el cálculo de línea basado en
aritmética sobre la máscara (sin Hough ni detectores automáticos, por el Principio I y §III);
transporte aislado en `src/transporte/` con simulador por defecto; `pyserial` declarado y usado solo
en ese paquete.

## Technical Context

**Language/Version**: Python 3.14.7 (venv gestionado con uv; `requires-python = ">=3.14"`).

**Primary Dependencies**: `opencv-python-headless` ≥ 4.13, NumPy (ya instalados), **`pyserial`**
(nuevo, declarado en `pyproject.toml` y versionado en `uv.lock`), `pytest` como dependencia de
desarrollo. Configuración en JSON estándar.

**Storage**: Sistema de archivos — configuración en `config/vision.json` (se **extiende**, no se
parte); salidas de diagnóstico y métricas en `salidas/` (ignorado por git); videos de validación en
`videos/` (no versionados).

**Testing**: pytest headless; unitarias por etapa (configuración de los parámetros nuevos,
estimador, control, compositor, cola, transporte) e integración (secuencias de fotogramas y replay
del footage real). Generador sintético ampliado con líneas desplazadas. **Ninguna prueba requiere
hardware**: el `TransporteSimulado` es el transporte por defecto.

**Target Platform**: Windows 11 (desarrollo); ejecución headless en la laptop del equipo durante el
recorrido. El robot es el destino físico, fuera del repositorio.

**Project Type**: Proyecto único — paquete Python (`src/`) con entry point de validación (CLI) y
suite de pruebas.

**Performance Goals**: ≤ 33 ms por fotograma a 30 fps incluyendo posición y control (SC-005);
decisión ≤ 8 fotogramas desde que la línea es visible (SC-004); el transporte no añade latencia al
bucle de visión (SC-005).

**Constraints**: Solo visión clásica autorizada por el Reto 1 (sin DL, modelos preentrenados, Haar
ni auto-detección de línea — explícitamente **sin Hough**); parámetros centralizados (FR-038);
determinismo total (sin azar); `src/vision/` **sin I/O**; `t_parada_s` y la semántica de la FSM
**intactos**; cuatro comandos discretos, sin velocidad ni duración de giro.

**Scale/Scope**: 1 cámara / 1 flujo; 2 etapas nuevas de visión + 1 de transporte; 4 comandos;
10 parámetros de configuración nuevos; corpus de validación: los 9 videos de práctica (locales, no
versionados) + secuencias sintéticas.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Gate | Estado |
|-----------|------|--------|
| I. Restricción Técnica Absoluta: Visión Clásica (NON-NEGOTIABLE) | La posición de línea se calcula **solo** con sumas por columna, umbral de medio pico y media ponderada sobre la máscara — aritmética autorizada, decisión del equipo. **Sin `HoughLinesP`, sin `fitLine`**, sin ninguna dependencia que detecte la línea automáticamente (§III lo prohíbe incluso para "herramientas de visión" convencionales). `pyserial` es transporte de bytes, no de visión. | PASS |
| II. Arquitectura de Pipeline Explícito por Etapas | Dos etapas nuevas con módulo y contrato propios: `posicion_linea.py` y `control_trayectoria.py`, más `compositor.py` como punto de arbitraje explícito. `src/transporte/` se crea **con una responsabilidad real** (transporte de comandos), no por nombre de carpeta. `src/models/` y `src/services/` **siguen vacíos**: la §II exige justificar la estructura por el pipeline. | PASS |
| III. Organización del Código y Dependencias Reproducibles | `pyserial` se declara en `pyproject.toml` antes de importarse, se instala con uv y se versiona en `uv.lock`. `import serial` **solo** aparece en `src/transporte/spp.py`. Sin secretos ni credenciales. `.venv` no versionado. | PASS |
| IV. Tiempo Real y Comportamiento Determinista | Estimador vectorizado (sin bucles por píxel); control determinista sin azar; envío **desacoplado** por `ColaTransporte` (nada de escrituras bloqueantes en el bucle); la pérdida temporal de línea se tolera y se recupera de forma autónoma (memoria del último lado). Todos los umbrales son parámetros configurables. | PASS |
| V. Calidad Verificable: Pruebas y Evidencia Medible | Cada etapa es headless y determinista; validación contra footage real antes de integrar (§V); métricas de rúbrica (correcciones, pérdidas, recuperaciones, latencia) registradas y exportadas; comando y resultados documentados en este mismo cambio. | PASS |
| VI. Trazabilidad Documental y Proceso de Planificación (Spec Kit) | Artefactos en `specs/002-control-trayectoria/` trazables a FR y SC; los vacíos del docente y el riesgo de convención de giro quedan registrados en `spec.md`, `research.md` y `AGENTS.md` §27 en el mismo cambio. | PASS |

**Nota sobre el orden del §II** (decisión de diseño, `research.md` Decisión 5): la Constitución
enumera el pipeline como *… posición de línea → control de trayectoria → señales → máquina de
estados → métricas*. Leída como orden de ejecución, el control se ejecutaría antes de la FSM, lo que
permitiría que una corrección de dirección **pisara** un PARE confirmado y el robot girara en vez de
detenerse.

Se interpreta que el §II describe **etapas del pipeline**, no un **árbitro de seguridad**, y se
introduce `compositor.py` como punto de convergencia donde la FSM tiene voto de veto. La Constitución
exige que cada etapa tenga «una única responsabilidad» y un contrato claro — el compositor cumple
eso, y `DecisionMovimiento` conserva su semántica sin modificación. La decisión queda argumentada en
`research.md` y es revisable en la revisión de cumplimiento.

**Complejidad**: sin violaciones que requieran justificación.

**Re-check post-Fase 1 (diseño)**: PASS — el diseño generado (`research.md`, `data-model.md`,
`contracts/`, `quickstart.md`) mantiene los seis gates: aritmética autorizada sin detectores
automáticos (I), módulos por etapa con contratos explícitos y sin capas especulativas (II),
`pyserial` declarada y confinada a `src/transporte/` (III), lógica determinista con envío desacoplado
(IV), pruebas headless y métricas exportables (V), artefactos Spec Kit trazables (VI).

## Project Structure

### Documentación (esta feature)

```text
specs/002-control-trayectoria/
├── spec.md              # Requerimientos (4 historias, 38 FR, 9 SC)
├── plan.md              # Este archivo (salida de /speckit.plan)
├── research.md          # Phase 0 output — 6 decisiones con alternativas rechazadas
├── data-model.md        # Phase 1 output — entidades e invariantes
├── quickstart.md        # Phase 1 output — verificación
├── contracts/           # Phase 1 output
│   ├── api-control.md           # Contratos de estimador, control y compositor
│   ├── transporte-bluetooth.md  # Trama SPP, opcodes, fallo seguro
│   ├── esquema-configuracion.md # 10 parámetros nuevos + validación
│   └── mapa-comandos.md         # Los 4 comandos, precedencia, evidencia visual
├── checklists/
│   └── plan-tecnico.md  # Trazabilidad por principio constitucional
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
config/
└── vision.json                      # Se extiende con 10 claves (no se parte)

src/
├── __init__.py                      # (existente)
├── main.py                          # CLI: cablea pipeline → control → compositor → cola
├── vision/
│   ├── __init__.py
│   ├── modelos.py                   # + ComandoMovimiento, Lado, CausaComando, PosicionLinea
│   ├── configuracion.py             # + ParametrosControl y su validación
│   ├── preprocesamiento.py          # (existente, sin cambios)
│   ├── segmentacion.py              # (existente, sin cambios)
│   ├── candidatos.py                # (existente, sin cambios)
│   ├── deteccion.py                 # (existente, sin cambios)
│   ├── posicion_linea.py            # NUEVO — Objetivo 3 (centroide del pico)
│   ├── control_trayectoria.py       # NUEVO — Objetivo 4 (bang-bang + histéresis + memoria)
│   ├── compositor.py                # NUEVO — arbitraje: control propone, FSM veto
│   ├── maquina_estados.py           # (existente, SIN cambios — su contrato no se toca)
│   ├── metricas.py                  # + MetricasControl (correcciones, pérdidas, velocidad)
│   ├── visualizacion.py             # + evidencia de posición, objetivo y comando
│   └── pipeline.py                  # Integra las etapas nuevas
└── transporte/                      # NUEVO — fuera de vision/ porque hace I/O
    ├── __init__.py
    ├── base.py                      # Protocol Transporte (sin I/O)
    ├── simulado.py                  # TransporteSimulado (todas las pruebas)
    ├── spp.py                       # TransporteSPP — ÚNICO archivo que importa serial
    └── cola.py                      # ColaTransporte (desacople + deduplicación)

tests/
├── conftest.py                      # + fixtures de línea desplazada
├── fixtures/
│   └── generador_sintetico.py       # + línea con desplazamiento y hueco
├── unit/
│   ├── test_configuracion.py        # + validación de los 10 parámetros nuevos
│   ├── test_posicion_linea.py       # NUEVO
│   ├── test_control_trayectoria.py  # NUEVO
│   ├── test_compositor.py           # NUEVO
│   ├── test_cola_transporte.py      # NUEVO
│   └── test_transporte.py           # NUEVO (SPP con simulado, protocolo, fallos)
└── integration/
    ├── test_control_fotogramas.py   # NUEVO — secuencia completa
    ├── test_footage_control.py      # NUEVO — replay de videos/ (marcador footage)
    └── test_rendimiento.py          # + presupuesto de las etapas nuevas

salidas/                             # Diagnóstico y métricas (git-ignored)
videos/                              # Footage local (git-ignored, no versionado)
```

**Structure Decision**: se sigue el patrón de 001 — un módulo por etapa del pipeline en
`src/vision/`, `modelos.py` como contratos compartidos, `pipeline.py` como fachada.

**Por qué `src/transporte/` y no `src/services/` o `src/models/`**: esas carpetas existen pero están
vacías, y la Constitución §II es explícita: *«MUST NOT existir capas, paquetes ni abstracciones sin
una responsabilidad real: la estructura se justifica por el pipeline, no por nombres de carpetas
(`src/models/` y `src/services/` no constituyen arquitectura mientras nada los defina)»*. «services»
no describe una etapa del pipeline. `transporte` sí: es la etapa que lleva la decisión al robot.
Ambas carpetas **siguen vacías**.

**Por qué fuera de `src/vision/`**: `src/vision/` es lógica pura sin I/O por diseño de 001 (las
pruebas lo asumen). `pyserial` hace I/O. Separarlos mantiene la suite headless y permite que
`TransporteSimulado` sustituya al driver real sin tocar una sola línea de visión.

**Impacto en artefactos existentes**:

| Artefacto | Cambio |
|-----------|--------|
| `pyproject.toml` | **Añadir** `pyserial` a `dependencies` |
| `uv.lock` | **Actualizar** por `uv sync` (reproducibilidad, Principio III) |
| `src/vision/modelos.py` | **Añadir** `ComandoMovimiento`, `Lado`, `CausaComando`, `PosicionLinea`, `DecisionControl`, `DecisionCompuesta` (sin tocar lo existente) |
| `src/vision/configuracion.py` | **Añadir** los 10 parámetros y sus reglas cruzadas |
| `src/vision/pipeline.py` | **Integrar** estimador, control y compositor en el bucle |
| `src/vision/metricas.py` | **Añadir** `MetricasControl` |
| `src/vision/visualizacion.py` | **Extender** con evidencia de posición, objetivo y comando |
| `src/main.py` | **Cablear** cola y transporte; flag `--transporte {simulado,spp}` |
| `src/vision/maquina_estados.py` | **SIN CAMBIOS** — su contrato se preserva (FR-026) |
| `tests/fixtures/generador_sintetico.py` | **Añadir** línea desplazada y con hueco |
| `AGENTS.md` | **Actualizar** estado real, comandos, riesgo de giro y vacíos (§VI) |
| `specs/001-cv-sign-detection/checklists/plan-tecnico.md` | Marcar CHK035 **cerrada** con referencia a 002 |

**Riesgos aceptados conscientemente**:

| Riesgo | Por qué se acepta | Mitigación |
|--------|-------------------|------------|
| El orden del §II se interpreta (control antes de FSM) | La lectura literal permitiría que una corrección pisara un PARE | Compositor con veto de FSM; documentado en `research.md` Decisión 5 y en el Constitution Check |
| Convención de giro no validable en software | Depende del montaje físico; los videos son de cámara en mano | Ley de control simétrica al signo del error: corregirlo es un parámetro, no un rediseño. Declarado como supuesto de riesgo |
| Zona muerta y `x_objetivo` calibrados con cámara en mano | No hay footage del robot montado | Marcado provisional; tarea de recalibración con footage propio |
| `roi_linea` anidada dentro de `roi_senales` | Consecuencia de la recalibración de 001 (y 0.10) | No afecta a esta spec: US1 solo usa `mascara_linea`. Se registra como inconsistencia |

## Complexity Tracking

> Sin violaciones constitucionales; no se requiere justificación de complejidad.

Nota de gobernanza: se mantiene el flujo de Spec Kit (Principio VI). OpenSpec queda sin uso para este
cambio, por decisión explícita del equipo, para no duplicar trabajo entre herramientas.
