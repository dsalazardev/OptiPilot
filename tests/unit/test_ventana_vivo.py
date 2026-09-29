"""Tests unitarios de la ventana en vivo del CLI (``--mostrar``).

Verifican, con un doble de renderizador (sin abrir ventanas reales), que
``publicar`` no bloquea, que el hilo dibuja el último fotograma disponible, que
cerrar la ventana pide terminar la corrida y que un fallo al abrir la ventana
se reporta sin tumbar la corrida (FR-031, SC-005).
"""

from __future__ import annotations

import threading
import time

import numpy as np

from src.main import _VentanaEnVivo


class _RenderizadorDoble:
    """Doble de prueba del renderizador: registra fotogramas y el cierre."""

    def __init__(self, nombre: str, cerrar: threading.Event) -> None:
        self.nombre = nombre
        self._cerrar = cerrar
        self.fotogramas: list[np.ndarray] = []
        self.dibujado = threading.Event()
        self.cerrada = False

    def dibujar(self, fotograma: np.ndarray) -> None:
        self.fotogramas.append(fotograma)
        self.dibujado.set()

    def cerrar(self) -> None:
        self.cerrada = True

    def simular_cierre(self) -> None:
        self._cerrar.set()


def _fotograma(valor: int) -> np.ndarray:
    return np.full((4, 4, 3), valor, dtype=np.uint8)


def _esperar(condicion, limite_s: float = 2.0) -> bool:
    fin = time.monotonic() + limite_s
    while time.monotonic() < fin:
        if condicion():
            return True
        time.sleep(0.005)
    return condicion()


def _crear(registrados: list[_RenderizadorDoble]) -> _VentanaEnVivo:
    def renderizador(nombre, cerrar):
        doble = _RenderizadorDoble(nombre, cerrar)
        registrados.append(doble)
        return doble

    vista = _VentanaEnVivo(renderizador=renderizador)
    vista.iniciar()
    assert _esperar(lambda: bool(registrados)), "el hilo no construyó el renderizador"
    return vista


def test_publicar_entrega_el_ultimo_fotograma_y_detener_cierra() -> None:
    registrados: list[_RenderizadorDoble] = []
    vista = _crear(registrados)
    doble = registrados[0]

    primero = _fotograma(1)
    segundo = _fotograma(2)
    vista.publicar(primero)
    assert _esperar(lambda: bool(doble.fotogramas))
    vista.publicar(segundo)
    assert _esperar(lambda: doble.fotogramas[-1] is segundo)

    assert vista.cierre_pedido is False
    assert vista.error is None
    vista.detener()
    assert doble.cerrada is True


def test_cerrar_la_ventana_pide_terminar_la_corrida() -> None:
    registrados: list[_RenderizadorDoble] = []
    vista = _crear(registrados)
    registrados[0].simular_cierre()
    assert _esperar(lambda: vista.cierre_pedido)
    assert vista.error is None
    vista.detener()
    assert registrados[0].cerrada is True


def test_fallo_del_renderizador_se_reporta_sin_romper() -> None:
    def renderizador(nombre, cerrar):
        raise RuntimeError("sin pantalla")

    vista = _VentanaEnVivo(renderizador=renderizador)
    vista.iniciar()
    assert _esperar(lambda: vista.error is not None)
    assert "sin pantalla" in vista.error
    assert vista.cierre_pedido is False
    vista.publicar(_fotograma(3))
    vista.detener()
