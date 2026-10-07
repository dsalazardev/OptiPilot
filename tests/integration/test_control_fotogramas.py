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

import numpy as np
import pytest

from src.transporte.cola import ColaTransporte
from src.transporte.simulado import TransporteSimulado
from src.vision.configuracion import ParametrosConfiguracion
from src.vision.maquina_estados import MaquinaEstados
from src.vision.modelos import (
    CausaComando,
    ComandoMovimiento,
    EstadoRobot,
    PermisoMovimiento,
    TipoEvento,
)
from src.vision.pipeline import PipelineVision
from tests.fixtures.generador_sintetico import (
    color_por_clase,
    crear_fondo,
    dibujar_octagono,
)
from tests.integration._escenarios import (
    ALTO,
    ANCHO,
    POSICIONES_SENAL,
    RADIO_SENAL,
    X_LINEA,
    fotograma_con,
)


class Corrida:
    """Resultado observable de una corrida de control."""

    def __init__(self) -> None:
        self.comandos_control: list[ComandoMovimiento] = []
        self.comandos_finales: list[ComandoMovimiento] = []
        self.causas_finales: list[CausaComando] = []
        self.veredictos: list[PermisoMovimiento] = []
        self.estados: list[EstadoRobot] = []
        self.eventos: list = []


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
        corrida.estados.append(estado.estado)
        corrida.eventos.extend(resultado.eventos)

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


# ---------------------------------------------------------------------------
# Feature 003 — cruce de señal: PARE/SIGA sobre la pista tapan la línea
# ---------------------------------------------------------------------------


def _fotograma_con_senal_sin_linea(clase: str) -> np.ndarray:
    """La señal está sobre la pista y tapa la línea: solo se ve el octágono.

    No se dibuja la línea a propósito: es exactamente lo que ve el estimador
    cuando el robot llega a la señal, y lo que antes se confundía con una
    pérdida de pista.
    """
    imagen = crear_fondo(ALTO, ANCHO)
    dibujar_octagono(imagen, POSICIONES_SENAL[clase], RADIO_SENAL, color_por_clase(clase))
    return imagen


def test_el_cruce_de_siga_no_dispara_busqueda_lateral(params: ParametrosConfiguracion) -> None:
    """SIGA tapando la línea: avance recto, sin búsqueda y sin parada."""
    frames = (
        [fotograma_con([], x_linea=X_LINEA)] * 30
        + [_fotograma_con_senal_sin_linea("SIGA")] * 60
        + [fotograma_con([], x_linea=X_LINEA)] * 30
    )
    corrida, _ = _correr(frames, params)
    # El SIGA confirma al tercer fotograma (índice 32); desde ahí y hasta que
    # reaparece la línea el único comando es el avance del cruce.
    en_cruce = range(32, 90)
    assert {corrida.causas_finales[i] for i in en_cruce} == {CausaComando.CRUCE_SENAL}
    assert all(corrida.comandos_finales[i] is ComandoMovimiento.AVANZAR for i in en_cruce)
    assert CausaComando.RECUPERACION not in corrida.causas_finales
    assert CausaComando.GRACIA_AGOTADA not in corrida.causas_finales
    assert PermisoMovimiento.NO_AUTORIZADO not in corrida.veredictos


def test_el_cruce_del_pare_detiene_tres_segundos_y_sigue_recto(
    params: ParametrosConfiguracion,
) -> None:
    """PARE tapando la línea: 3 s de parada y salida recta, sin búsqueda."""
    frames = (
        [fotograma_con([], x_linea=X_LINEA)] * 30
        + [_fotograma_con_senal_sin_linea("PARE")] * 90
        + [fotograma_con([], x_linea=X_LINEA)] * 60
    )
    corrida, _ = _correr(frames, params)
    vetados = [
        i
        for i, veredicto in enumerate(corrida.veredictos)
        if veredicto is PermisoMovimiento.NO_AUTORIZADO
    ]
    assert vetados, "el PARE debe vetar el movimiento"
    assert all(corrida.comandos_finales[i] is ComandoMovimiento.DETENER for i in vetados)
    assert all(corrida.causas_finales[i] is CausaComando.VETO_FSM for i in vetados)
    # La parada cubre T completo (90 fotogramas a 30 fps), con ±1 por el
    # redondeo de índice a tiempo.
    assert abs(len(vetados) - int(params.t_parada_s * params.fps_objetivo)) <= 1
    assert CausaComando.GRACIA_AGOTADA not in corrida.causas_finales
    assert CausaComando.RECUPERACION not in corrida.causas_finales
    # El primer fotograma autorizado tras el veto sigue en el cruce: recto.
    assert corrida.comandos_finales[vetados[-1] + 1] is ComandoMovimiento.AVANZAR
    assert corrida.causas_finales[vetados[-1] + 1] is CausaComando.CRUCE_SENAL


def test_el_mismo_pare_no_vuelve_a_detenerse_mientras_se_cruza(
    params: ParametrosConfiguracion,
) -> None:
    """Un PARE que parpadea durante el cruce no genera un segundo alto.

    Secuencia: la señal aparece (confirma y detiene), se oculta más de
    ``x_rearme`` fotogramas mientras el robot sigue sobre ella, y vuelve a
    aparecer cuando el cronómetro ya se cumplió. Si el rearme no estuviera
    bloqueado, la reaparición sería una ocurrencia nueva y el robot volvería a
    detenerse 3 s sobre la misma señal.
    """
    frames = (
        [fotograma_con([], x_linea=X_LINEA)] * 30           # 0-29: línea
        + [_fotograma_con_senal_sin_linea("PARE")] * 20     # 30-49: confirma
        + [crear_fondo(ALTO, ANCHO)] * 80                   # 50-129: ni línea ni señal
        + [_fotograma_con_senal_sin_linea("PARE")] * 40     # 130-169: la misma señal vuelve
        + [fotograma_con([], x_linea=X_LINEA)] * 40         # 170-209: línea de nuevo
    )
    corrida, _ = _correr(frames, params)
    # Solo la primera confirmación llega al sistema: la reaparición se filtra.
    confirmaciones = [e for e in corrida.eventos if e.tipo is TipoEvento.PARE_CONFIRMADO]
    assert len(confirmaciones) == 1
    # Un solo intervalo de veto: el PARE no vuelve a detener al robot.
    entradas = [
        i
        for i, veredicto in enumerate(corrida.veredictos)
        if veredicto is PermisoMovimiento.NO_AUTORIZADO
        and (i == 0 or corrida.veredictos[i - 1] is PermisoMovimiento.AUTORIZADO)
    ]
    assert len(entradas) == 1
    # Tras la parada, con la señal delante, avanza recto: no busca ni gira.
    assert CausaComando.GRACIA_AGOTADA not in corrida.causas_finales
    assert CausaComando.RECUPERACION not in corrida.causas_finales
    assert all(
        corrida.comandos_finales[i] is ComandoMovimiento.AVANZAR for i in range(135, 170)
    )
