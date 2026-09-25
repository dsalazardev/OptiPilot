"""Preprocesamiento: suavizado, espacio de color y recorte de ROIs (T009).

Técnica autorizada (Reto 1 · Constitución §I–§II):
- suavizado Gaussiano  → «Suavizado y reducción de ruido»;
- conversión BGR→HSV    → «Conversión entre espacios de color (RGB, HSV)»;
- recorte de ROIs       → «Recorte de regiones de interés (ROI)» — estricto,
  sin exceder el marco y con al menos 1 px de alto/ancho.

El suavizado se aplica una sola vez sobre el fotograma completo (vectorizado en
OpenCV); después se convierte a HSV una única vez y se recortan las dos regiones
de interés (línea y señales) mediante rebanado numpy. Nada de ello delega la
decisión de detección (Principio I): solo prepara la imagen para la
segmentación por color (T010).
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .configuracion import ParametrosConfiguracion, RectanguloNormalizado

__all__ = [
    "KERNEL_SUAVIZADO",
    "Preprocesador",
    "ResultadoPreprocesamiento",
    "recorte_px",
]

# Kernel del suavizado Gaussiano. Tamaño pequeño y estándar para el filtro
# pasa-bajos; no está en el contrato de configuración (FR-024) y se documenta
# aquí como constante única del módulo (evita números mágicos dispersos).
KERNEL_SUAVIZADO = (5, 5)


@dataclass(frozen=True)
class ResultadoPreprocesamiento:
    """Regiones HSV recortadas y rectángulos efectivos (píxeles) por ROI.

    ``alto``/``ancho`` son las dimensiones del fotograma original, necesarias
    para reconstruir máscaras a tamaño completo en la segmentación.
    """

    hsv_linea: np.ndarray
    hsv_senales: np.ndarray
    roi_linea_px: tuple[int, int, int, int]
    roi_senales_px: tuple[int, int, int, int]
    alto: int
    ancho: int


def recorte_px(
    rect: RectanguloNormalizado, ancho: int, alto: int
) -> tuple[int, int, int, int]:
    """Convierte una ROI normalizada a píxeles con recorte estricto.

    El redondeo se reparte entre el origen y el extremo para no exceder el marco
    del fotograma y se garantiza al menos 1 px de alto y ancho cuando el
    fotograma no es vacío. Devuelve ``(x, y, w, h)``.
    """
    if ancho <= 0 or alto <= 0:
        return (0, 0, 0, 0)
    x = int(round(rect.x * ancho))
    y = int(round(rect.y * alto))
    x2 = int(round((rect.x + rect.w) * ancho))
    y2 = int(round((rect.y + rect.h) * alto))
    x = max(0, min(x, ancho - 1))
    y = max(0, min(y, alto - 1))
    x2 = max(x + 1, min(x2, ancho))
    y2 = max(y + 1, min(y2, alto))
    return (x, y, x2 - x, y2 - y)


class Preprocesador:
    """Primera etapa del pipeline: imagen BGR → regiones HSV recortadas (T009)."""

    def __init__(self, params: ParametrosConfiguracion) -> None:
        self._params = params

    def aplicar(self, imagen_bgr: np.ndarray) -> ResultadoPreprocesamiento:
        """Suaviza, convierte a HSV y recorta las ROIs de línea y señales.

        Un fotograma vacío, ilegible o de canales incorrectos devuelve regiones
        vacías sin excepción (FR-014): la degradación controlada continúa en el
        pipeline y la máquina de estados.
        """
        if imagen_bgr is None or imagen_bgr.ndim != 3 or imagen_bgr.shape[2] != 3:
            alto = 0 if imagen_bgr is None else imagen_bgr.shape[0]
            ancho = 0 if imagen_bgr is None else imagen_bgr.shape[1]
            vacio = np.zeros((0, 0, 3), dtype=np.uint8)
            return ResultadoPreprocesamiento(
                hsv_linea=vacio,
                hsv_senales=vacio,
                roi_linea_px=(0, 0, 0, 0),
                roi_senales_px=(0, 0, 0, 0),
                alto=alto,
                ancho=ancho,
            )

        alto, ancho = imagen_bgr.shape[0], imagen_bgr.shape[1]
        if alto == 0 or ancho == 0:
            vacio = np.zeros((0, 0, 3), dtype=np.uint8)
            return ResultadoPreprocesamiento(
                hsv_linea=vacio,
                hsv_senales=vacio,
                roi_linea_px=(0, 0, 0, 0),
                roi_senales_px=(0, 0, 0, 0),
                alto=alto,
                ancho=ancho,
            )

        # Suavizado Gaussiano (reducción de ruido) y conversión a HSV.
        suavizada = cv2.GaussianBlur(imagen_bgr, KERNEL_SUAVIZADO, 0)
        hsv = cv2.cvtColor(suavizada, cv2.COLOR_BGR2HSV)

        roi_linea = recorte_px(self._params.roi_linea, ancho, alto)
        roi_senales = recorte_px(self._params.roi_senales, ancho, alto)

        x1, y1, w1, h1 = roi_linea
        x2, y2, w2, h2 = roi_senales
        return ResultadoPreprocesamiento(
            hsv_linea=hsv[y1 : y1 + h1, x1 : x1 + w1],
            hsv_senales=hsv[y2 : y2 + h2, x2 : x2 + w2],
            roi_linea_px=roi_linea,
            roi_senales_px=roi_senales,
            alto=alto,
            ancho=ancho,
        )