"""Integración del control en el bucle de producción (T036).

Recorre la cadena completa por fotograma —segmento → estima → decide → compone →
encola— con el **mismo orden que ``src/main.py::_correr``**, pero sobre
fotogramas sintéticos y con drenaje síncrono (el transporte real va en un hilo;
aquí interesa la secuencia de comandos, no el paralelismo).

La propiedad central que se verifica es SC-007 sobre una corrida entera: mientras
la FSM no autorice el movimiento, el comando encolado es ``DETENER``, pase lo que
pase con el control de trayectoria.
"""

from __future__ import annotations

import pytest

from src.transporte.cola import ColaTransporte
from src.transporte.simulado import TransporteSimulado
from src.vision.configuracion import ParametrosConfiguracion
from src.vision.maquina_estados import MaquinaEstados
from src.vision.modelos import (
    CausaComando,
    ComandoMovimiento,
    PermisoMovimiento,
)
from src.vision.pipeline import PipelineVision
from tests.integration._escenarios import X_LINEA, fotograma_con


class Corrida:
    """Resultado observable de una corrida de control."""

    def __init__(self) -> None:
        self.comandos_control: list[ComandoMovimiento] = []
        self.comandos_finales: list[ComandoMovimiento] = []
        self.causas_finales: list[CausaComando] = []
        self.veredictos: list[PermisoMovimiento] = []


def _correr(frames, params: ParametrosConfiguracion) -> tuple[Corrida, TransporteSimulado]:
    """Ejecuta el bucle de producción sobre los fotogramas dados."""
    pipeline = PipelineVision(params)
    maquina = MaquinaEstados(params, t_inicial=0.0)
    cola = ColaTransporte()
    transporte = TransporteSimulado()
    corrida = Corrida()

    for indice, imagen in enumerate(frames):
        t_s = indice / params.fps_objetivo
        resultado = pipeline.procesar(indice, t_s, imagen)
        presentes = frozenset(senal.clase for senal in resultado.senales_confirmadas)
        estado = maquina.actualizar(presentes, resultado.eventos, t_s)

        decision = pipeline.componer(resultado, estado.decision)
        corrida.comandos_control.append(resultado.decision_control.comando)
        corrida.comandos_finales.append(decision.comando)
        corrida.causas_finales.append(decision.causa)
        corrida.veredictos.append(estado.decision.veredicto)

        cola.encolar(decision.comando)
        cola.drenar(transporte)  # en el test el drenaje es síncrono

    return corrida, transporte


@pytest.fixture(scope="module")
def params() -> ParametrosConfiguracion:
    return ParametrosConfiguracion.por_defecto()


def _guion_con_pare() -> list:
    """Centrado → desplazado → PARE → centrado otra vez."""
    return (
        [fotograma_con([], x_linea=X_LINEA) for _ in range(10)]
        + [fotograma_con([], x_linea=X_LINEA + 110) for _ in range(10)]
        + [fotograma_con(["PARE"], x_linea=X_LINEA) for _ in range(10)]
        + [fotograma_con([], x_linea=X_LINEA) for _ in range(10)]
    )


def test_sc007_ningun_fotograma_no_autorizado_se_mueve(params: ParametrosConfiguracion) -> None:
    """SC-007 sobre la corrida entera: veto ⟹ ``DETENER`` en el 100 % de fotogramas."""
    corrida, _ = _correr(_guion_con_pare(), params)
    vetados = [
        indice
        for indice, veredicto in enumerate(corrida.veredictos)
        if veredicto is PermisoMovimiento.NO_AUTORIZADO
    ]
    assert vetados, "el guion debía provocar al menos un veto por PARE"
    for indice in vetados:
        assert corrida.comandos_finales[indice] is ComandoMovimiento.DETENER
        assert corrida.causas_finales[indice] is CausaComando.VETO_FSM


def test_la_fsm_efectivamente_veta_tras_confirmar_el_pare(params: ParametrosConfiguracion) -> None:
    """El guion confirma el PARE y la FSM lo refleja (no es un test vacío)."""
    corrida, _ = _correr(_guion_con_pare(), params)
    causas = [str(causa) for causa in corrida.causas_finales]
    assert "VETO_FSM" in causas


def test_sin_veto_el_comando_final_es_el_del_control(params: ParametrosConfiguracion) -> None:
    """Con la FSM autorizando, el compositor propaga la propuesta del control."""
    corrida, _ = _correr(_guion_con_pare(), params)
    for indice, veredicto in enumerate(corrida.veredictos):
        if veredicto is PermisoMovimiento.AUTORIZADO:
            assert corrida.comandos_finales[indice] is corrida.comandos_control[indice]


def test_el_control_corrige_hacia_el_lado_de_la_linea(params: ParametrosConfiguracion) -> None:
    """Con la línea desplazada a la derecha, el control pide ``DERECHA``."""
    corrida, _ = _correr(_guion_con_pare(), params)
    assert ComandoMovimiento.DERECHA in corrida.comandos_control


def test_la_cola_recibe_el_comando_final_no_el_del_control(params: ParametrosConfiguracion) -> None:
    """En los fotogramas vetados, el control propone avanzar pero se encola ``DETENER``."""
    corrida, transporte = _correr(_guion_con_pare(), params)
    vetados = [
        indice
        for indice, veredicto in enumerate(corrida.veredictos)
        if veredicto is PermisoMovimiento.NO_AUTORIZADO
    ]
    # El historial del transporte es la secuencia deduplicada de comandos finales.
    assert ComandoMovimiento.DETENER in transporte.historial()
    # Y al menos en un fotograma vetado el control proponía otra cosa.
    assert any(
        corrida.comandos_control[indice] is not ComandoMovimiento.DETENER for indice in vetados
    )


def test_la_cola_aplica_deduplicacion_en_la_corrida(params: ParametrosConfiguracion) -> None:
    """La radio no recibe un comando por fotograma: solo las transiciones."""
    corrida, transporte = _correr(_guion_con_pare(), params)
    assert len(transporte.historial()) < len(corrida.comandos_finales)
    assert len(transporte.historial()) > 0


def test_la_corrida_no_drena_dentro_del_bucle() -> None:
    """Documenta la frontera: este test drena a mano; la producción, en un hilo."""
    # Test de intención: si el bucle de _correr dejara de encolar, el historial
    # quedaría vacío aunque los comandos se calcularan bien.
    params = ParametrosConfiguracion.por_defecto()
    frames = [fotograma_con([], x_linea=X_LINEA) for _ in range(5)]
    pipeline = PipelineVision(params)
    maquina = MaquinaEstados(params, t_inicial=0.0)
    cola = ColaTransporte()
    for indice, imagen in enumerate(frames):
        resultado = pipeline.procesar(indice, indice / params.fps_objetivo, imagen)
        estado = maquina.actualizar(frozenset(), resultado.eventos, indice / params.fps_objetivo)
        decision = pipeline.componer(resultado, estado.decision)
        cola.encolar(decision.comando)
    assert cola.pendientes() > 0  # nada se drenó: está pendiente
    assert cola.ultimo_enviado() is None
