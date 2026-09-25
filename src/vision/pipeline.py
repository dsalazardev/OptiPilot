"""Orquestador del pipeline de visión por fotograma (T013).

Compone las etapas clásicas en orden: preprocesamiento → segmentación →
candidatos → detección/confirmación. Cada etapa solo usa primitivas autorizadas
de OpenCV y lógica propia; aquí no hay ninguna decisión de detección nueva
(Constitución §I–§II), solo composición, medición de latencia por
``time.perf_counter`` y el marcador de **visibilidad plena** por señal.

El marcador (data-model §12, SC-006) registra el PRIMER fotograma en el que la
señal aparece completamente dentro de la ROI de señales con área ≥ mínima; es
la base temporal de la latencia de decisión y se re-inicia cuando la ocurrencia
se re-arma (cierre de la ocurrencia anterior).

Garantías de contrato (api-pipeline.md):
- determinista: mismas entradas + misma configuración ⇒ misma salida;
- un fotograma vacío/ilegible devuelve un resultado vacío sin excepción
  (FR-014), con máscaras de tamaño 0 y ``latencia_ms`` no negativa;
- el módulo es puro: no captura cámara ni abre archivos.
"""

from __future__ import annotations

import time

import numpy as np

from .candidatos import ExtractorCandidatos
from .configuracion import ParametrosConfiguracion
from .deteccion import Detector
from .modelos import (
    CandidatoSenal,
    ClaseSenal,
    MarcadorVisibilidadPlena,
    ResultadoProcesamiento,
)
from .preprocesamiento import Preprocesador
from .segmentacion import Segmentador

__all__ = [
    "PipelineVision",
]


def _dentro_de_roi(
    caja_px: tuple[int, int, int, int],
    roi_senales_px: tuple[int, int, int, int],
) -> bool:
    """True si la caja (x, y, w, h) cae por completo dentro de la ROI."""
    x, y, w, h = caja_px
    rx, ry, rw, rh = roi_senales_px
    return bool(x >= rx and y >= ry and x + w <= rx + rw and y + h <= ry + rh)


class PipelineVision:
    """Pipeline por fotograma: BGR → segmentación, candidatos y confirmación."""

    def __init__(self, params: ParametrosConfiguracion) -> None:
        self._preprocesador = Preprocesador(params)
        self._segmentador = Segmentador(params)
        self._extractor_candidatos = ExtractorCandidatos(params)
        self._detector = Detector(params)
        self._area_minima_rel = params.area_minima_rel
        self._visibilidad_plena: dict[ClaseSenal, MarcadorVisibilidadPlena | None] = {
            ClaseSenal.PARE: None,
            ClaseSenal.SIGA: None,
        }

    def procesar(
        self,
        indice: int,
        t_s: float,
        imagen_bgr: np.ndarray,
    ) -> ResultadoProcesamiento:
        """Procesa un fotograma y devuelve el ``ResultadoProcesamiento``."""
        inicio = time.perf_counter()

        preprocesado = self._preprocesador.aplicar(imagen_bgr)
        segmentacion = self._segmentador.aplicar(preprocesado)
        candidatos = self._extractor_candidatos.extraer(
            mascara_roja=segmentacion.mascara_roja,
            mascara_verde=segmentacion.mascara_verde,
            roi_senales_px=segmentacion.roi_senales,
        )
        deteccion = self._detector.actualizar(candidatos, indice, t_s)
        visibilidad = self._marcar_visibilidad(candidatos, segmentacion.roi_senales, indice, t_s)
        for clase in deteccion.clases_rearmadas:
            self._visibilidad_plena[clase] = None

        latencia_ms = (time.perf_counter() - inicio) * 1000.0

        return ResultadoProcesamiento(
            segmentacion=segmentacion,
            candidatos=candidatos,
            senales_confirmadas=list(deteccion.senales_confirmadas),
            eventos=list(deteccion.eventos),
            latencia_ms=latencia_ms,
            visibilidad_plena=visibilidad,
        )

    def _marcar_visibilidad(
        self,
        candidatos: list[CandidatoSenal],
        roi_senales_px: tuple[int, int, int, int],
        indice: int,
        t_s: float,
    ) -> list[MarcadorVisibilidadPlena]:
        """Marca la primera visibilidad plena de cada señal en su ocurrencia."""
        marcadores: list[MarcadorVisibilidadPlena] = []
        for candidato in candidatos:
            if not candidato.es_valido:
                continue
            if not _dentro_de_roi(candidato.caja_px, roi_senales_px):
                continue
            if candidato.area_rel < self._area_minima_rel:
                continue
            clase = candidato.clase_estimada
            if self._visibilidad_plena[clase] is None:
                marcador = MarcadorVisibilidadPlena(clase=clase, fotograma_idx=indice, t_s=t_s)
                self._visibilidad_plena[clase] = marcador
                marcadores.append(marcador)
        return marcadores