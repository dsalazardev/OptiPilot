"""Extracción y validación de candidatos de señal (T011).

Técnica autorizada (Reto 1 · Constitución §I–§II):
- ``cv2.findContours`` (contornos externos) con ``cv2.contourArea``,
  ``cv2.arcLength``, ``cv2.boundingRect`` y ``cv2.moments`` → «Detección y
  análisis de contornos» y sus «propiedades básicas» (área, perímetro,
  centroide, caja, relación de aspecto);
- ``cv2.approxPolyDP`` → «Identificación de formas geométricas simples»
  (Douglas–Peucker); la forma objetivo es el octágono (8 vértices).

Reglas (FR-008/009/010): se descartan regiones con ``area_rel`` por debajo de
``area_minima_rel`` (fracción del área de la ROI de señales); la tolerancia de
aproximación poligonal es ~3 % del perímetro (constante del módulo, dentro del
rango 2–4 % exigido); un candidato es válido si tiene 8±``tolerancia_vertices``
vértices y su relación de aspecto cae en [``aspecto_min``, ``aspecto_max``]. El
motivo del rechazo se conserva en ``motivo_invalidez`` para depuración y para
explicar cada etapa del algoritmo (rúbrica, criterios 5 y 9).
"""

from __future__ import annotations

from collections.abc import Iterable

import cv2
import numpy as np

from .configuracion import ParametrosConfiguracion
from .modelos import CandidatoSenal, ClaseSenal

__all__ = [
    "EPSILON_APROX",
    "ExtractorCandidatos",
]

# Tolerancia de ``approxPolyDP`` como fracción del perímetro del contorno.
# Dentro del rango 2–4 % documentado en T011; se fija en 3 % para colapsar los
# puntos colineales del octágono rasterizado (8 esquinas) sin desdibujarlo.
EPSILON_APROX = 0.03


def _area_roi(roi_senales_px: tuple[int, int, int, int]) -> int:
    """Área en píxeles de la ROI de señales (denominador de ``area_rel``)."""
    x, y, w, h = roi_senales_px
    return w * h


def _motivo_invalidez(
    n_vertices: int, aspecto: float, p: ParametrosConfiguracion
) -> str | None:
    """Motivo(s) de rechazo de un candidato, o None si cumple todas las reglas."""
    motivos: list[str] = []
    if abs(n_vertices - p.vertices_objetivo) > p.tolerancia_vertices:
        motivos.append(
            f"n_vertices={n_vertices} fuera de {p.vertices_objetivo}"
            f"±{p.tolerancia_vertices}"
        )
    if not (p.aspecto_min <= aspecto <= p.aspecto_max):
        motivos.append(f"aspecto={aspecto:.2f} fuera de [{p.aspecto_min}, {p.aspecto_max}]")
    return "; ".join(motivos) or None


def _centroide(contorno: np.ndarray, caja: tuple[int, int, int, int]) -> tuple[int, int]:
    """Centroide por momentos de primer orden; cae a la caja si no hay área."""
    momentos = cv2.moments(contorno)
    if momentos["m00"] > 0:
        cx = int(round(momentos["m10"] / momentos["m00"]))
        cy = int(round(momentos["m01"] / momentos["m00"]))
    else:
        cx, cy = caja[0] + caja[2] // 2, caja[1] + caja[3] // 2
    return cx, cy


class ExtractorCandidatos:
    """Tercera etapa del pipeline: máscaras → regiones candidatas (T011).

    Convierte las máscaras roja/verde de la segmentación en
    ``CandidatoSenal``. La clase se estima por la máscara de origen (roja →
    PARE, verde → SIGA); cada contorno externo se describe (centroide, área,
    caja, aspecto, número de vértices) y se valida contra las reglas de forma.
    """

    def __init__(self, params: ParametrosConfiguracion) -> None:
        self._params = params

    def extraer(
        self,
        mascara_roja: np.ndarray,
        mascara_verde: np.ndarray,
        roi_senales_px: tuple[int, int, int, int],
    ) -> list[CandidatoSenal]:
        """Candidatos de las máscaras binarias {0,1} a tamaño completo.

        Una máscara vacía o una ROI degenerada devuelven lista vacía sin
        excepción (FR-014): la ausencia de señales es un resultado normal.
        """
        area_roi = _area_roi(roi_senales_px)
        if area_roi <= 0:
            return []

        candidatos: list[CandidatoSenal] = []
        candidatos.extend(
            self._de_mascara(mascara=mascara_roja, clase=ClaseSenal.PARE, area_roi=area_roi)
        )
        candidatos.extend(
            self._de_mascara(mascara=mascara_verde, clase=ClaseSenal.SIGA, area_roi=area_roi)
        )
        return candidatos

    def _de_mascara(
        self,
        mascara: np.ndarray,
        clase: ClaseSenal,
        area_roi: int,
    ) -> Iterable[CandidatoSenal]:
        """Candidatos de una única máscara (clase fijada por la de origen)."""
        if mascara is None or mascara.ndim != 2 or mascara.size == 0:
            return ()

        contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contorno in contornos:
            area_px = cv2.contourArea(contorno)
            area_rel = area_px / area_roi
            if area_rel < self._params.area_minima_rel:
                # Descarte por área mínima (FR-008): no llega a ser candidato.
                continue

            caja = cv2.boundingRect(contorno)
            ancho, alto = caja[2], caja[3]
            if ancho <= 0 or alto <= 0:
                continue
            aspecto = ancho / alto

            perimetro = cv2.arcLength(contorno, True)
            aproximado = cv2.approxPolyDP(contorno, EPSILON_APROX * perimetro, True)
            n_vertices = len(aproximado)

            motivo = _motivo_invalidez(n_vertices, aspecto, self._params)
            yield CandidatoSenal(
                clase_estimada=clase,
                centro_px=_centroide(contorno, caja),
                area_px=int(round(area_px)),
                area_rel=area_rel,
                n_vertices=n_vertices,
                caja_px=caja,
                aspecto=aspecto,
                es_valido=motivo is None,
                motivo_invalidez=motivo,
            )