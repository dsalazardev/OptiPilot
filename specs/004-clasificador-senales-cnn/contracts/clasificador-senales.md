# Contrato: Clasificador de señales (ONNX)

**Feature**: `004-clasificador-senales-cnn` | **Date**: 2026-11-02

## 1. Artefactos

| Artefacto | Ruta por defecto | Descripción |
|---|---|---|
| Modelo ONNX | `assets/modelos/senales_mobilenet.onnx` | MobileNet exportado desde `MobileNet.keras` |
| Metadata | `assets/modelos/senales_mobilenet.json` | Clases, tamaño, preproceso, hash y paridad |

El runtime no importa TensorFlow ni el proyecto `optipilot_classifier`. Solo consume estos dos archivos.

## 2. Metadata

El JSON MUST contener:

```json
{
  "modelo": "MobileNet",
  "archivo_onnx": "senales_mobilenet.onnx",
  "opset": 13,
  "tamano_entrada": [224, 224],
  "canal": "RGB",
  "preproceso": "mobilenet_tf",
  "escala": "[-1, 1]",
  "clases": {"0": "PARE", "1": "SIGA", "2": "ZONA ESCOLAR", "3": "VELOCIDAD 60"},
  "sha256": "...",
  "paridad_diferencia_maxima": 0.0,
  "paridad_aciertos": 12,
  "paridad_muestras": 12
}
```

`clases` mapea índice de salida → etiqueta. El runtime MUST rechazar el modelo si:
- falta el archivo o la metadata;
- el SHA-256 no coincide;
- el tamaño de entrada no es `[224, 224]`;
- el número de clases no coincide con la salida del modelo;
- `preproceso` no es `mobilenet_tf`.

## 3. Preprocesamiento

Para el contexto BGR del fotograma (la CNN solo se ejecuta si el localizador propone una región):

1. `cv2.cvtColor(contexto, cv2.COLOR_BGR2RGB)`
2. `cv2.resize(..., (224, 224), interpolation=cv2.INTER_AREA)`
3. `float32`
4. `x / 127.5 - 1.0` (rango `[-1, 1]`)
5. `np.expand_dims(x, axis=0)` (NHWC)

El orden y la escala MUST coincidir con `keras.applications.mobilenet.preprocess_input` usado en el entrenamiento.

## 4. Interfaz

```python
class ClasificadorSenales(Protocol):
    def clasificar(self, imagen_bgr: np.ndarray) -> PrediccionSenal: ...
    def cerrar(self) -> None: ...
```

`PrediccionSenal`:

```python
@dataclass(frozen=True)
class PrediccionSenal:
    clase: str
    confianza: float
    probabilidades: dict[str, float]
    clase_senal: ClaseSenal | None
    clase_extra: ClaseSenalExtra | None
```

El pipeline envuelve cada predicción aceptada en `ClasificacionCNN` con la caja y el centroide de la región; el clasificador no conoce ni devuelve coordenadas.

Reglas:
- `clasificar` MUST ser determinista para la misma imagen y modelo.
- `clasificar` MUST NOT lanzar por una imagen vacía o inválida: devuelve una predicción con `clase="DESCONOCIDA"`, `confianza=0.0`, `clase_senal=None`, `clase_extra=None`.
- La sesión ONNX se carga una sola vez en el constructor.
- `cerrar` MUST ser idempotente.

## 5. Mapeo de clases

| Etiqueta | Destino |
|---|---|
| `PARE` | `ClaseSenal.PARE` |
| `SIGA` | `ClaseSenal.SIGA` |
| `ZONA ESCOLAR` | `ClaseSenalExtra.ZONA_ESCOLAR` |
| `VELOCIDAD 60` | `ClaseSenalExtra.VELOCIDAD_60` |
| cualquier otra | ninguna; se descarta |

## 6. Umbral y confirmación

- Una predicción solo se considera si `confianza >= umbral_confianza_senal` (default 0.70).
- PARE/SIGA pasan al `Detector` existente con `n_confirmacion = 3`, `k_tolerancia = 2`, `x_rearme = 5`.
- ZONA/VELOCIDAD usan `n_confirmacion_extra = 3` y solo cambian el modo tras 3 predicciones consecutivas de la misma clase.
- Una predicción por debajo del umbral no cuenta para la confirmación.

## 7. Errores

| Condición | Comportamiento |
|---|---|
| `--clasificador onnx` y modelo ausente | Abortar con código 2 y mensaje claro |
| `--clasificador onnx` y ONNX Runtime ausente | Abortar con código 2 |
| Imagen vacía/ilegible | Predicción desconocida; no lanzar |
| Error interno de inferencia | Registrar y descartar la predicción; el bucle sigue |
| `--clasificador off` | No cargar ni importar ONNX; camino clásico intacto |

## 8. Rendimiento

- Objetivo: ≤ 15 ms por inferencia en el portátil de desarrollo.
- Si el bucle supera el presupuesto, se permite inferir cada N fotogramas; la confirmación temporal se cuenta sobre muestras de inferencia, no sobre fotogramas.
- La inferencia MUST ejecutarse en el hilo de visión; el transporte sigue desacoplado en su hilo.
