"""Smoke test opcional del modelo ONNX real (specs/004).

Se ejecuta cuando existen el artefacto y el dataset del proyecto de
entrenamiento. No usa TensorFlow: el modelo se carga con ONNX Runtime.
"""

from __future__ import annotations

import os
from pathlib import Path

import cv2
import pytest

from src.clasificacion.onnx import ClasificadorONNX

RAIZ = Path(__file__).resolve().parents[2]
MODELO = RAIZ / "assets" / "modelos" / "senales_mobilenet.onnx"
METADATOS = RAIZ / "assets" / "modelos" / "senales_mobilenet.json"
DATASET = Path(
    os.environ.get(
        "OPTIPILOT_CLASSIFIER_DATASET",
        RAIZ.parent / "optipilot_classifier" / "dataset",
    )
)

pytestmark = [
    pytest.mark.cnn,
    pytest.mark.skipif(
        not MODELO.is_file() or not METADATOS.is_file() or not DATASET.is_dir(),
        reason="modelo ONNX o dataset de entrenamiento no disponibles",
    ),
]

ESPERADOS = {
    "0": "PARE",
    "1": "SIGA",
    "2": "ZONA ESCOLAR",
    "3": "VELOCIDAD 60",
}


def test_clasifica_una_muestra_de_cada_clase() -> None:
    clasificador = ClasificadorONNX(MODELO, METADATOS)
    try:
        for carpeta, esperado in ESPERADOS.items():
            rutas = sorted((DATASET / carpeta).glob("*.jpg"))
            assert rutas, f"no hay imágenes en {DATASET / carpeta}"
            imagen = cv2.imread(str(rutas[0]))
            prediccion = clasificador.clasificar(imagen)
            assert prediccion.clase == esperado
            assert prediccion.confianza > 0.0
    finally:
        clasificador.cerrar()
