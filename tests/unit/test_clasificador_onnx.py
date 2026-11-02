"""Tests unitarios del adaptador ONNX (specs/004)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from src.clasificacion.onnx import ClasificadorONNX
from src.vision.modelos import ClaseSenalExtra


class _Entrada:
    name = "imagen"


class _SesionFalsa:
    def __init__(self, salida: list[float]) -> None:
        self.salida = np.asarray([salida], dtype=np.float32)
        self.llamadas: list[dict] = []

    def get_inputs(self) -> list[_Entrada]:
        return [_Entrada()]

    def run(self, _salidas, entradas):
        self.llamadas.append(entradas)
        return [self.salida]


def _modelo(tmp_path: Path, salida: list[float], *, preproceso: str = "mobilenet_tf"):
    ruta_modelo = tmp_path / "modelo.onnx"
    ruta_modelo.write_bytes(b"modelo de prueba")
    metadatos = {
        "modelo": "MobileNet",
        "archivo_onnx": ruta_modelo.name,
        "opset": 13,
        "tamano_entrada": [224, 224],
        "canal": "RGB",
        "preproceso": preproceso,
        "escala": "[-1, 1]",
        "clases": {
            "0": "PARE",
            "1": "SIGA",
            "2": "ZONA ESCOLAR",
            "3": "VELOCIDAD 60",
        },
        "sha256": hashlib.sha256(ruta_modelo.read_bytes()).hexdigest(),
    }
    ruta_metadatos = tmp_path / "modelo.json"
    ruta_metadatos.write_text(json.dumps(metadatos), encoding="utf-8")
    sesion = _SesionFalsa(salida)
    clasificador = ClasificadorONNX(
        ruta_modelo, ruta_metadatos, fabrica_sesion=lambda _: sesion
    )
    return clasificador, sesion


def test_clasifica_y_mapea_zona_escolar(tmp_path: Path) -> None:
    clasificador, sesion = _modelo(tmp_path, [0.1, 0.2, 0.6, 0.1])
    imagen = np.zeros((40, 60, 3), dtype=np.uint8)

    prediccion = clasificador.clasificar(imagen)

    assert prediccion.clase == "ZONA ESCOLAR"
    assert prediccion.confianza == pytest.approx(0.6)
    assert prediccion.clase_extra is ClaseSenalExtra.ZONA_ESCOLAR
    assert prediccion.clase_senal is None
    assert prediccion.probabilidades["ZONA ESCOLAR"] == pytest.approx(0.6)
    lote = sesion.llamadas[0]["imagen"]
    assert lote.shape == (1, 224, 224, 3)
    assert float(lote.min()) == pytest.approx(-1.0)
    assert float(lote.max()) == pytest.approx(-1.0)


def test_imagen_invalida_no_llama_al_modelo(tmp_path: Path) -> None:
    clasificador, sesion = _modelo(tmp_path, [0.1, 0.2, 0.6, 0.1])
    prediccion = clasificador.clasificar(np.zeros((0, 0, 3), dtype=np.uint8))
    assert prediccion.clase == "DESCONOCIDA"
    assert prediccion.confianza == 0.0
    assert sesion.llamadas == []


def test_hash_incorrecto_falla_al_cargar(tmp_path: Path) -> None:
    clasificador, _ = _modelo(tmp_path, [0.1, 0.2, 0.6, 0.1])
    ruta_metadatos = tmp_path / "modelo.json"
    datos = json.loads(ruta_metadatos.read_text(encoding="utf-8"))
    datos["sha256"] = "0" * 64
    ruta_metadatos.write_text(json.dumps(datos), encoding="utf-8")

    with pytest.raises(ValueError, match="SHA-256"):
        ClasificadorONNX(
            tmp_path / "modelo.onnx",
            ruta_metadatos,
            fabrica_sesion=lambda _: None,
        )


def test_preproceso_desconocido_falla_al_cargar(tmp_path: Path) -> None:
    _, _ = _modelo(tmp_path, [0.1, 0.2, 0.6, 0.1])
    ruta_metadatos = tmp_path / "modelo.json"
    datos = json.loads(ruta_metadatos.read_text(encoding="utf-8"))
    datos["preproceso"] = "otro"
    ruta_metadatos.write_text(json.dumps(datos), encoding="utf-8")

    with pytest.raises(ValueError, match="preproceso"):
        ClasificadorONNX(
            tmp_path / "modelo.onnx",
            ruta_metadatos,
            fabrica_sesion=lambda _: None,
        )


def test_salida_sin_softmax_se_convierte_en_probabilidades(tmp_path: Path) -> None:
    clasificador, _ = _modelo(tmp_path, [1.0, 2.0, 3.0, 4.0])
    prediccion = clasificador.clasificar(np.zeros((10, 10, 3), dtype=np.uint8))
    assert prediccion.clase == "VELOCIDAD 60"
    assert 0.0 <= prediccion.confianza <= 1.0
    assert sum(prediccion.probabilidades.values()) == pytest.approx(1.0, abs=1e-5)


def test_cerrar_es_idempotente_y_bloquea_la_inferencia(tmp_path: Path) -> None:
    clasificador, _ = _modelo(tmp_path, [0.1, 0.2, 0.6, 0.1])
    clasificador.cerrar()
    clasificador.cerrar()
    assert clasificador.clasificar(np.zeros((10, 10, 3), dtype=np.uint8)).clase == "DESCONOCIDA"


def test_modelo_ausente_falla_al_cargar(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ClasificadorONNX(
            tmp_path / "no_existe.onnx",
            tmp_path / "no_existe.json",
            fabrica_sesion=lambda _: None,
        )
