# Data Model: Clasificador CNN de Señales y Cadencia de Marcha

**Feature**: `004-clasificador-senales-cnn` | **Date**: 2026-11-02

## Ubicación de los tipos compartidos

`ClaseSenalExtra`, `ModoMarcha`, `PrediccionSenal`, `RegionSenal` y `ClasificacionCNN` viven en `src/vision/modelos.py` (datos puros, sin E/S). `src/clasificacion/base.py` y `src/clasificacion/onnx.py` importan esos tipos desde `src.vision.modelos`; no se crea un `src/clasificacion/modelos.py` para evitar un ciclo `vision → clasificacion → vision`. `src/vision/pipeline.py` referencia el `Protocol` solo bajo `TYPE_CHECKING` y lo consume por duck typing en runtime.

## Enums nuevos

### `ColorRegion`

```python
class ColorRegion(StrEnum):
    ROJO = "ROJO"
    VERDE = "VERDE"
    AMARILLO = "AMARILLO"
```

Indica qué máscara clásica originó la propuesta; la CNN debe ser coherente con ella.

### `ClaseSenalExtra`

```python
class ClaseSenalExtra(StrEnum):
    ZONA_ESCOLAR = "ZONA ESCOLAR"
    VELOCIDAD_60 = "VELOCIDAD 60"
```

Se mantiene separado de `ClaseSenal` (PARE/SIGA) para no alterar la FSM ni el `Detector`.

### `ModoMarcha`

```python
class ModoMarcha(StrEnum):
    SIGA = "SIGA"
    ZONA_ESCOLAR = "ZONA ESCOLAR"
    VELOCIDAD_60 = "VELOCIDAD 60"
```

Determina el intervalo de `w`:

| Modo | Intervalo | Config |
|---|---:|---|
| `SIGA` | 1.0 s | `intervalo_siga_s` |
| `ZONA_ESCOLAR` | 2.0 s | `intervalo_zona_escolar_s` |
| `VELOCIDAD_60` | 0.5 s | `intervalo_velocidad_60_s` |

`PARE` no es un modo de marcha: es un veto de la FSM.

## Entidades

### `RegionSenal`

Propuesta clásica antes de la CNN.

| Campo | Tipo | Descripción |
|---|---|---|
| `caja_px` | `tuple[int, int, int, int]` | `(x, y, w, h)` en coordenadas del fotograma completo |
| `centro_px` | `tuple[int, int]` | centroide de la región |
| `area_px` | `int` | área del contorno |
| `area_rel` | `float` | área / área de `roi_senales` |
| `n_vertices` | `int` | vértices de `approxPolyDP` |
| `aspecto` | `float` | `w / h` |
| `color` | `ColorRegion` | máscara que originó la propuesta |

Invariantes: `w > 0`, `h > 0`, `area_rel >= 0`, `n_vertices >= 1`, `aspecto > 0`.

El localizador reutiliza `aspecto_min`/`aspecto_max` de la configuración existente y **no** exige 8 vértices: acepta el pentágono de ZONA ESCOLAR y el círculo de VELOCIDAD 60.

### `PrediccionSenal`

Salida del clasificador para el contexto del fotograma (sin caja: el clasificador no conoce la región).

| Campo | Tipo | Descripción |
|---|---|---|
| `clase` | `str` | etiqueta del modelo (`PARE`, `SIGA`, `ZONA ESCOLAR`, `VELOCIDAD 60`) |
| `confianza` | `float` | probabilidad top-1 en [0, 1] |
| `probabilidades` | `dict[str, float]` | distribución completa |
| `clase_senal` | `ClaseSenal \| None` | PARE/SIGA si aplica |
| `clase_extra` | `ClaseSenalExtra \| None` | ZONA/VELOCIDAD si aplica |

Invariantes: `0 <= confianza <= 1`; exactamente uno de `clase_senal`/`clase_extra` es no nulo, o ambos nulos si la etiqueta no se reconoce.

### `ClasificacionCNN`

Une la predicción con la región que la originó; es lo que consume el visor y las métricas.

| Campo | Tipo | Descripción |
|---|---|---|
| `prediccion` | `PrediccionSenal` | salida del modelo |
| `caja_px` | `tuple[int, int, int, int]` | caja de la región en el fotograma |
| `centro_px` | `tuple[int, int]` | centroide de la región |

Solo se incluyen clasificaciones **aceptadas** (confianza ≥ umbral y, para PARE/SIGA, forma de octágono). Las rechazadas se cuentan aparte en métricas.

PARE/SIGA conservan el filtro de vértices de 001: `abs(n_vertices - vertices_objetivo) <= tolerancia_vertices` (7–9). Las clases extra no lo aplican.

### `CandidatoSenal` (extensión)

Se añade un campo opcional al final:

| Campo | Tipo | Default |
|---|---|---|
| `confianza_cnn` | `float \| None` | `None` |

No se modifica ningún campo existente; los tests de 001 siguen siendo válidos.

### `ResultadoProcesamiento` (extensión)

Se añaden campos opcionales al final:

| Campo | Tipo | Default |
|---|---|---|
| `clasificaciones_cnn` | `list[ClasificacionCNN]` | `[]` |
| `modo_marcha` | `ModoMarcha` | `ModoMarcha.SIGA` |

### `CadenciaMarcha`

Estado puro del planificador de envío.

| Campo | Tipo | Descripción |
|---|---|---|
| `_ultimo_avance_t` | `float \| None` | instante del último `w` |
| `_ultima_orden` | `ComandoMovimiento \| None` | último comando transmitido |

API:

```python
def debe_enviar(self, comando: ComandoMovimiento, modo: ModoMarcha, t_s: float) -> bool
def reiniciar(self) -> None
```

Reglas:
- `DETENER` ⇒ `True` siempre y resetea `_ultimo_avance_t`.
- `IZQUIERDA`/`DERECHA` ⇒ `True` (el bucle aplica la cadencia de frames).
- `AVANZAR` ⇒ `True` si `_ultima_orden is not AVANZAR` o `t_s - _ultimo_avance_t >= intervalo(modo)`; en caso contrario `False`.
- Al enviar `AVANZAR`, actualiza `_ultimo_avance_t = t_s` y `_ultima_orden`.

## Configuración nueva

| Campo | Tipo | Default | Validación |
|---|---|---:|---|
| `rango_hsv_amarillo` | `RangoHSV` | H 20–35, S 100–255, V 80–255 | HSV válido; sin solape con rojo/verde |
| `clasificador_habilitado` | `bool` | `False` | — |
| `ruta_modelo_senales` | `str` | `assets/modelos/senales_mobilenet.onnx` | no vacío si habilitado |
| `ruta_metadatos_senales` | `str` | `assets/modelos/senales_mobilenet.json` | no vacío si habilitado |
| `umbral_confianza_senal` | `float` | `0.70` | `[0, 1]` |
| `area_minima_region_senal_rel` | `float` | `0.0005` | `(0, 1)` |
| `n_confirmacion_extra` | `int` | `3` | `>= 1` |
| `intervalo_siga_s` | `float` | `1.0` | `> 0` |
| `intervalo_zona_escolar_s` | `float` | `2.0` | `> 0` |
| `intervalo_velocidad_60_s` | `float` | `0.5` | `> 0` |

## Metadata del modelo (`senales_mobilenet.json`)

```json
{
  "modelo": "MobileNet",
  "archivo_origen": "modelos_guardados/MobileNet.keras",
  "archivo_onnx": "senales_mobilenet.onnx",
  "opset": 13,
  "tamano_entrada": [224, 224],
  "canal": "RGB",
  "preproceso": "mobilenet_tf",
  "escala": "[-1, 1]",
  "clases": {
    "0": "PARE",
    "1": "SIGA",
    "2": "ZONA ESCOLAR",
    "3": "VELOCIDAD 60"
  },
  "paridad_diferencia_maxima": 0.0,
  "paridad_aciertos": 12,
  "paridad_muestras": 12,
  "sha256": "..."
}
```

## Flujo de estados

```text
predicción CNN
   ├─ PARE/SIGA → CandidatoSenal → Detector → FSM
   └─ extra → confirmación (3) → ModoMarcha
FSM AUTORIZADO + ModoMarcha → CadenciaMarcha → ColaTransporte
FSM NO_AUTORIZADO → DETENER inmediato → ColaTransporte
```

## Persistencia

No hay base de datos. El estado vive en memoria durante la corrida. Las métricas se exportan a `salidas/<corrida_id>/metricas.json` y `eventos.jsonl`. El modelo y la metadata son archivos versionados en `assets/modelos/`.
