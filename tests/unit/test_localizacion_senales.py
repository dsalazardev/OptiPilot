"""Tests unitarios del localizador clásico de regiones de señal (specs/004)."""

from __future__ import annotations

import cv2
import numpy as np

from src.vision.configuracion import ParametrosConfiguracion
from src.vision.localizacion_senales import LocalizadorSenales
from src.vision.modelos import ColorRegion, RegionSenal
from src.vision.preprocesamiento import Preprocesador
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


def _localizador() -> LocalizadorSenales:
    return LocalizadorSenales(ParametrosConfiguracion.por_defecto())


def _propuestas(imagen: np.ndarray) -> list[RegionSenal]:
    params = ParametrosConfiguracion.por_defecto()
    pre = Preprocesador(params).aplicar(imagen)
    return _localizador().propuestas(pre)


def _pentagono(centro: tuple[int, int], radio: float) -> np.ndarray:
    angulos = np.linspace(0.0, 2.0 * np.pi, 5, endpoint=False) - np.pi / 2.0
    return np.column_stack(
        [
            centro[0] + radio * np.cos(angulos),
            centro[1] + radio * np.sin(angulos),
        ]
    ).astype(np.int32)


def test_pare_rojo_genera_una_region() -> None:
    imagen = crear_fondo(ALTO, ANCHO)
    dibujar_octagono(imagen, CENTRO, RADIO, ROJO_BGR)
    regiones = _propuestas(imagen)
    assert len(regiones) == 1
    assert regiones[0].area_px > 0
    assert regiones[0].n_vertices == 8
    assert regiones[0].color is ColorRegion.ROJO


def test_siga_verde_genera_una_region() -> None:
    imagen = crear_fondo(ALTO, ANCHO)
    dibujar_octagono(imagen, CENTRO, RADIO, VERDE_BGR)
    regiones = _propuestas(imagen)
    assert len(regiones) == 1
    assert regiones[0].n_vertices == 8
    assert regiones[0].color is ColorRegion.VERDE


def test_zona_escolar_amarilla_genera_una_region() -> None:
    imagen = crear_fondo(ALTO, ANCHO)
    cv2.fillPoly(imagen, [_pentagono(CENTRO, RADIO)], AMARILLO_BGR)
    regiones = _propuestas(imagen)
    assert len(regiones) == 1
    assert regiones[0].n_vertices == 5
    assert regiones[0].color is ColorRegion.AMARILLO


def test_velocidad_60_se_localiza_por_su_borde_rojo() -> None:
    imagen = crear_fondo(ALTO, ANCHO)
    cv2.circle(imagen, CENTRO, int(RADIO), (255, 255, 255), -1)
    cv2.circle(imagen, CENTRO, int(RADIO), (0, 0, 220), 8)
    regiones = _propuestas(imagen)
    assert len(regiones) == 1
    assert regiones[0].caja_px[2] >= 80
    assert regiones[0].color is ColorRegion.ROJO


def test_fondo_sin_senales_no_genera_propuestas() -> None:
    assert _propuestas(crear_fondo(ALTO, ANCHO)) == []


def test_una_senal_fuera_de_la_roi_no_se_propone() -> None:
    imagen = crear_fondo(ALTO, ANCHO)
    dibujar_octagono(imagen, (300, 380), RADIO, ROJO_BGR)
    assert _propuestas(imagen) == []


def test_una_region_muy_pequena_se_descarta() -> None:
    imagen = crear_fondo(ALTO, ANCHO)
    cv2.circle(imagen, CENTRO, 3, ROJO_BGR, -1)
    assert _propuestas(imagen) == []


def test_supresion_de_regiones_solapadas() -> None:
    grande = RegionSenal(
        caja_px=(100, 100, 80, 80),
        centro_px=(140, 140),
        area_px=6000,
        area_rel=0.04,
        n_vertices=8,
        aspecto=1.0,
    )
    pequena = RegionSenal(
        caja_px=(105, 105, 60, 60),
        centro_px=(135, 135),
        area_px=3000,
        area_rel=0.02,
        n_vertices=8,
        aspecto=1.0,
    )
    conservadas = LocalizadorSenales._suprimir_solapadas([pequena, grande])
    assert conservadas == [grande]


def test_dos_senales_separadas_se_conservan() -> None:
    imagen = crear_fondo(ALTO, ANCHO)
    dibujar_octagono(imagen, (180, 140), RADIO, ROJO_BGR)
    dibujar_octagono(imagen, (450, 140), RADIO, VERDE_BGR)
    regiones = _propuestas(imagen)
    assert len(regiones) == 2
