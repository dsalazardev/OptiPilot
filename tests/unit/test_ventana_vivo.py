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

from src.main import _ControlManual, _VentanaEnVivo, _iterar_captura
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


# -- dead-man ------------------------------------------------------------


def test_silencio_en_modo_manual_detiene_el_robot() -> None:
    """El dead-man es el motivo de existir del modo manual con seguridad."""
    cola = ColaTransporte()
    transporte = TransporteSimulado()
    control = _ControlManual(cola, deadman_s=0.15)
    control.alternar_modo()
    cola.drenar(transporte)

    # El operador salió a buscar algo y no vuelve a mandar órdenes.
    assert _esperar(lambda: cola.ultimo_enviado() is not None, 2.0), (
        "el dead-man debió encolar DETENER tras el silencio"
    )
    cola.drenar(transporte)
    assert cola.ultimo_enviado() is ComandoMovimiento.DETENER
    control.pedir_cierre()


def test_una_orden_de_movimiento_repone_el_margen() -> None:
    """Teclear mantiene vivo el robot; el silencio posterior vuelve a parar."""
    cola = ColaTransporte()
    transporte = TransporteSimulado()
    control = _ControlManual(cola, deadman_s=0.25)
    control.alternar_modo()

    # Con una orden reciente no debe dispararse el dead-man todavía.
    control.interpretar("w")
    time.sleep(0.1)
    cola.drenar(transporte)
    assert transporte.historial()[-1] is ComandoMovimiento.AVANZAR

    # Y al soltar las teclas, sí.
    assert _esperar(lambda: bool(cola.drenar(transporte)), 2.0)
    assert cola.ultimo_enviado() is ComandoMovimiento.DETENER
    control.pedir_cierre()


def test_el_deadman_no_dispara_en_modo_autonomo() -> None:
    """En autónomo manda la visión: el vigilante no debe interferir."""
    cola = ColaTransporte()
    transporte = TransporteSimulado()
    control = _ControlManual(cola, deadman_s=0.1)
    # Nunca se entra en modo manual.
    time.sleep(0.3)
    cola.drenar(transporte)
    assert transporte.historial() == []
    control.pedir_cierre()


def test_salir_del_modo_manual_detiene_el_vigilante() -> None:
    """Al volver a autónomo el vigilante muere: no puede parar a la visión."""
    cola = ColaTransporte()
    transporte = TransporteSimulado()
    control = _ControlManual(cola, deadman_s=0.1)
    control.alternar_modo()
    control.alternar_modo()  # de vuelta a autónomo
    assert control.manual_activo is False

    time.sleep(0.3)
    cola.drenar(transporte)
    # Solo el DETENER de haber entrado en manual, nada del vigilante.
    assert transporte.historial() == [ComandoMovimiento.DETENER]
    control.pedir_cierre()


def test_cerrar_libera_el_vigilante() -> None:
    """``pedir_cierre`` no debe dejar un hilo vivo al final de la corrida."""
    control = _ControlManual(ColaTransporte(), deadman_s=0.1)
    control.alternar_modo()
    control.pedir_cierre()
    # Si el vigilante quedara vivo, join con timeoutExpired delataría el hilo.
    control._detener_vigilante()


# -- cronómetro real ----------------------------------------------------


class _CapturaDoble:
    """Captura falsa: devuelve N fotogramas y simula una entrega lenta."""

    def __init__(self, total: int, espera_s: float) -> None:
        self.total = total
        self.espera_s = espera_s
        self.leidos = 0

    def read(self):
        if self.leidos >= self.total:
            return False, None
        self.leidos += 1
        if self.espera_s:
            time.sleep(self.espera_s)
        return True, np.full((4, 4, 3), self.leidos, dtype=np.uint8)


def test_reloj_real_mide_el_tiempo_de_verdad() -> None:
    """``t_s`` debe seguir al reloj, no al índice dividido por el fps."""
    # 4 fotogramas a 30 fps nominales, pero entregados con 50 ms de retraso real:
    # por índice saldrían 0.0, 0.033, 0.067, 0.100; por reloj, ~0.05, ~0.10, ...
    captura = _CapturaDoble(total=4, espera_s=0.05)
    tiempos = [t for _, t, _ in _iterar_captura(captura, 30.0, None, reloj_real=True)]

    assert len(tiempos) == 4
    assert tiempos[0] >= 0.05, f"el primer fotograma ya tardó 50 ms: {tiempos}"
    # Si usara indice/fps, el último sería 3/30 = 0.1 s exactos.
    assert tiempos[-1] >= 0.19, f"el reloj real no está midiendo la entrega: {tiempos}"
    assert tiempos == sorted(tiempos), "el tiempo debe ser monótono"


def test_reloj_de_video_sigue_usando_indice_sobre_fps() -> None:
    """Sin ``reloj_real`` el tiempo es ``indice / fps``: las pruebas lo fijan."""
    captura = _CapturaDoble(total=4, espera_s=0.05)
    tiempos = [t for _, t, _ in _iterar_captura(captura, 30.0, None)]

    assert tiempos == [0.0, 1 / 30, 2 / 30, 3 / 30]


def test_el_parada_dura_t_segundos_reales_con_reloj_real() -> None:
    """El requisito: T = 3.0 s deben ser 3 segundos reales en fuente viva."""
    # 30 fps declarados pero 20 ms de retraso real: por índice, 6 fotogramas
    # "valdrían" 0.2 s; por reloj, 6 fotogramas tardan ~0.12 s de más.
    captura = _CapturaDoble(total=6, espera_s=0.02)
    t_inicio = time.perf_counter()
    tiempos = [t for _, t, _ in _iterar_captura(captura, 30.0, None, reloj_real=True)]
    transcurrido = time.perf_counter() - t_inicio

    assert tiempos[-1] >= 0.11, f"el reloj no capturó la latencia de entrega: {tiempos}"
    # El error contra el reloj del proceso es el ruido de la propia medición.
    assert abs(tiempos[-1] - transcurrido) < 0.02


def test_max_fotogramas_no_ignora_el_reloj_real() -> None:
    captura = _CapturaDoble(total=10, espera_s=0.0)
    indices = [i for i, _, _ in _iterar_captura(captura, 30.0, 3, reloj_real=True)]
    assert indices == [0, 1, 2]
