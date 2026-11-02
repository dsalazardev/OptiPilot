"""Integración del clasificador CNN opcional con el pipeline (specs/004)."""

from __future__ import annotations

import cv2
import numpy as np

from src.vision.configuracion import ParametrosConfiguracion
from src.vision.modelos import (
    ClaseSenal,
    ClaseSenalExtra,
    ModoMarcha,
    PrediccionSenal,
)
from src.vision.pipeline import PipelineVision
from tests.fixtures.generador_sintetico import (
    ROJO_BGR,
    VERDE_BGR,
    crear_fondo,
    dibujar_octagono,
)

ALTO = 480
ANCHO = 640
CENTRO = (300, 140)
RADIO = 45.0
AMARILLO_BGR = (0, 220, 220)


class _ClasificadorFijo:
    def __init__(self, prediccion: PrediccionSenal) -> None:
        self._prediccion = prediccion
        self.llamadas = 0

    def clasificar(self, imagen_bgr: np.ndarray) -> PrediccionSenal:
        self.llamadas += 1
        return self._prediccion

    def cerrar(self) -> None:
        pass


def _pare(confianza: float = 0.95) -> PrediccionSenal:
    return PrediccionSenal(
        clase="PARE",
        confianza=confianza,
        probabilidades={"PARE": confianza, "SIGA": 1.0 - confianza},
        clase_senal=ClaseSenal.PARE,
    )


def _siga(confianza: float = 0.95) -> PrediccionSenal:
    return PrediccionSenal(
        clase="SIGA",
        confianza=confianza,
        probabilidades={"SIGA": confianza, "PARE": 1.0 - confianza},
        clase_senal=ClaseSenal.SIGA,
    )


def _zona() -> PrediccionSenal:
    return PrediccionSenal(
        clase="ZONA ESCOLAR",
        confianza=0.95,
        probabilidades={"ZONA ESCOLAR": 0.95},
        clase_extra=ClaseSenalExtra.ZONA_ESCOLAR,
    )


def _velocidad() -> PrediccionSenal:
    return PrediccionSenal(
        clase="VELOCIDAD 60",
        confianza=0.95,
        probabilidades={"VELOCIDAD 60": 0.95},
        clase_extra=ClaseSenalExtra.VELOCIDAD_60,
    )


def _octagono(color: tuple[int, int, int]) -> np.ndarray:
    imagen = crear_fondo(ALTO, ANCHO)
    dibujar_octagono(imagen, CENTRO, RADIO, color)
    return imagen


def _pentagono_amarillo() -> np.ndarray:
    imagen = crear_fondo(ALTO, ANCHO)
    angulos = np.linspace(0.0, 2.0 * np.pi, 5, endpoint=False) - np.pi / 2.0
    puntos = np.column_stack(
        [CENTRO[0] + RADIO * np.cos(angulos), CENTRO[1] + RADIO * np.sin(angulos)]
    ).astype(np.int32)
    cv2.fillPoly(imagen, [puntos], AMARILLO_BGR)
    return imagen


def _velocidad_60() -> np.ndarray:
    imagen = crear_fondo(ALTO, ANCHO)
    cv2.circle(imagen, CENTRO, int(RADIO), (255, 255, 255), -1)
    cv2.circle(imagen, CENTRO, int(RADIO), (0, 0, 220), 8)
    return imagen


def _procesar(clasificador, imagen, fotogramas: int = 3):
    pipeline = PipelineVision(ParametrosConfiguracion.por_defecto(), clasificador)
    resultado = None
    for indice in range(fotogramas):
        resultado = pipeline.procesar(indice, indice / 30.0, imagen)
    assert resultado is not None
    return resultado


def test_pare_se_confirma_con_la_cnn() -> None:
    resultado = _procesar(_ClasificadorFijo(_pare()), _octagono(ROJO_BGR))
    assert [senal.clase for senal in resultado.senales_confirmadas] == [ClaseSenal.PARE]
    assert resultado.modo_marcha is ModoMarcha.SIGA
    assert resultado.clasificaciones_cnn[0].prediccion.clase == "PARE"


def test_siga_se_confirma_con_la_cnn() -> None:
    resultado = _procesar(_ClasificadorFijo(_siga()), _octagono(VERDE_BGR))
    assert [senal.clase for senal in resultado.senales_confirmadas] == [ClaseSenal.SIGA]
    assert resultado.modo_marcha is ModoMarcha.SIGA


def test_zona_escolar_cambia_el_modo_sin_tocar_la_fsm() -> None:
    resultado = _procesar(_ClasificadorFijo(_zona()), _pentagono_amarillo())
    assert resultado.senales_confirmadas == []
    assert resultado.modo_marcha is ModoMarcha.ZONA_ESCOLAR
    assert resultado.clasificaciones_cnn[0].prediccion.clase == "ZONA ESCOLAR"


def test_velocidad_60_cambia_el_modo_sin_tocar_la_fsm() -> None:
    resultado = _procesar(_ClasificadorFijo(_velocidad()), _velocidad_60())
    assert resultado.senales_confirmadas == []
    assert resultado.modo_marcha is ModoMarcha.VELOCIDAD_60


def test_confianza_baja_se_rechaza() -> None:
    clasificador = _ClasificadorFijo(_pare(0.40))
    resultado = _procesar(clasificador, _octagono(ROJO_BGR))
    assert resultado.senales_confirmadas == []
    assert resultado.clasificaciones_cnn == []
    assert resultado.rechazadas_cnn == 1


def test_una_mancha_verde_no_octagonal_no_es_siga() -> None:
    imagen = crear_fondo(ALTO, ANCHO)
    cv2.rectangle(imagen, (250, 100), (350, 190), VERDE_BGR, -1)
    clasificador = _ClasificadorFijo(_siga())
    resultado = _procesar(clasificador, imagen)
    assert resultado.senales_confirmadas == []
    assert resultado.clasificaciones_cnn == []
    assert resultado.rechazadas_cnn == 1


def test_sin_clasificador_el_camino_clasico_sigue_funcionando() -> None:
    pipeline = PipelineVision(ParametrosConfiguracion.por_defecto())
    imagen = _octagono(ROJO_BGR)
    resultado = None
    for indice in range(3):
        resultado = pipeline.procesar(indice, indice / 30.0, imagen)
    assert resultado is not None
    assert [senal.clase for senal in resultado.senales_confirmadas] == [ClaseSenal.PARE]
    assert resultado.clasificaciones_cnn == []
    assert resultado.rechazadas_cnn == 0
