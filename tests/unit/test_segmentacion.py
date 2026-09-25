"""Tests unitarios de segmentación (T014) y escenarios de línea (T017).

Validan las máscaras binarias sobre fixtures sintéticas: el rojo se detecta en
su ROI de señales con los dos rangos de tono, el verde en el suyo, el ruido es
suprimido por la morfología y la ausencia de línea/señales produce máscaras
vacías y «no detectado» sin excepción (FR-014).
"""

from __future__ import annotations

import numpy as np
import pytest

from src.vision.preprocesamiento import Preprocesador
from src.vision.segmentacion import Segmentador, linea_detectada
from tests.fixtures.generador_sintetico import (
    ALTO_POR_DEFECTO,
    ANCHO_POR_DEFECTO,
    LINEA_BGR,
    aplicar_ruido,
    crear_fondo,
    dibujar_linea_vertical,
    fotograma_con_linea,
    fotograma_con_senal,
    fotograma_vacio,
)


@pytest.fixture()
def segmentar(parametros_por_defecto):
    """Pipeline preprocesamiento→segmentación ya encadenado."""
    preparador = Preprocesador(parametros_por_defecto)
    segmentador_adapter = Segmentador(parametros_por_defecto)

    def _segmentar(imagen_bgr: np.ndarray):
        return segmentador_adapter.aplicar(preparador.aplicar(imagen_bgr))

    return _segmentar


def _densidad(mascara: np.ndarray) -> int:
    return int(np.count_nonzero(mascara))


def _dentro(rect: tuple[int, int, int, int], mascara: np.ndarray) -> bool:
    """True si todos los píxeles activos caen dentro del rect (x, y, w, h)."""
    if _densidad(mascara) == 0:
        return True
    ys, xs = np.nonzero(mascara)
    x, y, w, h = rect
    return bool(
        np.all(xs >= x)
        and np.all(xs < x + w)
        and np.all(ys >= y)
        and np.all(ys < y + h)
    )


# ---------------------------------------------------------------------------
# T014 — Máscaras de señales (US1)
# ---------------------------------------------------------------------------


def test_mascara_roja_detecta_octagono_pare(segmentar) -> None:
    resultado = segmentar(fotograma_con_senal("PARE"))
    assert _densidad(resultado.mascara_roja) >= 4000
    assert _densidad(resultado.mascara_verde) == 0
    assert _dentro(resultado.roi_senales, resultado.mascara_roja)


def test_mascara_verde_detecta_octagono_siga(segmentar) -> None:
    resultado = segmentar(fotograma_con_senal("SIGA"))
    assert _densidad(resultado.mascara_verde) >= 4000
    assert _densidad(resultado.mascara_roja) == 0
    assert _dentro(resultado.roi_senales, resultado.mascara_verde)


def test_no_hay_confusion_entre_mascaras_roja_y_verde(segmentar) -> None:
    pare = segmentar(fotograma_con_senal("PARE"))
    siga = segmentar(fotograma_con_senal("SIGA"))
    assert _densidad(pare.mascara_verde) == 0
    assert _densidad(siga.mascara_roja) == 0


def test_mascaras_no_salen_de_la_roi_de_senales(segmentar) -> None:
    for clase in ("PARE", "SIGA"):
        resultado = segmentar(fotograma_con_senal(clase))
        assert _dentro(resultado.roi_senales, resultado.mascara_roja)
        assert _dentro(resultado.roi_senales, resultado.mascara_verde)


def test_escena_sin_senales_produce_mascaras_vacias(segmentar) -> None:
    resultado = segmentar(fotograma_vacio())
    assert _densidad(resultado.mascara_roja) == 0
    assert _densidad(resultado.mascara_verde) == 0


def test_ruido_aislado_suprimido_por_morfologia(segmentar) -> None:
    resultado = segmentar(fotograma_vacio(ruido_sigma=10.0, semilla=7))
    assert _densidad(resultado.mascara_roja) == 0
    assert _densidad(resultado.mascara_verde) == 0


def test_senal_con_ruido_sigue_detectada(segmentar) -> None:
    for clase in ("PARE", "SIGA"):
        resultado = segmentar(fotograma_con_senal(clase, ruido_sigma=10.0, semilla=7))
        mascara = resultado.mascara_roja if clase == "PARE" else resultado.mascara_verde
        assert _densidad(mascara) >= 4000


# ---------------------------------------------------------------------------
# T017 — Escenarios de la línea guía (US3)
# ---------------------------------------------------------------------------


def test_mascara_linea_aisla_linea_sintetica(segmentar) -> None:
    resultado = segmentar(fotograma_con_linea())
    assert _densidad(resultado.mascara_linea) >= 4000
    assert _dentro(resultado.roi_linea, resultado.mascara_linea)
    ys, xs = np.nonzero(resultado.mascara_linea)
    assert xs.mean() < 340.0, "la máscara debe concentrarse cerca del centro de la línea"


def test_sin_linea_mascara_vacia_y_no_detectado(segmentar) -> None:
    resultado = segmentar(fotograma_vacio())
    assert _densidad(resultado.mascara_linea) == 0
    assert not linea_detectada(resultado.mascara_linea)


def test_ruido_no_rompe_la_mascara_de_linea(segmentar) -> None:
    resultado = segmentar(fotograma_con_linea(ruido_sigma=10.0, semilla=11))
    assert _densidad(resultado.mascara_linea) >= 4000
    assert linea_detectada(resultado.mascara_linea)


def test_sombra_en_la_roi_no_elimina_la_linea(segmentar) -> None:
    """Una sombra (banda oscura) a un lado no impide aislar la línea central."""
    alto, ancho = ALTO_POR_DEFECTO, ANCHO_POR_DEFECTO
    imagen = crear_fondo(alto, ancho)
    # Sombra: banda oscura gris (V bajo, segmentable como «oscura») izquierda.
    imagen[240:480, 120:200] = (60, 60, 60)
    dibujar_linea_vertical(imagen, x_centro=320, grosor=24, color_bgr=LINEA_BGR)
    resultado = segmentar(aplicar_ruido(imagen, sigma=10.0, semilla=13))

    ys, xs = np.nonzero(resultado.mascara_linea)
    if xs.size == 0:
        pytest.fail("la línea central desapareció con sombra + ruido")
    centrales = (xs >= 300) & (xs < 340)
    assert int(np.count_nonzero(centrales)) >= 3500, "la línea central debe sobrevivir la sombra"
