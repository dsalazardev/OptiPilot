"""Generador de fotogramas sintéticos para pruebas headless (T007).

Produce imágenes BGR con octágonos PARE/SIGA, línea guía y ruido controlado.
Las señales se dibujan como polígonos simples con ``cv2.fillPoly`` y colores
planos de tono (HSV) estable, para poder validar la segmentación por color sin
cámara ni footage externo (Constitución §V).
"""

from __future__ import annotations

import cv2
import numpy as np

ALTO_POR_DEFECTO = 480
ANCHO_POR_DEFECTO = 640
COLOR_FONDO = (225, 225, 225)
ROJO_BGR = (30, 30, 220)
VERDE_BGR = (60, 200, 60)
LINEA_BGR = (40, 40, 40)
LADOS_OCTAGONO = 8

__all__ = [
    "ALTO_POR_DEFECTO",
    "ANCHO_POR_DEFECTO",
    "COLOR_FONDO",
    "LINEA_BGR",
    "ROJO_BGR",
    "VERDE_BGR",
    "aplicar_ruido",
    "color_por_clase",
    "crear_fondo",
    "dibujar_linea_vertical",
    "dibujar_octagono",
    "fotograma_con_linea",
    "fotograma_con_senal",
    "fotograma_vacio",
    "puntos_octagono",
]


def color_por_clase(clase: str) -> tuple[int, int, int]:
    """Color BGR plano de la señal: rojo para PARE, verde para SIGA."""
    return ROJO_BGR if clase.upper() == "PARE" else VERDE_BGR


def crear_fondo(
    alto: int = ALTO_POR_DEFECTO,
    ancho: int = ANCHO_POR_DEFECTO,
    color_bgr: tuple[int, int, int] = COLOR_FONDO,
) -> np.ndarray:
    """Fotograma uniforme del tamaño indicado."""
    imagen = np.zeros((alto, ancho, 3), dtype=np.uint8)
    imagen[:, :] = color_bgr
    return imagen


def puntos_octagono(
    centro: tuple[int, int],
    radio: float,
    rotacion_grados: float = 0.0,
) -> np.ndarray:
    """8 vértices de un octágono regular con rotación y escala controladas."""
    angulos = np.linspace(0.0, 2.0 * np.pi, LADOS_OCTAGONO, endpoint=False)
    angulos = angulos + np.deg2rad(rotacion_grados)
    x = centro[0] + radio * np.cos(angulos)
    y = centro[1] + radio * np.sin(angulos)
    return np.column_stack([x, y]).astype(np.int32)


def dibujar_octagono(
    imagen: np.ndarray,
    centro: tuple[int, int],
    radio: float,
    color_bgr: tuple[int, int, int],
    rotacion_grados: float = 0.0,
) -> None:
    """Dibuja un octágono relleno (polígono simple) sobre la imagen."""
    vertices = puntos_octagono(centro, radio, rotacion_grados)
    cv2.fillPoly(imagen, [vertices], color_bgr)


def dibujar_linea_vertical(
    imagen: np.ndarray,
    x_centro: int,
    grosor: int,
    color_bgr: tuple[int, int, int] = LINEA_BGR,
) -> None:
    """Dibuja una línea vertical desde el borde inferior hasta la mitad del cuadro."""
    alto = imagen.shape[0]
    cv2.rectangle(
        imagen,
        (x_centro - grosor // 2, alto // 2),
        (x_centro + grosor // 2, alto - 1),
        color_bgr,
        thickness=-1,
    )


def aplicar_ruido(imagen: np.ndarray, sigma: float, semilla: int = 0) -> np.ndarray:
    """Añade ruido gaussiano determinista (semilla explícita)."""
    if sigma <= 0:
        return imagen.copy()
    generador = np.random.default_rng(semilla)
    ruido = generador.normal(loc=0.0, scale=sigma, size=imagen.shape)
    con_ruido = imagen.astype(np.float32) + ruido
    return np.clip(con_ruido, 0, 255).astype(np.uint8)


def fotograma_con_senal(
    clase: str = "PARE",
    centro: tuple[int, int] = (320, 140),
    radio: float = 45.0,
    rotacion_grados: float = 0.0,
    ruido_sigma: float = 0.0,
    semilla: int = 0,
    alto: int = ALTO_POR_DEFECTO,
    ancho: int = ANCHO_POR_DEFECTO,
) -> np.ndarray:
    """Fotograma con un octágono de la clase indicada en la zona de señales."""
    imagen = crear_fondo(alto, ancho)
    dibujar_octagono(imagen, centro, radio, color_por_clase(clase), rotacion_grados)
    return aplicar_ruido(imagen, ruido_sigma, semilla)


def fotograma_con_linea(
    x_centro: int = 320,
    grosor: int = 24,
    ruido_sigma: float = 0.0,
    semilla: int = 0,
    alto: int = ALTO_POR_DEFECTO,
    ancho: int = ANCHO_POR_DEFECTO,
) -> np.ndarray:
    """Fotograma con una línea guía oscura vertical en la zona inferior."""
    imagen = crear_fondo(alto, ancho)
    dibujar_linea_vertical(imagen, x_centro, grosor)
    return aplicar_ruido(imagen, ruido_sigma, semilla)


def fotograma_vacio(
    ruido_sigma: float = 0.0,
    semilla: int = 0,
    alto: int = ALTO_POR_DEFECTO,
    ancho: int = ANCHO_POR_DEFECTO,
) -> np.ndarray:
    """Fotograma sin línea ni señales (escena negativa)."""
    imagen = crear_fondo(alto, ancho)
    return aplicar_ruido(imagen, ruido_sigma, semilla)
