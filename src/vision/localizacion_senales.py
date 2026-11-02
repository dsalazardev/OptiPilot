"""Localización clásica de regiones candidatas de señal (specs/004).

La CNN no busca señales en el fotograma completo: eso produciría falsos
positivos (el modelo actual predice SIGA sobre footage sin señales). Esta etapa
usa segmentación por color, morfología y contornos —técnicas clásicas— para
proponer regiones; la CNN solo decide la clase de cada recorte.

Colores:
- rojo: PARE y el borde de VELOCIDAD 60;
- verde: SIGA;
- amarillo: ZONA ESCOLAR.

No se exige forma de octágono: ZONA ESCOLAR es un pentágono y VELOCIDAD 60 es
un círculo. El filtro de forma se limita a área y aspecto configurables.
"""

from __future__ import annotations

import cv2
import numpy as np

from .configuracion import ParametrosConfiguracion
from .modelos import ColorRegion, RegionSenal
from .preprocesamiento import ResultadoPreprocesamiento

__all__ = ["LocalizadorSenales"]

#: Tolerancia de la aproximación poligonal usada para el diagnóstico de vértices.
_EPSILON_APROX = 0.03

#: Solapamiento a partir del cual dos propuestas se consideran la misma región.
_IOU_SUPRESION = 0.5


def _mascarar(hsv: np.ndarray, rangos: tuple) -> np.ndarray:
    mascara = None
    for rango in rangos:
        inferior, superior = rango.limites()
        parcial = cv2.inRange(
            hsv,
            np.array(inferior, dtype=np.uint8),
            np.array(superior, dtype=np.uint8),
        )
        mascara = parcial if mascara is None else cv2.bitwise_or(mascara, parcial)
    return mascara


def _abrir_cerrar(mascara: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    abierta = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, kernel)
    return cv2.morphologyEx(abierta, cv2.MORPH_CLOSE, kernel)


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1 = max(ax, bx)
    y1 = max(ay, by)
    x2 = min(ax + aw, bx + bw)
    y2 = min(ay + ah, by + bh)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    interseccion = (x2 - x1) * (y2 - y1)
    union = aw * ah + bw * bh - interseccion
    return interseccion / union if union > 0 else 0.0


class LocalizadorSenales:
    """Propone regiones de señal con máscaras de color y contornos."""

    def __init__(self, params: ParametrosConfiguracion) -> None:
        self._params = params
        self._kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (params.kernel_morfologico_px, params.kernel_morfologico_px),
        )

    def propuestas(self, pre: ResultadoPreprocesamiento) -> list[RegionSenal]:
        """Devuelve regiones candidatas en coordenadas del fotograma completo."""
        hsv = pre.hsv_senales
        rx, ry, rw, rh = pre.roi_senales_px
        if hsv.size == 0 or rw <= 0 or rh <= 0:
            return []

        mascaras = (
            (ColorRegion.ROJO, _mascarar(hsv, self._params.rangos_hsv_rojo)),
            (ColorRegion.VERDE, _mascarar(hsv, (self._params.rango_hsv_verde,))),
            (ColorRegion.AMARILLO, _mascarar(hsv, (self._params.rango_hsv_amarillo,))),
        )
        area_roi = float(rw * rh)
        propuestas: list[RegionSenal] = []
        for color, mascara in mascaras:
            limpia = _abrir_cerrar(mascara, self._kernel)
            contornos, _ = cv2.findContours(
                limpia, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            for contorno in contornos:
                region = self._region(contorno, rx, ry, area_roi, color)
                if region is not None:
                    propuestas.append(region)

        return self._suprimir_solapadas(propuestas)

    def _region(
        self,
        contorno: np.ndarray,
        rx: int,
        ry: int,
        area_roi: float,
        color: ColorRegion,
    ) -> RegionSenal | None:
        area = float(cv2.contourArea(contorno))
        if area <= 0.0 or area_roi <= 0.0:
            return None
        area_rel = area / area_roi
        if area_rel < self._params.area_minima_region_senal_rel:
            return None

        x, y, ancho, alto = cv2.boundingRect(contorno)
        if ancho <= 0 or alto <= 0:
            return None
        aspecto = ancho / alto
        if not (
            self._params.aspecto_min <= aspecto <= self._params.aspecto_max
        ):
            return None

        perimetro = cv2.arcLength(contorno, True)
        aproximacion = cv2.approxPolyDP(contorno, _EPSILON_APROX * perimetro, True)
        n_vertices = len(aproximacion)
        if n_vertices < 3:
            return None

        caja = (x + rx, y + ry, ancho, alto)
        centro = (caja[0] + ancho // 2, caja[1] + alto // 2)
        return RegionSenal(
            caja_px=caja,
            centro_px=centro,
            area_px=int(area),
            area_rel=area_rel,
            n_vertices=n_vertices,
            aspecto=aspecto,
            color=color,
        )

    @staticmethod
    def _suprimir_solapadas(propuestas: list[RegionSenal]) -> list[RegionSenal]:
        ordenadas = sorted(propuestas, key=lambda r: r.area_px, reverse=True)
        conservadas: list[RegionSenal] = []
        for region in ordenadas:
            if all(
                _iou(region.caja_px, otra.caja_px) <= _IOU_SUPRESION
                for otra in conservadas
            ):
                conservadas.append(region)
        return conservadas
