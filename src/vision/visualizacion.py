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

from .configuracion import ParametrosConfiguracion
from .maquina_estados import ResultadoEstado
from .modelos import ComandoMovimiento, DecisionCompuesta, ResultadoProcesamiento

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
_COLOR_OBJETIVO = (255, 255, 255)
_COLOR_ZONA = (180, 180, 180)
_COLOR_POSICION = (0, 255, 255)
_COLOR_AVANZAR = (0, 220, 0)
_COLOR_LATERAL = (0, 180, 255)
_COLOR_DETENER = (0, 0, 255)
_COLOR_MANUAL = (0, 165, 255)
_COLOR_AUTO = (0, 255, 0)

#: Recordatorio de teclas para la demostración en vivo (se dibuja abajo a la
#: derecha). Sin esto, en plena pista nadie recuerda el mapa de teclas.
_AYUDA_TECLAS = "m modo | w a d mover | x detener | c captura | q salir"


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


def _color_de_comando(comando: ComandoMovimiento) -> tuple[int, int, int]:
    if comando is ComandoMovimiento.AVANZAR:
        return _COLOR_AVANZAR
    if comando is ComandoMovimiento.DETENER:
        return _COLOR_DETENER
    return _COLOR_LATERAL


def _linea_vertical(anotada: np.ndarray, x: float, color: tuple[int, int, int], grosor: int) -> None:
    alto = anotada.shape[0]
    x_px = int(round(x))
    if 0 <= x_px < anotada.shape[1]:
        cv2.line(anotada, (x_px, 0), (x_px, alto - 1), color, grosor)


def _flecha_direccion(anotada: np.ndarray, comando: ComandoMovimiento) -> None:
    """Flecha grande en el centro: de un vistazo, hacia dónde va el robot.

    Es lo primero que mira el público en la demo, así que va centrada y gruesa.
    ``DETENER`` no es una dirección: se dibuja como un aspa para que se distinga
    de un giro.
    """
    alto, ancho = anotada.shape[:2]
    cx, cy = ancho // 2, int(alto * 0.66)
    largo = int(min(ancho, alto) * 0.15)
    grosor = max(5, int(min(ancho, alto) * 0.012))
    color = _color_de_comando(comando)

    if comando is ComandoMovimiento.DETENER:
        cv2.line(anotada, (cx - largo, cy - largo), (cx + largo, cy + largo), color, grosor, cv2.LINE_AA)
        cv2.line(anotada, (cx - largo, cy + largo), (cx + largo, cy - largo), color, grosor, cv2.LINE_AA)
        return

    destinos = {
        ComandoMovimiento.AVANZAR: (cx, cy - largo),
        ComandoMovimiento.IZQUIERDA: (cx - largo, cy),
        ComandoMovimiento.DERECHA: (cx + largo, cy),
    }
    destino = destinos.get(comando)
    if destino is None:
        return
    cv2.arrowedLine(anotada, (cx, cy), destino, color, grosor, cv2.LINE_AA, tipLength=0.35)


def _banner_modo(anotada: np.ndarray, modo: str | None) -> None:
    """Banda superior con el modo vigente, para no confundir AUTO con MANUAL."""
    if modo is None:
        return
    texto = f"MODO: {modo}"
    color = _COLOR_MANUAL if modo == "MANUAL" else _COLOR_AUTO
    (ancho_texto, alto_texto), _ = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    cv2.rectangle(anotada, (6, 6), (18 + ancho_texto, 18 + alto_texto), _COLOR_FONDO_TEXTO, -1)
    cv2.putText(
        anotada, texto, (12, 14 + alto_texto), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA
    )


def _ayuda_teclas(anotada: np.ndarray) -> None:
    """Recordatorio de teclas, abajo a la derecha."""
    (ancho_texto, _), _ = cv2.getTextSize(_AYUDA_TECLAS, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
    x = max(0, anotada.shape[1] - ancho_texto - 10)
    _texto(anotada, _AYUDA_TECLAS, (x, anotada.shape[0] - 10))


def _dibujar_control(
    anotada: np.ndarray,
    resultado: ResultadoProcesamiento,
    params: ParametrosConfiguracion,
    decision: DecisionCompuesta | None,
    comando_mostrado: ComandoMovimiento | None = None,
    modo: str | None = None,
) -> None:
    """Evidencia del control de trayectoria (T034, ``mapa-comandos.md`` §6).

    Dibuja la referencia de centrado (``x_objetivo``), la zona muerta, la banda
    de histéresis, la posición estimada y —si se pasa la decisión compuesta— el
    comando final con su causa y la memoria de lado. Es material del póster
    (criterios 9 y 10) y no participa en ninguna decisión.
    """
    ancho = anotada.shape[1]
    x_objetivo = params.x_objetivo * ancho
    zona = params.zona_muerta * ancho
    histeresis = params.histeresis * ancho

    _linea_vertical(anotada, x_objetivo, _COLOR_OBJETIVO, 1)
    for x in (x_objetivo - zona, x_objetivo + zona):
        _linea_vertical(anotada, x, _COLOR_ZONA, 1)
    for x in (x_objetivo - zona - histeresis, x_objetivo + zona + histeresis):
        cv2.line(
            anotada,
            (int(round(x)), 0),
            (int(round(x)), anotada.shape[0] - 1),
            _COLOR_ZONA,
            1,
            cv2.LINE_AA,
        )

    posicion = resultado.posicion
    if posicion is not None and posicion.valida and posicion.x_px is not None:
        _linea_vertical(anotada, posicion.x_px, _COLOR_POSICION, 2)
        _texto(anotada, f"x={posicion.x_px:.0f} e={posicion.error_norm:+.2f}", (8, 40))

    comando = (
        comando_mostrado
        if comando_mostrado is not None
        else (decision.comando if decision is not None else None)
    )
    if comando is None:
        _banner_modo(anotada, modo)
        _ayuda_teclas(anotada)
        return
    _flecha_direccion(anotada, comando)
    color = _color_de_comando(comando)
    escala = 0.9 if comando is ComandoMovimiento.DETENER else 0.6
    y = anotada.shape[0] - 52
    cv2.putText(
        anotada, str(comando), (8, y), cv2.FONT_HERSHEY_SIMPLEX, escala, _COLOR_FONDO_TEXTO, 4, cv2.LINE_AA
    )
    cv2.putText(anotada, str(comando), (8, y), cv2.FONT_HERSHEY_SIMPLEX, escala, color, 2, cv2.LINE_AA)
    if decision is not None:
        _texto(anotada, f"causa: {decision.causa}", (8, y + 18))
    _banner_modo(anotada, modo)
    _ayuda_teclas(anotada)


def anotar(
    imagen_bgr: np.ndarray,
    resultado: ResultadoProcesamiento,
    estado: ResultadoEstado | None = None,
    params: ParametrosConfiguracion | None = None,
    decision: DecisionCompuesta | None = None,
    comando_mostrado: ComandoMovimiento | None = None,
    modo: str | None = None,
) -> np.ndarray:
    """Devuelve una copia anotada del fotograma. No modifica la entrada ni guarda.

    ``cv2.putText`` no dibuja tildes ni caracteres fuera de ASCII, así que los
    rótulos del panel se escriben sin acentos; la causa de la decisión sí puede
    llevar el guion bajo de ``T_CUMPLIDO``.

    ``params`` y ``decision`` son opcionales para no romper a los consumidores de
    001: sin ellos se dibuja exactamente lo mismo que antes. Con ellos se añade
    la evidencia del control de trayectoria (T034).

    ``comando_mostrado`` permite pintar una orden distinta a la de ``decision``:
    en modo MANUAL el robot obedece al teclado, así que el visor debe dibujar esa
    orden y no la que el pipeline habría tomado. ``modo`` rotula AUTO/MANUAL.
    """
    anotada = imagen_bgr.copy()
    segmentacion = resultado.segmentacion
    _superponer(anotada, segmentacion.mascara_linea, _COLOR_LINEA, _ALFA_LINEA)
    _superponer(anotada, segmentacion.mascara_roja, _COLOR_PARE, _ALFA_SENAL)
    _superponer(anotada, segmentacion.mascara_verde, _COLOR_SIGA, _ALFA_SENAL)
    _dibujar_candidatos(anotada, resultado)
    _dibujar_confirmadas(anotada, resultado)
    if params is not None:
        _dibujar_control(anotada, resultado, params, decision, comando_mostrado, modo)
    if estado is not None:
        _dibujar_estado(anotada, estado)
    return anotada
