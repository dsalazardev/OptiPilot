"""Tests unitarios del estimador de posición de línea (T010–T012).

Verifican el Objetivo 3 del Reto 1: la posición lateral de la línea guía
respecto al objetivo configurado. Todas las máscaras son sintéticas, luego no
hacen falta cámara, vídeo ni robot (Principio V).

Grupos:
- posición con línea centrada y descentrada a ambos lados
- el error se mide contra ``x_objetivo``, no contra el centro fijo
- determinismo
- pérdida de confianza: borde, ruido y umbral
- selección entre varias líneas: la pista gruesa/continua gana a la trampa delgada
- invariantes del contrato Q1–Q7
- cumplimiento normativo: nada de Hough ni de ``cv2.fitLine`` (FR-003)
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from src.vision.configuracion import ParametrosConfiguracion
from src.vision.modelos import ResultadoSegmentacion
from src.vision.posicion_linea import EstimadorLinea

ANCHO = 478
ALTO = 850


def _segmentacion(mascara: np.ndarray, roi: tuple[int, int, int, int] | None = None) -> ResultadoSegmentacion:
    """Envuelve una máscara de línea en un ``ResultadoSegmentacion`` válido."""
    vacia = np.zeros_like(mascara)
    return ResultadoSegmentacion(
        mascara_linea=mascara,
        mascara_roja=vacia,
        mascara_verde=vacia,
        roi_linea=roi if roi is not None else (0, int(ALTO * 0.10), ANCHO, int(ALTO * 0.45)),
        roi_senales=(0, 0, ANCHO, 100),
    )


def _banda(centro_x: int, ancho_banda: int = 55, filas: int = 120) -> np.ndarray:
    """Máscara con una banda vertical de ``ancho_banda`` columnas centrada en ``centro_x``."""
    mascara = np.zeros((ALTO, ANCHO), dtype=np.uint8)
    inicio = int(ALTO * 0.10)
    y0 = inicio + max(0, (int(ALTO * 0.45) - filas) // 2)
    x0 = max(0, centro_x - ancho_banda // 2)
    x1 = min(ANCHO, x0 + ancho_banda)
    mascara[y0 : y0 + filas, x0:x1] = 1
    return mascara


def _estimador(**kw: object) -> EstimadorLinea:
    return EstimadorLinea(ParametrosConfiguracion(**kw))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Posición con línea válida
# ---------------------------------------------------------------------------


def test_linea_centrada_da_error_cerca_de_cero() -> None:
    pos = _estimador(x_objetivo=0.5).aplicar(_segmentacion(_banda(ANCHO // 2)))
    assert pos.valida
    assert pos.x_px == pytest.approx(ANCHO // 2, abs=2.0)
    assert pos.x_norm == pytest.approx(0.5, abs=0.01)
    assert pos.error_norm == pytest.approx(0.0, abs=0.02)
    assert pos.confianza > 0.35


def test_linea_a_la_derecha_da_error_positivo() -> None:
    """Signo de ``error_norm``: positivo = la línea está a la derecha del objetivo."""
    pos = _estimador(x_objetivo=0.5).aplicar(_segmentacion(_banda(360)))
    assert pos.valida
    assert pos.x_px == pytest.approx(360, abs=2.0)
    assert pos.error_norm > 0.0
    assert pos.x_norm == pytest.approx(pos.x_px / ANCHO, abs=1e-9)


def test_linea_a_la_izquierda_da_error_negativo() -> None:
    pos = _estimador(x_objetivo=0.5).aplicar(_segmentacion(_banda(110)))
    assert pos.valida
    assert pos.error_norm < 0.0


def test_error_se_mide_contra_x_objetivo_y_no_contra_el_centro() -> None:
    """FR-004: con ``x_objetivo`` descentrado, una línea centrada geométricamente da error."""
    mascara = _banda(ANCHO // 2)
    contra_centro = _estimador(x_objetivo=0.5).aplicar(_segmentacion(mascara))
    contra_objetivo = _estimador(x_objetivo=0.2).aplicar(_segmentacion(mascara))
    assert contra_centro.error_norm == pytest.approx(0.0, abs=0.02)
    assert contra_objetivo.error_norm == pytest.approx(0.3, abs=0.02)
    # La posición no cambia: lo que cambia es el objetivo contra el que se mide.
    assert contra_objetivo.x_px == pytest.approx(contra_centro.x_px, abs=1e-9)


def test_ancho_banda_refleja_la_grosura_de_la_linea() -> None:
    delgada = _estimador().aplicar(_segmentacion(_banda(240, ancho_banda=41)))
    gruesa = _estimador().aplicar(_segmentacion(_banda(240, ancho_banda=91)))
    assert delgada.valida and gruesa.valida
    assert gruesa.ancho_banda_px > delgada.ancho_banda_px
    assert delgada.ancho_banda_px >= 41


# ---------------------------------------------------------------------------
# Determinismo e invariantes del contrato
# ---------------------------------------------------------------------------


def test_es_determinista_ante_la_misma_entrada() -> None:
    """Q6/FR-008: sin azar, la misma máscara da el mismo resultado."""
    estimador = _estimador()
    mascara = _segmentacion(_banda(300))
    primero = estimador.aplicar(mascara)
    segundo = estimador.aplicar(mascara)
    assert primero == segundo


def test_la_normalizacion_no_depende_de_como_se_recorte_la_roi() -> None:
    """``x_norm`` se normaliza por el ancho del fotograma, no por el de la ROI.

    Es lo que hace que ``x_objetivo = 0.5`` equivalga al centro geométrico
    (239 px de 478 en el footage medido) y que el error conserve la misma
    escala aunque alguien ensanche o recorte la ROI.
    """
    roi = (100, 85, 278, 382)
    con_roi = _estimador().aplicar(_segmentacion(_banda(300), roi=roi))
    con_fotograma_completo = _estimador().aplicar(_segmentacion(_banda(300)))
    assert con_roi.x_px == pytest.approx(con_fotograma_completo.x_px, abs=1e-9)
    assert con_roi.x_norm == pytest.approx(con_fotograma_completo.x_norm, abs=1e-9)
    # Y el objetivo geométrico sigue siendo 0.5 con cualquiera de las dos ROIs.
    assert con_roi.error_norm == pytest.approx(con_roi.x_norm - 0.5, abs=1e-12)


def test_error_norm_es_siempre_la_diferencia_con_el_objetivo() -> None:
    """Q5: ``error_norm == x_norm - x_objetivo`` exacto, no aproximado."""
    for objetivo in (0.2, 0.35, 0.5, 0.75):
        pos = _estimador(x_objetivo=objetivo).aplicar(_segmentacion(_banda(280)))
        assert pos.valida
        assert pos.error_norm == pytest.approx(pos.x_norm - objetivo, abs=1e-12)


def test_x_px_y_x_norm_quedan_dentro_del_rango() -> None:
    """Q4."""
    for centro in (60, 240, 400):
        pos = _estimador().aplicar(_segmentacion(_banda(centro)))
        assert pos.valida
        assert 0 <= pos.x_px <= ANCHO
        assert 0.0 <= pos.x_norm <= 1.0


def test_la_fraccion_de_anticipacion_descarta_el_tramo_lejano() -> None:
    """``frac_anticipacion`` descarta la parte SUPERIOR de la ROI (la lejana).

    Es la franja que más se estrecha con la distancia y más ruido acumula; leer
    sólo el tramo cercano al robot es lo que permite corregir a tiempo. Se
    comprueba con las dos mitades por separado: una línea que vive en la franja
    lejana deja de contarse, y una que vive en la cercana se sigue leyendo igual.
    """
    inicio_roi = int(ALTO * 0.10)
    alto_roi = int(ALTO * 0.45)
    y_corte = inicio_roi + int(alto_roi * 0.40)

    lejana = np.zeros((ALTO, ANCHO), dtype=np.uint8)
    lejana[inicio_roi + 15 : y_corte - 15, 213:268] = 1
    cercana = np.zeros((ALTO, ANCHO), dtype=np.uint8)
    cercana[y_corte + 25 : y_corte + 145, 213:268] = 1

    # Con el default 0.40, la franja lejana está descartada y la cercana se lee.
    assert _estimador(frac_anticipacion=0.40).aplicar(_segmentacion(lejana)).valida is False
    pos_cercana = _estimador(frac_anticipacion=0.40).aplicar(_segmentacion(cercana))
    assert pos_cercana.valida
    assert pos_cercana.x_px == pytest.approx(240, abs=3.0)

    # Sin descartar nada, ambas se leen: es el parámetro, no el caso, la causa.
    assert _estimador(frac_anticipacion=0.0).aplicar(_segmentacion(lejana)).valida


def test_un_segundo_modo_en_la_franja_lejana_no_desplaza_a_la_pista() -> None:
    """Con la anticipación activa, la mancha lejana no debe contaminar la posición.

    Al descartarla, la línea se lee limpia. Sin descartarla hay dos candidatos y
    el estimador **elige uno** —el de mayor grosor × continuidad, la línea
    principal—, en vez de promediar entre modos, que inventaría una línea en
    medio que no existe (contrato §1).
    """
    mascara = _banda(240)
    inicio_roi = int(ALTO * 0.10)
    y_lejana = inicio_roi + int(ALTO * 0.45) // 8
    # Masa >= mitad del pico (60 de 120 filas) para que entre en el soporte.
    mascara[y_lejana : y_lejana + 60, 60:115] = 1

    con_anticipacion = _estimador(frac_anticipacion=0.40).aplicar(_segmentacion(mascara))
    sin_anticipacion = _estimador(frac_anticipacion=0.0).aplicar(_segmentacion(mascara))
    assert con_anticipacion.valida
    assert con_anticipacion.x_px == pytest.approx(240, abs=3.0)
    # Dos modos visibles: se elige la línea principal; nunca el punto medio.
    assert sin_anticipacion.valida
    assert sin_anticipacion.x_px == pytest.approx(240, abs=3.0)


# ---------------------------------------------------------------------------
# Pérdida de confianza: Q2, ambigüedad, borde
# ---------------------------------------------------------------------------


def test_mascara_vacia_es_invalida_y_no_lanza() -> None:
    """Q1/Q2: sin píxeles no hay posición, y no se inventa ninguna."""
    pos = _estimador().aplicar(_segmentacion(np.zeros((ALTO, ANCHO), dtype=np.uint8)))
    assert pos.valida is False
    assert pos.x_px is None
    assert pos.x_norm is None
    assert pos.error_norm is None
    assert pos.confianza == 0.0


def test_ruido_disperso_no_produce_una_posicion_valida() -> None:
    """Ruido sin pico dominante: confianza baja y posición inválida."""
    mascara = np.zeros((ALTO, ANCHO), dtype=np.uint8)
    filas = np.arange(int(ALTO * 0.10), int(ALTO * 0.10) + 120)
    rng = np.random.default_rng(7)
    mascara[filas, : int(ANCHO * 0.55)] = rng.integers(0, 2, size=(len(filas), int(ANCHO * 0.55)))
    pos = _estimador(frac_pico=0.99, umbral_confianza=0.9).aplicar(_segmentacion(mascara))
    assert pos.valida is False
    assert pos.x_px is None
    assert pos.confianza == 0.0


def test_dos_bandas_de_masa_comparable_se_elige_una_nunca_el_promedio() -> None:
    """Dos modos comparables: se elige uno por puntaje, jamás su promedio.

    El estimador no promedia entre modos (inventaría una línea en medio que no
    existe); selecciona el de mayor grosor × continuidad. Como los dos pesan
    parecido, su dominancia baja (~0.5) y un umbral de confianza alto la
    rechaza: esa es la vía para exigir una escena sin ambigüedad.
    """
    mascara = _banda(150, ancho_banda=61)
    y_lectura = int(ALTO * 0.10) + int(ALTO * 0.45) - 200
    mascara[y_lectura : y_lectura + 100, 320:380] = 1
    pos = _estimador().aplicar(_segmentacion(mascara))
    assert pos.valida
    # La posición es el centroide de uno de los dos tramos, no el punto medio.
    assert pos.x_px == pytest.approx(150, abs=3.0)
    # Con umbral alto, la dominancia ~0.5 no alcanza: sin ambigüedad o nada.
    exigente = _estimador(umbral_confianza=0.95).aplicar(_segmentacion(mascara))
    assert exigente.valida is False
    assert exigente.x_px is None


def test_linea_en_el_borde_de_la_roi_no_es_una_posicion_valida() -> None:
    """El pico pegado al borde se trata como pérdida, no como posición en el borde."""
    pos = _estimador().aplicar(_segmentacion(_banda(4, ancho_banda=40)))
    assert pos.valida is False
    assert pos.x_px is None


def test_umbral_de_confianza_es_efectivo() -> None:
    """``umbral_confianza`` gobierna la validez: ``valida`` ⟺ ``confianza >= umbral``.

    Se comprueba como invariante sobre todo el recorrido del parámetro, no con
    un caso puntual: si alguien invirtiera la comparación, o dejara el umbral sin
    efecto, el test falla.
    """
    mascara = _segmentacion(_banda(240))
    base = _estimador(umbral_confianza=0.0).aplicar(mascara)
    assert base.valida
    for umbral in (0.0, 0.25, 0.5, 0.75, 0.95, 1.0):
        pos = _estimador(umbral_confianza=umbral).aplicar(mascara)
        assert pos.valida == (base.confianza >= umbral), f"umbral={umbral}"
    # Si la confianza real no llega a 1.0, un umbral apenas superior la invalida.
    if base.confianza < 1.0:
        por_encima = _estimador(umbral_confianza=base.confianza + 0.01).aplicar(mascara)
        assert por_encima.valida is False
        assert por_encima.x_px is None


# ---------------------------------------------------------------------------
# Selección entre varias líneas: la pista gruesa gana a la trampa delgada
# ---------------------------------------------------------------------------


def _con_dos_bandas(primera: np.ndarray, segunda: np.ndarray) -> np.ndarray:
    return primera | segunda


def test_una_linea_trampa_delgada_no_desplaza_a_la_pista() -> None:
    """La trampa entra en el ROI y es más delgada: la posición no cambia.

    Ambas bandas son continuas y sus picos son iguales (la altura de la banda),
    que es el caso que confundía al estimador anterior: ``argmax`` devolvía la
    primera columna, así que una trampa delgada a la izquierda se llevaba la
    posición. Ahora el filtro de grosor la descarta.
    """
    pista = _banda(300, ancho_banda=55)
    trampa = _banda(120, ancho_banda=10)
    pos = _estimador().aplicar(_segmentacion(_con_dos_bandas(pista, trampa)))
    assert pos.valida
    assert pos.x_px == pytest.approx(300, abs=3.0)
    assert pos.ancho_banda_px >= 55


def test_solo_una_linea_trampa_delgada_no_da_posicion() -> None:
    """Si lo único visible es una línea más delgada que la pista, no hay dato."""
    pos = _estimador().aplicar(_segmentacion(_banda(120, ancho_banda=10)))
    assert pos.valida is False
    assert pos.x_px is None


def test_el_filtro_de_grosor_es_la_causa() -> None:
    """Con ``grosor_minimo_rel = 0`` la misma trampa delgada sí se lee."""
    pos = _estimador(grosor_minimo_rel=0.0).aplicar(_segmentacion(_banda(120, ancho_banda=10)))
    assert pos.valida
    assert pos.x_px == pytest.approx(120, abs=3.0)


def test_sin_memoria_gana_la_mas_gruesa() -> None:
    """Dos candidatas válidas y sin trayectoria previa: manda el grosor."""
    mascara = _con_dos_bandas(_banda(150, ancho_banda=55), _banda(360, ancho_banda=75))
    pos = _estimador().aplicar(_segmentacion(mascara))
    assert pos.valida
    assert pos.x_px == pytest.approx(360, abs=3.0)


def test_entre_dos_validas_prefiere_la_coherente_con_la_trayectoria() -> None:
    """Con memoria de la posición previa, no salta a una banda más gruesa lejana.

    Es la regla que pide el Reto ante una línea trampa que aparece en el ROI:
    mientras la pista siga cerca de donde estaba, se conserva la pista.
    """
    estimador = _estimador()
    estimador.aplicar(_segmentacion(_banda(150, ancho_banda=55)))  # memoria en 150
    mascara = _con_dos_bandas(_banda(150, ancho_banda=55), _banda(360, ancho_banda=75))
    pos = estimador.aplicar(_segmentacion(mascara))
    assert pos.valida
    assert pos.x_px == pytest.approx(150, abs=3.0)


def test_una_trampa_que_pasa_el_grosor_no_gana_solo_por_estar_mas_cerca() -> None:
    """La memoria no resucita una candidata claramente peor.

    La trampa de 20 px supera el filtro de grosor y está pegada a la memoria,
    pero su puntaje es menos de la mitad del de la pista (55 px): no compite.
    """
    estimador = _estimador()
    estimador.aplicar(_segmentacion(_banda(120, ancho_banda=55)))  # memoria en 120
    mascara = _con_dos_bandas(_banda(300, ancho_banda=55), _banda(120, ancho_banda=20))
    pos = estimador.aplicar(_segmentacion(mascara))
    assert pos.valida
    assert pos.x_px == pytest.approx(300, abs=3.0)


def test_reiniciar_olvida_la_trayectoria() -> None:
    """Entre corridas la memoria no sobrevive: vuelve a decidir el puntaje."""
    estimador = _estimador()
    estimador.aplicar(_segmentacion(_banda(150, ancho_banda=55)))
    estimador.reiniciar()
    mascara = _con_dos_bandas(_banda(150, ancho_banda=55), _banda(360, ancho_banda=75))
    pos = estimador.aplicar(_segmentacion(mascara))
    assert pos.x_px == pytest.approx(360, abs=3.0)


# ---------------------------------------------------------------------------
# T012 — cumplimiento normativo (FR-003, Principio I)
# ---------------------------------------------------------------------------

PROHIBIDAS = ("HoughLinesP", "HoughLines", "HoughCircles", "fitLine", "goodFeaturesToTrack", "createCLAHE")


def test_el_estimador_no_usa_tecnicas_prohibidas() -> None:
    """El Reto 1 prohíbe la detección automática de la línea sin lógica propia.

    Hough y ``fitLine`` resuelven la línea por sí solos, que es exactamente lo
    que el enunciado prohíbe. La regresión se comprueba sobre el **árbol
    sintáctico** y no sobre el texto: un ``grep`` daría un falso positivo con
    cualquier docstring que mencione lo prohibido para explicar que no se usa
    (que es justo lo que hace este archivo). ``ast`` sólo ve identificadores y
    atributos realmente ejecutados.
    """
    ruta = Path(__file__).resolve().parents[2] / "src" / "vision" / "posicion_linea.py"
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    usados: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Name):
            usados.add(nodo.id)
        elif isinstance(nodo, ast.Attribute):
            usados.add(nodo.attr)
    for simbolo in PROHIBIDAS:
        assert simbolo not in usados, f"{simbolo} está prohibido (FR-003)"
    # La técnica autorizada es aritmética sobre la máscara binaria: ni siquiera
    # hace falta OpenCV en este módulo.
    assert "cv2" not in usados
