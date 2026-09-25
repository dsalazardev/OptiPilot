"""Tests unitarios de candidatos de señal (T015).

Validan la extracción de contornos y la validación de forma sobre fixtures
sintéticas: octágonos válidos de ambas clases, objetos rojos/verdes no
octogonales descartados con motivo, área mínima que descarta regiones pequeñas
y aspecto fuera de rango con ``motivo_invalidez`` (FR-008/009/010).
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from src.vision.candidatos import ExtractorCandidatos
from src.vision.modelos import ClaseSenal
from src.vision.preprocesamiento import Preprocesador
from src.vision.segmentacion import Segmentador
from tests.fixtures.generador_sintetico import (
    ROJO_BGR,
    crear_fondo,
    fotograma_con_senal,
    fotograma_vacio,
    puntos_octagono,
)


@pytest.fixture()
def segmentar(parametros_por_defecto):
    """Pipeline preprocesamiento→segmentación ya encadenado."""
    preparador = Preprocesador(parametros_por_defecto)
    segmentador = Segmentador(parametros_por_defecto)

    def _segmentar(imagen_bgr: np.ndarray):
        return segmentador.aplicar(preparador.aplicar(imagen_bgr))

    return _segmentar


@pytest.fixture()
def extraer(parametros_por_defecto):
    """Extractor de candidatos con la configuración del contrato."""
    extractor = ExtractorCandidatos(parametros_por_defecto)

    def _extraer(resultado_segmentacion):
        return extractor.extraer(
            mascara_roja=resultado_segmentacion.mascara_roja,
            mascara_verde=resultado_segmentacion.mascara_verde,
            roi_senales_px=resultado_segmentacion.roi_senales,
        )

    return _extraer


def _octagono_aplastado(centro=(320, 140), radio=45, escala_x=1.5) -> np.ndarray:
    """Octágono regular estirado en X (relación de aspecto fuera de rango)."""
    vertices = puntos_octagono(centro, radio)
    verts_alargados = vertices.copy()
    verts_alargados[:, 0] = centro[0] + (vertices[:, 0] - centro[0]) * escala_x
    return verts_alargados


# ---------------------------------------------------------------------------
# T015 — Candidatos válidos (US1)
# ---------------------------------------------------------------------------


def test_octagono_pare_genera_candidato_valido(segmentar, extraer) -> None:
    candidatos = extraer(segmentar(fotograma_con_senal("PARE")))
    assert len(candidatos) == 1
    candidato = candidatos[0]
    assert candidato.clase_estimada == ClaseSenal.PARE
    assert candidato.es_valido is True
    assert candidato.motivo_invalidez is None
    assert 7 <= candidato.n_vertices <= 9
    assert 0.70 <= candidato.aspecto <= 1.40
    assert candidato.area_rel >= 0.001
    assert candidato.area_px > 0
    x, y, w, h = candidato.caja_px
    assert w > 0 and h > 0
    cx, cy = candidato.centro_px
    assert 280 <= cx <= 360
    assert 100 <= cy <= 180


def test_octagono_siga_genera_candidato_valido(segmentar, extraer) -> None:
    candidatos = extraer(segmentar(fotograma_con_senal("SIGA")))
    assert len(candidatos) == 1
    candidato = candidatos[0]
    assert candidato.clase_estimada == ClaseSenal.SIGA
    assert candidato.es_valido is True
    assert candidato.motivo_invalidez is None
    assert 7 <= candidato.n_vertices <= 9
    assert 0.70 <= candidato.aspecto <= 1.40


def test_escena_sin_senales_no_genera_candidatos(segmentar, extraer) -> None:
    candidatos = extraer(segmentar(fotograma_vacio()))
    assert candidatos == []


def test_no_se_confunde_la_mascara_de_origen(segmentar, extraer) -> None:
    pare = extraer(segmentar(fotograma_con_senal("PARE")))
    siga = extraer(segmentar(fotograma_con_senal("SIGA")))
    assert all(c.clase_estimada == ClaseSenal.PARE for c in pare)
    assert all(c.clase_estimada == ClaseSenal.SIGA for c in siga)


# ---------------------------------------------------------------------------
# T015 — Objetos no octogonales descartados
# ---------------------------------------------------------------------------


def test_cuadrado_rojo_es_candidato_invalido_por_vertices(segmentar, extraer) -> None:
    imagen = crear_fondo()
    cv2.rectangle(imagen, (275, 95), (365, 185), ROJO_BGR, thickness=-1)
    candidatos = extraer(segmentar(imagen))
    assert len(candidatos) == 1
    candidato = candidatos[0]
    assert candidato.es_valido is False
    assert candidato.motivo_invalidez is not None
    assert "vertices" in candidato.motivo_invalidez


def test_octagono_aplastado_invalido_por_aspecto(segmentar, extraer) -> None:
    imagen = crear_fondo()
    cv2.fillPoly(imagen, [_octagono_aplastado()], ROJO_BGR)
    candidatos = extraer(segmentar(imagen))
    assert len(candidatos) == 1
    candidato = candidatos[0]
    assert candidato.es_valido is False
    assert candidato.motivo_invalidez is not None
    assert "aspecto" in candidato.motivo_invalidez


# ---------------------------------------------------------------------------
# T015 — Área mínima y aspectos de borde
# ---------------------------------------------------------------------------


def test_octagono_diminuto_se_descarta_por_area(segmentar, extraer) -> None:
    candidatos = extraer(segmentar(fotograma_con_senal("PARE", radio=5.0)))
    assert candidatos == []