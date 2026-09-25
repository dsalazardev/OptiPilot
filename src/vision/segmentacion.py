"""Segmentación por color: máscaras binarias de línea y señales (T010).

Técnica autorizada (Reto 1 · Constitución §I–§II):
- umbralización HSV con ``cv2.inRange`` → «Umbralización» y «Segmentación por
  color»;
- apertura y cierre con ``cv2.morphologyEx`` → «Operaciones morfológicas
  (apertura y cierre)».

Las máscaras se entregan a TAMAÑO COMPLETO del fotograma (contrato
``ResultadoSegmentacion``, valores {0,1}); la umbralización y la morfología se
aplican sobre las regiones recortadas (menos píxeles ⇒ más barato) y el
resultado se inserta en la máscara completa con rebanado numpy (vectorizado).
El rojo se segmenta como UNIÓN de sus dos rangos de tono (wrap 0–10 y 170–179).

Un fotograma sin línea o sin señales produce máscaras vacías sin excepción
(FR-014); ``linea_detectada`` reporta «no detectado» a partir de la máscara.
"""

from __future__ import annotations

import numpy as np
import cv2

from .configuracion import ParametrosConfiguracion, RangoHSV
from .modelos import ResultadoSegmentacion
from .preprocesamiento import ResultadoPreprocesamiento

__all__ = [
    "Segmentador",
    "linea_detectada",
]


def linea_detectada(mascara_linea: np.ndarray) -> bool:
    """True si la máscara de línea contiene píxeles activos («no detectado» = vacía)."""
    return bool(np.count_nonzero(mascara_linea) > 0)


def _kernel_morfologico(params: ParametrosConfiguracion) -> np.ndarray:
    k = params.kernel_morfologico_px
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))


def _mascarar_hsv(hsv: np.ndarray, rango: RangoHSV) -> np.ndarray:
    """Umbraliza por color: máscara {0,255} del rango HSV dado."""
    inferior, superior = rango.limites()
    return cv2.inRange(hsv, np.array(inferior, dtype=np.uint8), np.array(superior, dtype=np.uint8))


def _abrir_cerrar(mascara: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Apertura (quita ruido) seguida de cierre (cierra huecos) en la mascara."""
    abierta = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, kernel)
    return cv2.morphologyEx(abierta, cv2.MORPH_CLOSE, kernel)


def _insertar_en_completa(
    mascara_roi: np.ndarray, roi_px: tuple[int, int, int, int], alto: int, ancho: int
) -> np.ndarray:
    """Coloca una máscara de ROI dentro de una máscara completa {0,1} del fotograma.

    Si la región es vacía (fotograma vacío/canal inválido) devuelve máscara
    completa vacía sin excepción (FR-014).
    """
    completa = np.zeros((alto, ancho), dtype=np.uint8)
    x, y, w, h = roi_px
    if w > 0 and h > 0 and mascara_roi.size > 0:
        sub = mascara_roi[:h, :w]
        completa[y : y + sub.shape[0], x : x + sub.shape[1]] = (sub > 0).astype(np.uint8)
    return completa


class Segmentador:
    """Segunda etapa del pipeline: regiones HSV → máscaras binarias (T010)."""

    def __init__(self, params: ParametrosConfiguracion) -> None:
        self._params = params
        self._kernel = _kernel_morfologico(params)

    def mascara_linea(self, hsv_linea: np.ndarray) -> np.ndarray:
        """Máscara de la línea guía sobre la ROI de línea."""
        return _abrir_cerrar(_mascarar_hsv(hsv_linea, self._params.rango_hsv_linea), self._kernel)

    def mascara_roja(self, hsv_senales: np.ndarray) -> np.ndarray:
        """Máscara roja en la ROI de señales (unión de los dos rangos de tono)."""
        union = None
        for rango in self._params.rangos_hsv_rojo:
            parcial = _mascarar_hsv(hsv_senales, rango)
            union = parcial if union is None else cv2.bitwise_or(union, parcial)
        return _abrir_cerrar(union, self._kernel)

    def mascara_verde(self, hsv_senales: np.ndarray) -> np.ndarray:
        """Máscara verde en la ROI de señales."""
        return _abrir_cerrar(_mascarar_hsv(hsv_senales, self._params.rango_hsv_verde), self._kernel)

    def aplicar(self, pre: ResultadoPreprocesamiento) -> ResultadoSegmentacion:
        """Máscaras completas (línea, roja, verde) a tamaño del fotograma."""
        return ResultadoSegmentacion(
            mascara_linea=_insertar_en_completa(
                self.mascara_linea(pre.hsv_linea), pre.roi_linea_px, pre.alto, pre.ancho
            ),
            mascara_roja=_insertar_en_completa(
                self.mascara_roja(pre.hsv_senales), pre.roi_senales_px, pre.alto, pre.ancho
            ),
            mascara_verde=_insertar_en_completa(
                self.mascara_verde(pre.hsv_senales), pre.roi_senales_px, pre.alto, pre.ancho
            ),
            roi_linea=pre.roi_linea_px,
            roi_senales=pre.roi_senales_px,
        )