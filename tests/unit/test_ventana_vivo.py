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
import pytest

from src.main import _ControlManual, _VentanaEnVivo
from src.transporte.cola import ColaTransporte
from src.transporte.simulado import TransporteSimulado
from src.vision.modelos import ComandoMovimiento


class _RenderizadorDoble:
    """Doble de prueba del renderizador: registra fotogramas y el cierre."""

    def __init__(self, nombre: str, control) -> None:
        self.nombre = nombre
        self.control = control
        self.fotogramas: list[np.ndarray] = []
        self.dibujado = threading.Event()
        self.cerrada = False

    def dibujar(self, fotograma: np.ndarray) -> None:
        self.fotogramas.append(fotograma)
        self.dibujado.set()

    def cerrar(self) -> None:
        self.cerrada = True

    def simular_cierre(self) -> None:
        self.control.pedir_cierre()


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
    def renderizador(nombre, control):
        doble = _RenderizadorDoble(nombre, control)
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
    def renderizador(nombre, control):
        raise RuntimeError("sin pantalla")

    vista = _VentanaEnVivo(renderizador=renderizador)
    vista.iniciar()
    assert _esperar(lambda: vista.error is not None)
    assert "sin pantalla" in vista.error
    assert vista.cierre_pedido is False
    vista.publicar(_fotograma(3))
    vista.detener()


# -- control manual por teclado ------------------------------------------------


@pytest.mark.parametrize(
    ("keysym", "esperado"),
    [
        ("w", ComandoMovimiento.AVANZAR),
        ("W", ComandoMovimiento.AVANZAR),
        ("a", ComandoMovimiento.IZQUIERDA),
        ("A", ComandoMovimiento.IZQUIERDA),
        ("d", ComandoMovimiento.DERECHA),
        ("D", ComandoMovimiento.DERECHA),
        ("x", ComandoMovimiento.DETENER),
        ("X", ComandoMovimiento.DETENER),
        ("space", ComandoMovimiento.DETENER),
    ],
)
def test_teclas_de_movimiento_en_cola(keysym: str, esperado: ComandoMovimiento) -> None:
    cola = ColaTransporte()
    control = _ControlManual(cola)
    control.alternar_modo()  # a modo manual

    control.interpretar(keysym)
    cola.drenar(TransporteSimulado())

    assert cola.ultimo_enviado() is esperado


def test_teclas_de_movimiento_se_ignoran_en_modo_autonomo() -> None:
    cola = ColaTransporte()
    control = _ControlManual(cola)

    assert control.manual_activo is False
    control.interpretar("w")

    cola.drenar(TransporteSimulado())
    assert cola.ultimo_enviado() is None


def test_entrar_en_modo_manual_detiene_el_robot() -> None:
    cola = ColaTransporte()
    transporte = TransporteSimulado()
    cola.encolar(ComandoMovimiento.DERECHA)
    cola.drenar(transporte)

    control = _ControlManual(cola)
    assert control.alternar_modo() == "MANUAL"
    cola.drenar(transporte)

    # El operador no puede heredar el último mando del pipeline creyendo que
    # tiene el control: al conmutar, el robot queda parado.
    assert cola.ultimo_enviado() is ComandoMovimiento.DETENER


@pytest.mark.parametrize("keysym", ["q", "Q", "Escape"])
def test_teclas_de_cierre_piden_terminar(keysym: str) -> None:
    control = _ControlManual(ColaTransporte())
    assert control.interpretar(keysym) == "cerrar"
    assert control.cerrar.is_set()


def test_tecla_m_alterna_el_modo_y_la_etiqueta() -> None:
    control = _ControlManual(ColaTransporte())
    assert control.modo == "AUTÓNOMO"

    assert control.interpretar("m") == "modo MANUAL"
    assert control.manual_activo is True
    assert control.modo == "MANUAL"

    assert control.interpretar("M") == "modo AUTÓNOMO"
    assert control.manual_activo is False
    assert control.modo == "AUTÓNOMO"


def test_tecla_no_mapeada_no_hace_nada() -> None:
    cola = ColaTransporte()
    control = _ControlManual(cola)
    control.alternar_modo()

    assert control.interpretar("z") is None
    assert control.interpretar("") is None
    cola.drenar(TransporteSimulado())
    # La única transmisión es el DETENER del conmutador, no una orden de `z`.
    assert cola.ultimo_enviado() is ComandoMovimiento.DETENER


def test_la_ventana_expone_el_modo_al_bucle_de_vision() -> None:
    registrados: list[_RenderizadorDoble] = []
    vista = _crear(registrados)
    assert vista.manual_activo is False

    vista.control.alternar_modo()
    assert vista.manual_activo is True

    vista.detener()
    assert registrados[0].cerrada is True
