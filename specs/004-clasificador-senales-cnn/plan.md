# Implementation Plan: Clasificador CNN de Señales y Cadencia de Marcha

**Branch**: `main` | **Date**: 2026-11-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/004-clasificador-senales-cnn/spec.md`

## Summary

Integrar un clasificador CNN de 4 clases (`PARE`, `SIGA`, `ZONA ESCOLAR`, `VELOCIDAD 60`) como etapa **opcional** del pipeline de OptiPilot, sin migrar Python 3.14 ni instalar TensorFlow:

1. El proyecto `optipilot_classifier` exporta `MobileNet.keras` a `senales_mobilenet.onnx` + metadata, con verificación de paridad Keras/ONNX.
2. OptiPilot añade `onnxruntime` y un paquete `src/clasificacion/` que carga el modelo una vez.
3. Un localizador clásico nuevo (rojo/verde/amarillo + contornos) propone regiones y actúa como compuerta; la CNN clasifica el contexto del fotograma solo si hay región.
4. PARE/SIGA alimentan el `Detector` y la FSM existentes; ZONA/VELOCIDAD actualizan un `ModoMarcha`.
5. El bucle autónomo aplica la cadencia solicitada: PARE `x` 3.0 s; SIGA `w` cada 1.0 s; ZONA cada 2.0 s; VELOCIDAD cada 0.5 s.
6. Todo el camino nuevo está apagado por defecto (`--clasificador off`), de modo que la suite y el comportamiento actual no cambian.

## Technical Context

**Language/Version**: Python 3.14.7 en OptiPilot; Python 3.13.7 en el proyecto de entrenamiento.

**Primary Dependencies**: `numpy>=2.4`, `opencv-python-headless>=4.13`, `onnxruntime>=1.31` (runtime); `tensorflow>=2.21`, `keras>=3.15`, `tf2onnx>=1.17`, `onnx>=1.23` solo en entrenamiento/exportación.

**Storage**: modelo `.onnx` + `senales_mobilenet.json` en `assets/modelos/`; configuración en `config/vision.json`; salidas en `salidas/<corrida_id>/`.

**Testing**: `pytest` (unit + integration), marcador `cnn` opcional para smoke test con el modelo real; tests existentes sin cambios con el clasificador apagado.

**Target Platform**: Windows 11, cámara DroidCam por WiFi o índice local; robot mBot por RFCOMM (`w/a/d/x`).

**Project Type**: aplicación de visión en tiempo real con CLI de validación y control de robot.

**Performance Goals**: inferencia ONNX ≤ 15 ms por fotograma; bucle completo dentro del presupuesto de 33 ms/fotograma cuando sea posible, o inferencia cada N fotogramas con confirmación sobre muestras de inferencia.

**Constraints**: sin TensorFlow en `src/`; `src/vision/` sin E/S; un byte por comando; PARE 3.0 s; cadencia en segundos; sin hardware nuevo.

**Scale/Scope**: 4 clases, una región por señal, video/cámara en vivo, una corrida a la vez.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **§I Técnicas permitidas**: la localización usa HSV, umbralización, morfología y contornos (permitidas). La CNN es una excepción autorizada para la fase posterior, no para el Reto 1; queda registrada en la spec y en AGENTS.md.
- **§II Separación y estructura**: `src/vision/` sigue siendo lógica pura; la E/S del modelo vive en `src/clasificacion/`; `src/transporte/` sigue siendo el único paquete con sockets.
- **§III Dependencias**: se añade `onnxruntime` (runtime) y herramientas de exportación solo en el proyecto de entrenamiento. No se introduce TensorFlow en OptiPilot.
- **§IV Determinismo**: localizador y mapeo de clases son deterministas; la inferencia ONNX es determinista para la misma entrada. La cadencia depende de `t_s` inyectado, no del reloj global dentro de la lógica.
- **§V Pruebas sin hardware**: localizador, clasificador falso, cadencia y pipeline se prueban con dobles; el modelo real es un smoke test opcional.
- **§VI Documentación y trazabilidad**: se actualizan AGENTS.md, la spec y las tareas; las métricas y el visor muestran la decisión.

Sin violaciones no justificadas. El uso de CNN está explícitamente autorizado para esta fase y separado del Reto 1.

## Project Structure

### Documentation (this feature)

```text
specs/004-clasificador-senales-cnn/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── tasks.md
├── contracts/
│   ├── clasificador-senales.md
│   ├── cadencia-marcha.md
│   └── cli.md
└── checklists/
    └── plan-tecnico.md
```

### Source Code (repository root)

```text
src/
├── clasificacion/
│   ├── __init__.py
│   ├── base.py              # Protocol ClasificadorSenales (importa modelos de vision)
│   └── onnx.py              # ClasificadorONNX (única frontera de E/S)
├── vision/
│   ├── localizacion_senales.py   # regiones rojo/verde/amarillo
│   ├── cadencia_marcha.py        # lógica pura de intervalos
│   ├── modelos.py                # ClaseSenalExtra, ModoMarcha, PrediccionSenal, RegionSenal, ClasificacionCNN
│   ├── configuracion.py          # rango amarillo + bloque CNN/cadencia
│   ├── pipeline.py               # etapa opcional CNN
│   ├── metricas.py               # métricas CNN y modo
│   └── visualizacion.py          # caja/etiqueta/modo
├── transporte/                   # sin cambios
└── main.py                       # flags y cadencia

assets/modelos/
├── senales_mobilenet.onnx
└── senales_mobilenet.json

config/vision.json                # parámetros nuevos
tests/
├── unit/
│   ├── test_localizacion_senales.py
│   ├── test_clasificador_onnx.py
│   └── test_cadencia_marcha.py
└── integration/
    └── test_clasificador_cnn.py
```

**Structure Decision**: se mantiene la arquitectura de pipeline existente. Se añade `src/clasificacion/` para aislar la E/S del modelo y `src/vision/localizacion_senales.py` para la propuesta clásica; no se tocan `src/models/` ni `src/services/`.

## Phase 0: Research

Ver [research.md](./research.md). Decisiones principales:

1. **ONNX Runtime en Python 3.14** en lugar de Keras in-process: TensorFlow 2.21 no tiene wheel `cp314`; `onnxruntime` 1.31 sí. Se evita migrar el proyecto y se mantiene la suite.
2. **Híbrido, no full-frame**: el MobileNet actual predice `SIGA` con 60.8–95.6 % sobre frames sin señal de `videos/rutaIdeal/`; clasificar el frame completo es inseguro. La localización clásica restringe el dominio.
3. **MobileNet** como modelo desplegado: mejor relación latencia/accuracy del experimento; VGG/ResNet/DenseNet quedan como comparación offline.
4. **Cadencia por señal** en segundos, con `w` gobernado por el modo y correcciones `a`/`d` con la cadencia de fotogramas existente.
5. **PARE** sigue en la FSM existente (`t_parada_s = 3.0`), no se duplica en la cadencia.
6. **Modelo externo, artefacto interno**: no se importa `optipilot_classifier`; solo se copia el `.onnx` + metadata.

## Phase 1: Design

Ver [data-model.md](./data-model.md) y [contracts/](./contracts/).

### Data flow

```text
frame BGR
  ├─ Preprocesador → hsv_senales
  ├─ LocalizadorSenales → regiones (rojo/verde/amarillo)
  ├─ ClasificadorONNX(contexto) → PrediccionSenal
  ├─ filtro por confianza + supresión
  ├─ CandidatoSenal (PARE/SIGA) → Detector → FSM
  └─ clases extra → confirmación → ModoMarcha
        │
        ▼
  ControlTrayectoria → compositor → CadenciaMarcha → ColaTransporte
```

### Interfaces

- `Protocol ClasificadorSenales`: `clasificar(imagen_bgr: np.ndarray) -> PrediccionSenal` y `cerrar()`.
- `ClasificadorONNX`: carga `InferenceSession`, metadata y aplica el preproceso MobileNet.
- `LocalizadorSenales.propuestas(pre: ResultadoPreprocesamiento) -> list[RegionSenal]`.
- `CadenciaMarcha.debe_enviar(comando, modo, t_s) -> bool` + `reiniciar()`.
- `PipelineVision(params, clasificador=None)` y `ResultadoProcesamiento(clasificaciones_cnn, modo_marcha)`.
- `CadenciaMarcha` solo se instancia cuando `--clasificador onnx`; con `off`, `main.py` conserva el camino actual (`indice % fotogramas_por_orden`) y no cambia el comportamiento.
- `pipeline.py` referencia el `Protocol ClasificadorSenales` solo bajo `TYPE_CHECKING` y lo consume por duck typing en runtime, para no crear un ciclo `vision.pipeline → clasificacion.base → vision.modelos`.

### Configuration

Campos nuevos en `ParametrosConfiguracion` y `config/vision.json`:

- `rango_hsv_amarillo`
- `clasificador_habilitado`
- `ruta_modelo_senales`
- `ruta_metadatos_senales`
- `umbral_confianza_senal`
- `area_minima_region_senal_rel`
- `n_confirmacion_extra`
- `intervalo_siga_s`
- `intervalo_zona_escolar_s`
- `intervalo_velocidad_60_s`

Validaciones: HSV válido y sin solape con rojo/verde; umbral en [0,1]; área en (0,1); intervalos > 0; `n_confirmacion_extra >= 1`.

### Error handling

- Modelo ausente/inválido con `--clasificador onnx`: error de arranque, código distinto de 0.
- ONNX Runtime no instalado: mensaje claro; el camino `off` no lo importa.
- Recorte vacío o imagen inválida: predicción descartada sin excepción.
- Fallo interno del clasificador: se registra y se descarta la predicción; la FSM y el control siguen funcionando.
- Fuente de video vacía: comportamiento degradado existente.

## Phase 2: Task Planning Approach

Las tareas se generan en [tasks.md](./tasks.md), ordenadas por dependencia:

1. Exportación ONNX + paridad (proyecto de entrenamiento).
2. Dependencia y artefacto en OptiPilot.
3. Modelos/configuración y validaciones.
4. Localizador clásico.
5. Paquete de clasificación ONNX.
6. Integración en pipeline y CLI.
7. Cadencia de marcha.
8. Métricas y visualización.
9. Tests unitarios/integración y suite completa.
10. Documentación (AGENTS.md, quickstart, póster si aplica).

## Cobertura del plan aprobado

| Elemento del plan | Dónde queda en la spec |
|---|---|
| No importar `optipilot_classifier`; separar entrenamiento y runtime | Research Decisión 7; Assumptions «Un solo proceso»; FR-029 |
| ONNX Runtime en Python 3.14, sin TensorFlow | Clarifications; FR-012; Research Decisión 1; SC-005/SC-006 |
| Híbrido: clásico localiza, CNN clasifica | Clarifications; US1; FR-001–FR-012 |
| Localizador rojo/verde/amarillo + contornos | FR-001–FR-005C; Research Decisión 3 |
| Paquete `src/clasificacion/` como frontera de E/S | FR-029; plan §Project Structure; data-model §Ubicación |
| Inyección opcional en `PipelineVision` | FR-026; plan §Interfaces |
| CLI `--clasificador`, `--modelo-senales`, `--metadatos-senales` | FR-027–FR-028; contracts/cli.md |
| PARE `x` + 3.0 s + reanudar | FR-016–FR-017; contracts/cadencia-marcha.md |
| SIGA 1.0 s, ZONA 2.0 s, VELOCIDAD 0.5 s | FR-018–FR-021; SC-004; contracts/cadencia-marcha.md |
| Primer `w` inmediato; correcciones con `fotogramas_por_orden` | FR-022–FR-023; contracts/cadencia-marcha.md |
| Solo con clasificador activo; `off` idéntico | FR-025A; contracts/cadencia-marcha.md §9 |
| Métricas y visor | FR-034–FR-037; SC-009; US4 |
| Exportación y paridad | FR-031–FR-033; SC-005; quickstart |
| Validación con dataset y riesgo de dominio | SC-001/SC-001A/SC-002; Assumptions; Research Decisión 2 |
| Suite existente intacta | FR-026; SC-007; tasks Fase 3/6 |
| Actualización de AGENTS.md | Task T035; plan §Phase 2 |

## Risks & Mitigations

| Riesgo | Impacto | Mitigación |
|---|---|---|
| El modelo no generaliza a la cámara del robot | Falsos positivos/negativos | Híbrido con localización clásica, umbral 0.70, confirmación 3; grabar footage y reentrenar después |
| `w` espaciado no cambia la velocidad real | La cadencia no produce el efecto esperado | Validar en pista; documentar el supuesto; el firmware es del robot |
| Latencia ONNX > presupuesto | Bucle lento | Medir; inferir cada N frames; MobileNet es el modelo más liviano |
| Exportación Keras 3 → ONNX falla | Bloqueo de integración | Fallback a SavedModel temporal con `tf2onnx`; verificar paridad antes de copiar |
| `onnxruntime` cp314 no carga | Bloqueo de runtime | Verificar import y smoke test antes de cablear; alternativa: migrar a 3.13 (no preferida) |
| ZONA/VELOCIDAD persistentes aunque el cartel desaparezca | Marcha inadecuada | Es el comportamiento solicitado; se puede añadir expiración configurable si el docente lo pide |

## Complexity Tracking

No hay violaciones de la Constitución que justificar. La única desviación es el uso de CNN, autorizado para esta fase y registrado en la spec; no afecta al Reto 1 original.
