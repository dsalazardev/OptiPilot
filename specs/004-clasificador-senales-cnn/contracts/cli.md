# Contrato: CLI de OptiPilot con clasificador

**Feature**: `004-clasificador-senales-cnn` | **Date**: 2026-11-02

## 1. Flags nuevos

| Flag | Valores | Default | Descripción |
|---|---|---|---|
| `--clasificador` | `off`, `onnx` | `off` | Activa la clasificación CNN de señales |
| `--modelo-senales` | ruta | `assets/modelos/senales_mobilenet.onnx` | Modelo ONNX |
| `--metadatos-senales` | ruta | `assets/modelos/senales_mobilenet.json` | Metadata del modelo |

Los flags existentes (`--fuente`, `--config`, `--diagnostico`, `--mostrar`, `--salida`, `--max-fotogramas`, `--anotacion`, `--transporte`, `--rotar`) no cambian.

## 2. Comandos

```powershell
# Camino clásico actual (sin CNN)
uv run python -m src.main --fuente http://192.168.1.10:4747/video --transporte spp --mostrar

# Con CNN (ONNX) y robot real
uv run python -m src.main --fuente http://192.168.1.10:4747/video --transporte spp --mostrar --clasificador onnx

# Validación con video y diagnóstico
uv run python -m src.main --fuente videos/rutaIdeal/video1.mp4 --clasificador onnx --diagnostico

# Simulación sin hardware
uv run python -m src.main --fuente videos/rutaIdeal/video1.mp4 --clasificador onnx --transporte simulado
```

## 3. Códigos de salida

| Código | Significado |
|---:|---|
| 0 | Corrida completada |
| 2 | Configuración inválida, fuente inválida o modelo/clasificador no disponible |
| 3 | Error de transporte no recuperable (comportamiento existente) |

## 4. Comportamiento

- `--clasificador off`: no se importa `onnxruntime`, no se lee el modelo y el pipeline es idéntico al actual.
- `--clasificador onnx`: el modelo y la metadata deben existir y validar; si no, se aborta antes de abrir la fuente.
- El modelo se carga una vez al inicio de la corrida.
- La cámara y el transporte siguen siendo responsabilidad de `main.py`; `src/vision/` no abre archivos ni sockets.
- `--mostrar` dibuja la etiqueta CNN y el modo de marcha; `--diagnostico` guarda los fotogramas anotados.

## 5. Tests

```powershell
uv run pytest -q                       # suite completa, clasificador off por defecto
uv run pytest tests/unit -q
uv run pytest tests/integration -q
uv run pytest -m cnn                   # smoke test opcional con el modelo real
```
