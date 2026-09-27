"""Anotación visual por etapa para el modo diagnóstico (SC-012).

Dibuja sobre una **copia** del fotograma las máscaras de segmentación, los
candidatos con su veredicto de forma, las señales confirmadas y —si se pasa—
el estado y la decisión de la máquina. Sirve como evidencia explicable por etapa
para el póster y la defensa oral, y **nunca** guarda en disco: el guardado es
responsabilidad del CLI (contrato ``api-pipeline.md`` §Visualización).

No participa en ninguna decisión: recibe el resultado ya calculado y solo lo
dibuja (contrato de eventos/métricas, Regla 4).
"""

from __future__ import annotations

import cv2
import numpy as np

from .maquina_estados import ResultadoEstado
from .modelos import ResultadoProcesamiento

__all__ = ["anotar"]

_ALFA_LINEA = 0.35
_ALFA_SENAL = 0.55
_COLOR_LINEA = (255, 200, 0)
_COLOR_PARE = (0, 0, 255)
_COLOR_SIGA = (0, 200, 0)
_COLOR_VALIDO = (0, 220, 0)
_COLOR_INVALIDO = (0, 140, 255)
_COLOR_TEXTO = (255, 255, 255)
_COLOR_FONDO_TEXTO = (0, 0, 0)


def _superponer(anotada: np.ndarray, mascara: np.ndarray, color: tuple[int, int, int], alfa: float) -> None:
    """Mezcla ``color`` sobre ``anotada`` solo donde ``mascara`` es positiva.

    Se recorta la mezcla a la selección en vez de aplicarla al fotograma entero,
    para no teñir las zonas ajenas a la máscara.
    """
    seleccion = mascara > 0
    if not seleccion.any():
        return
    capa = np.zeros_like(anotada)
    capa[seleccion] = color
    mezcla = cv2.addWeighted(capa, alfa, anotada, 1.0 - alfa, 0.0)
    anotada[seleccion] = mezcla[seleccion]


def _texto(anotada: np.ndarray, contenido: str, org: tuple[int, int]) -> None:
    """Escribe una línea de texto con fondo para que se lea sobre cualquier máscara."""
    (x, y) = org
    cv2.putText(
        anotada,
        contenido,
        (x + 1, y + 1),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        _COLOR_FONDO_TEXTO,
        2,
        cv2.LINE_AA,
    )
    cv2.putText(anotada, contenido, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, _COLOR_TEXTO, 1, cv2.LINE_AA)


def _color_de_clase(clase) -> tuple[int, int, int]:
    return _COLOR_PARE if str(clase) == "PARE" else _COLOR_SIGA


def _dibujar_candidatos(anotada: np.ndarray, resultado: ResultadoProcesamiento) -> None:
    """Contorno de cada candidato con su clase y el motivo si fue descartado."""
    for candidato in resultado.candidatos:
        x, y, ancho, alto = candidato.caja_px
        color = _COLOR_VALIDO if candidato.es_valido else _COLOR_INVALIDO
        cv2.rectangle(anotada, (x, y), (x + ancho, y + alto), color, 1)
        etiqueta = f"{candidato.clase_estimada} v={candidato.n_vertices}"
        if not candidato.es_valido and candidato.motivo_invalidez:
            etiqueta = f"{etiqueta} {candidato.motivo_invalidez}"
        _texto(anotada, etiqueta, (max(0, x), max(12, y - 4)))


def _dibujar_confirmadas(anotada: np.ndarray, resultado: ResultadoProcesamiento) -> None:
    """Marca la señal confirmada y su ocurrencia (flanco de subida de FR-011)."""
    for senal in resultado.senales_confirmadas:
        color = _color_de_clase(senal.clase)
        cv2.circle(anotada, senal.centro_px, 6, color, -1)
        _texto(anotada, f"{senal.clase} CONF oc={senal.ocurrencia_id}", (8, 20))


def _dibujar_estado(anotada: np.ndarray, estado: ResultadoEstado) -> None:
    """Panel con estado, veredicto y causa de la decisión (data-model §8)."""
    decision = estado.decision
    lineas = [
        f"estado: {estado.estado}",
        f"decision: {decision.veredicto} ({decision.causa})",
    ]
    for numero, linea in enumerate(lineas):
        _texto(anotada, linea, (8, anotada.shape[0] - 30 + 14 * numero))


def anotar(
    imagen_bgr: np.ndarray,
    resultado: ResultadoProcesamiento,
    estado: ResultadoEstado | None = None,
) -> np.ndarray:
    """Devuelve una copia anotada del fotograma. No modifica la entrada ni guarda.

    ``cv2.putText`` no dibuja tildes ni caracteres fuera de ASCII, así que los
    rótulos del panel se escriben sin acentos; la causa de la decisión sí puede
    llevar el guion bajo de ``T_CUMPLIDO_CON_SIGA``.
    """
    anotada = imagen_bgr.copy()
    segmentacion = resultado.segmentacion
    _superponer(anotada, segmentacion.mascara_linea, _COLOR_LINEA, _ALFA_LINEA)
    _superponer(anotada, segmentacion.mascara_roja, _COLOR_PARE, _ALFA_SENAL)
    _superponer(anotada, segmentacion.mascara_verde, _COLOR_SIGA, _ALFA_SENAL)
    _dibujar_candidatos(anotada, resultado)
    _dibujar_confirmadas(anotada, resultado)
    if estado is not None:
        _dibujar_estado(anotada, estado)
    return anotada
