# Implementation Plan: Módulo de Procesamiento de Imagen y Detección de Señales PARE/SIGA

**Branch**: `001-cv-sign-detection` (git: `main`) | **Date**: 2026-09-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-cv-sign-detection/spec.md`

## Summary

Implementar el módulo de visión del cerebro del robot: pipeline clásico de procesamiento de imagen
(suavizado, conversión a HSV, ROI, segmentación por color, morfología, contornos, geometría de
octágonos) que produce máscaras de línea y señales, detección y clasificación confirmada de octágonos
PARE/SIGA, una máquina de estados determinista que decide AUTORIZADO/NO AUTORIZADO (parada por T
mínimo y reanudación por SIGA), métricas y evidencia visual por etapa.

Enfoque técnico: OpenCV headless como biblioteca de primitivas autorizadas; módulos Python puros por
etapa en `src/vision/` con contratos de datos explícitos; lógica determinista e inyectable para
pruebas headless (pytest con imágenes sintéticas y fotogramas); parámetros centralizados en JSON;
entry point de validación sobre archivos de video.

## Technical Context

**Language/Version**: Python 3.14.7 (venv gestionado con uv; `requires-python = ">=3.14"`).

**Primary Dependencies**: `opencv-python-headless` ≥ 4.13 (wheels oficiales con soporte Python 3.14)
y NumPy (ya instalado en el venv); `pytest` como dependencia de desarrollo. Configuración en JSON
estándar (sin dependencias adicionales).

**Storage**: Sistema de archivos — configuración JSON en `config/vision.json`; salidas de
diagnóstico y métricas en `salidas/` (ignorado por git); videos de validación locales en `videos/`
(no versionados).

**Testing**: pytest headless; unitarias por etapa (configuración, segmentación, candidatos,
confirmación, máquina de estados, métricas) e integración sobre secuencias de fotogramas; generador
de imágenes sintéticas con OpenCV/NumPy; sin cámara ni GUI.

**Target Platform**: Windows 11 (desarrollo, repositorio en OneDrive); módulo ejecutable headless en
la máquina del robot (hardware por definir fuera de este alcance).

**Project Type**: Proyecto único — paquete Python (`src/`) con entry point de validación (CLI) y
suite de pruebas.

**Performance Goals**: ≤ 33 ms por fotograma a 30 fps (SC-007); decisión (detener/continuar) ≤ 8
fotogramas desde visibilidad plena (SC-006); reanudación ≤ 5 fotogramas tras cumplirse la condición
(SC-009).

**Constraints**: Solo visión clásica autorizada por el Reto 1 (sin DL, modelos preentrenados, Haar ni
auto-detección); parámetros centralizados (FR-024); determinismo total (sin fuentes de azar; K-Means
no se usa en v1); el módulo no controla motores (entrega `DecisiónMovimiento` a la capa de control);
cámara y canal físico fuera de alcance; T provisional configurable pendiente de confirmación del
docente.

**Scale/Scope**: 1 cámara / 1 flujo de fotogramas; 2 clases de señal (PARE/SIGA) + máscara de línea;
~8 etapas de pipeline; corpus de validación: videos de práctica (externos) + grabaciones propias;
~15 parámetros de configuración.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Gate | Estado |
|-----------|------|--------|
| I. Restricción Técnica Absoluta: Visión Clásica (NON-NEGOTIABLE) | OpenCV usado solo como primitivas autorizadas (espacios de color, umbralización, morfología, contornos, `approxPolyDP`, Canny opcional); cero técnicas prohibidas; dependencia justificada como biblioteca de primitivas con lógica de detección propia | PASS |
| II. Arquitectura de Pipeline Explícito por Etapas | Un módulo por etapa con contrato de entrada/salida, inspeccionable y visualizable por etapa; sin capas especulativas (`src/models/`, `src/services/` permanecen vacíos y sin rol) | PASS |
| III. Organización del Código y Dependencias Reproducibles | Dependencias declaradas en `pyproject.toml` e instaladas con uv; se adopta y versiona `uv.lock` (documentado); `.venv` no versionado; módulos por etapa del pipeline | PASS |
| IV. Tiempo Real y Comportamiento Determinista | Parámetros centralizados (FR-024); máquina de estados determinista probada por inyección de eventos; presupuesto de latencia medido y reportado; sin azar | PASS |
| V. Calidad Verificable: Pruebas y Evidencia Medible | pytest headless con fixtures sintéticas y fotogramas; métricas de rúbrica registradas y exportadas; comandos documentados en el mismo cambio | PASS |
| VI. Trazabilidad Documental y Proceso de Planificación (Spec Kit) | Spec/plan/tasks en `specs/` trazables a FR/SC; `AGENTS.md` y comandos actualizados en el mismo cambio | PASS |

**Gobernanza (actualizada)**: el Principio VI nombraba OpenSpec como flujo de planificación; la
constitución fue enmendada a v2.0.0 (2026-09-24) para reconocer Spec Kit (adoptado en el commit
`docs/spec-kit`) como herramienta activa de gobernanza y planificación. Este cambio se planifica en
`specs/001-cv-sign-detection/` conforme a ese flujo y la trazabilidad queda cubierta por sus
artefactos.

**Re-check post-Fase 1 (diseño)**: PASS — el diseño generado (`research.md`, `data-model.md`,
`contracts/`, `quickstart.md`) mantiene los seis gates: sin técnicas prohibidas (I), un módulo por
etapa con contratos explícitos y sin capas especulativas (II), dependencias declaradas con `uv.lock`
versionado (III), máquina de estados determinista e inyectable (IV), pruebas headless y métricas
exportables (V), artefactos Spec Kit trazables más actualización de `AGENTS.md` en el mismo cambio
(VI). No se requieren justificaciones de complejidad.

## Project Structure

### Documentation (this feature)

```text
specs/001-cv-sign-detection/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
│   ├── api-pipeline.md
│   ├── esquema-configuracion.md
│   └── esquema-eventos-metricas.md
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
config/
└── vision.json                      # Configuración por defecto versionada (parámetros centralizados)

src/
├── __init__.py                      # (existente)
├── main.py                          # Entry point de validación (reemplaza el sample de PyCharm)
└── vision/
    ├── __init__.py
    ├── modelos.py                   # Contratos de datos compartidos (entidades, enums, dataclasses)
    ├── configuracion.py             # ParametrosConfiguracion: defaults, carga y validación JSON
    ├── preprocesamiento.py          # Suavizado + BGR→HSV + recorte de ROI
    ├── segmentacion.py              # Máscaras binarias (línea, rojo, verde) + morfología
    ├── candidatos.py                # Contornos: área mínima, vértices (approxPolyDP), propiedades
    ├── deteccion.py                 # Clasificación PARE/SIGA + confirmación temporal (N/K/X)
    ├── maquina_estados.py           # EN MARCHA / DETENIDO (fases) + DecisiónMovimiento
    ├── metricas.py                  # Eventos, ocurrencias y resumen exportable por corrida
    ├── visualizacion.py             # Anotación por etapa (modo diagnóstico)
    └── pipeline.py                  # Orquestador por fotograma (fachada estable)

tests/
├── conftest.py
├── fixtures/
│   ├── generador_sintetico.py       # Octágonos y líneas sintéticos con HSV controlado
│   └── __init__.py
├── unit/
│   ├── test_configuracion.py
│   ├── test_segmentacion.py
│   ├── test_candidatos.py
│   ├── test_deteccion_confirmacion.py
│   ├── test_maquina_estados.py
│   └── test_metricas.py
└── integration/
    ├── test_pipeline_fotogramas.py
    ├── test_escenarios_estado.py
    ├── test_corrida_demo.py
    ├── test_footage_linea.py
    └── test_rendimiento.py

salidas/                             # Artefactos de diagnóstico y métricas (git-ignored)
videos/                              # Footage local de validación (git-ignored, no versionado)
```

**Structure Decision**: proyecto único con el pipeline en `src/vision/` — un módulo por etapa del
pipeline (Principio II), `modelos.py` como contratos de datos compartidos (entidades, enums y
dataclasses; sin lógica de etapa) y `pipeline.py` como fachada estable que orquesta por fotograma.
`tests/` separa unitarias (etapas aisladas, inyección de datos) de integración (secuencias completas
de fotogramas). `src/models/` y `src/services/` quedan vacíos: no se les asigna rol para no crear
arquitectura especulativa. `src/main.py` deja de ser el sample de PyCharm y pasa a ser el CLI de
validación.

**Impacto en artefactos existentes**:

| Artefacto | Cambio |
|-----------|--------|
| `pyproject.toml` | Añadir `dependencies` (opencv-python-headless, numpy), grupo dev (pytest), `[tool.uv] package = false`, `[tool.pytest.ini_options]` con `pythonpath`/`testpaths`/marcadores |
| `uv.lock` | Nuevo (se adopta y versiona para reproducibilidad; se documenta) |
| `config/vision.json` | Nuevo (valores por defecto de todos los parámetros) |
| `src/main.py` | Reemplazar el sample por el CLI de validación |
| `src/vision/**` | Nuevo (pipeline completo) |
| `tests/**` | Nuevo (unitarias + integración + fixtures) |
| `.gitignore` | Ignorar `salidas/`, `videos/`, `.pytest_cache/`; NO ignorar `uv.lock` |
| `AGENTS.md` | Actualizar comandos (uv sync, pytest, CLI), dependencias, estado del proyecto y comandos verificados |

## Complexity Tracking

> Sin violaciones constitucionales; no se requiere justificación de complejidad.

Nota de gobernanza: la enmienda v2.0.0 de la constitución (2026-09-24) reconoce Spec Kit como
herramienta activa de gobernanza y planificación; este plan y sus artefactos quedan alineados con ese
flujo (Principio VI).
