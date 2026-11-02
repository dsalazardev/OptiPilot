# Quickstart: Clasificador CNN de Señales

**Feature**: `004-clasificador-senales-cnn`

## 1. Exportar el modelo (entrenamiento, Python 3.13)

```powershell
cd "D:\Universidad de Caldas\Noveno semestre\Vision Artificial En Tiempo Real\optipilot_classifier"
python -m pip install tf2onnx onnx onnxruntime
python exportar_onnx.py
```

Salidas:
- `modelos_guardados/senales_mobilenet.onnx`
- `modelos_guardados/senales_mobilenet.json`

Criterio de aceptación: `max|Δ| < 1e-4` y top-1 `12/12`.

## 2. Copiar el artefacto a OptiPilot

```powershell
Copy-Item "..\optipilot_classifier\modelos_guardados\senales_mobilenet.onnx" "assets\modelos\"
Copy-Item "..\optipilot_classifier\modelos_guardados\senales_mobilenet.json" "assets\modelos\"
```

## 3. Sincronizar el runtime

```powershell
cd "D:\Universidad de Caldas\Noveno semestre\Vision Artificial En Tiempo Real\OptiPilot"
uv sync
uv run python -c "import onnxruntime; print(onnxruntime.__version__)"
```

## 4. Smoke test del clasificador

```powershell
uv run python -m src.main --fuente videos\rutaIdeal\video1.mp4 --clasificador onnx --max-fotogramas 30 --diagnostico
```

Verificar:
- no hay excepciones al cargar el modelo;
- el visor/diagnóstico muestra las etiquetas CNN;
- `metricas.json` incluye `clasificaciones_cnn`.

## 5. Pruebas

```powershell
uv run pytest -q
uv run pytest tests/unit/test_cadencia_marcha.py -q
uv run pytest tests/integration/test_clasificador_cnn.py -q
uv run pytest -m cnn -q
```

## 6. Corrida con el robot

```powershell
uv run python -m src.main --fuente http://IP:4747/video --transporte spp --mostrar --clasificador onnx
```

Cadencia esperada:
- PARE: `x` y 3.0 s de espera.
- SIGA: `w` cada 1.0 s.
- ZONA ESCOLAR: `w` cada 2.0 s.
- VELOCIDAD 60: `w` cada 0.5 s.

## 7. Solución de problemas

| Síntoma | Causa probable | Acción |
|---|---|---|
| `No module named onnxruntime` | Venv sin sincronizar | `uv sync` |
| `No se encontró el modelo` | Ruta incorrecta | Revisar `--modelo-senales` |
| Todas las predicciones son `SIGA` | Dominio distinto | Grabar footage del robot y reentrenar; revisar umbral |
| No se detectan señales amarillas | Rango HSV mal calibrado | Ajustar `rango_hsv_amarillo` |
| El robot no cambia de velocidad | Firmware mantiene movimiento continuo | Validar el supuesto en pista; no es un bug del software |
