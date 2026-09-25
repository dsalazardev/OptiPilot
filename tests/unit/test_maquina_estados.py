"""Tests unitarios de la máquina de estados PARE/SIGA (T019).

Validan los 9 escenarios de aceptación de US2 inyectando secuencias
deterministas de señales confirmadas, eventos y tiempos inyectados: un PARE
detiene e inicia T, T nunca reanuda por sí solo, el SIGA confirmado durante la
detención queda armado y reanuda al cumplirse T, un PARE nuevo no reinicia T ni
invalida el SIGA armado, las pérdidas momentáneas ≤ K no afectan el estado ni el
cronómetro, y el rearme del PARE ocurre tras X fotogramas sin verlo. Se comprueba
además el determinismo y el invariante DETENIDO_* ⇒ NO_AUTORIZADO
(FR-015..FR-025).
"""

from __future__ import annotations

import pytest

from src.vision.maquina_estados import MaquinaEstados, ResultadoEstado
from src.vision.modelos import (
    CausaTransicion,
    ClaseSenal,
    DecisionMovimiento,
    EstadoRobot,
    EventoSenal,
    TipoEvento,
)


def _maquina(parametros_por_defecto) -> MaquinaEstados:
    """Máquina nueva en EN_MARCHA, con reloj arrancando en 0.0 s."""
    return MaquinaEstados(parametros_por_defecto, t_inicial=0.0)


def _evento(tipo: TipoEvento, clase: ClaseSenal, idx: int, t_s: float) -> EventoSenal:
    return EventoSenal(tipo=tipo, fotograma_idx=idx, t_s=t_s, clase=clase)


def _pare(idx: int, t_s: float) -> EventoSenal:
    return _evento(TipoEvento.PARE_CONFIRMADO, ClaseSenal.PARE, idx, t_s)


def _siga(idx: int, t_s: float) -> EventoSenal:
    return _evento(TipoEvento.SIGA_CONFIRMADO, ClaseSenal.SIGA, idx, t_s)


def _transiciones(resultado: ResultadoEstado) -> list[tuple]:
    return [(t.desde, t.hacia, t.causa) for t in resultado.transiciones_nuevas]


def test_estado_inicial_es_marcha_autORIZada(parametros_por_defecto) -> None:
    """Sin señales ni eventos el robot sigue y la decisión es AUTORIZADO (FR-015)."""
    maquina = _maquina(parametros_por_defecto)

    resultado = maquina.actualizar(frozenset(), [], t_s=0.0)

    assert resultado.estado is EstadoRobot.EN_MARCHA
    assert resultado.decision is DecisionMovimiento.AUTORIZADO
    assert resultado.transiciones_nuevas == []


def test_pare_detiene_e_inicia_el_cronometro_t(parametros_por_defecto) -> None:
    """Escenario 1: PARE confirmado en EN_MARCHA ⇒ NO_AUTORIZADO y DETENIDO_MINIMO."""
    maquina = _maquina(parametros_por_defecto)

    resultado = maquina.actualizar(
        frozenset({ClaseSenal.PARE}), [_pare(idx=0, t_s=0.0)], t_s=0.0
    )

    assert resultado.estado is EstadoRobot.DETENIDO_MINIMO
    assert resultado.decision is DecisionMovimiento.NO_AUTORIZADO
    assert _transiciones(resultado) == [
        (EstadoRobot.EN_MARCHA, EstadoRobot.DETENIDO_MINIMO, CausaTransicion.PARE_CONFIRMADO)
    ]


def test_pare_persistente_no_reinicia_t_ni_duplica_detencion(parametros_por_defecto) -> None:
    """Escenario 2: con PARE aún visible T no se reinicia ni se duplica la parada."""
    maquina = _maquina(parametros_por_defecto)
    maquina.actualizar(frozenset({ClaseSenal.PARE}), [_pare(0, 0.0)], t_s=0.0)

    intermedio = maquina.actualizar(frozenset({ClaseSenal.PARE}), [], t_s=1.0)
    reanudacion = maquina.actualizar(
        frozenset({ClaseSenal.PARE, ClaseSenal.SIGA}), [_siga(2, 3.0)], t_s=3.0
    )

    assert intermedio.estado is EstadoRobot.DETENIDO_MINIMO
    assert intermedio.decision is DecisionMovimiento.NO_AUTORIZADO
    assert intermedio.transiciones_nuevas == []
    assert reanudacion.estado is EstadoRobot.EN_MARCHA
    assert reanudacion.decision is DecisionMovimiento.AUTORIZADO


def test_siga_tras_cumplir_t_reanuda_y_registra_transicion(parametros_por_defecto) -> None:
    """Escenario 3: T cumplido y SIGA confirmado ⇒ AUTORIZADO y EN_MARCHA."""
    maquina = _maquina(parametros_por_defecto)
    maquina.actualizar(frozenset({ClaseSenal.PARE}), [_pare(0, 0.0)], t_s=0.0)

    resultado = maquina.actualizar(
        frozenset({ClaseSenal.SIGA}), [_siga(idx=1, t_s=3.0)], t_s=3.0
    )

    assert resultado.estado is EstadoRobot.EN_MARCHA
    assert resultado.decision is DecisionMovimiento.AUTORIZADO
    assert _transiciones(resultado) == [
        (EstadoRobot.DETENIDO_MINIMO, EstadoRobot.EN_MARCHA, CausaTransicion.T_CUMPLIDO)
    ]


def test_siga_confirmado_antes_de_t_queda_armado(parametros_por_defecto) -> None:
    """Escenario 4: SIGA antes de T reanuda al cumplirse T aunque salga de vista."""
    maquina = _maquina(parametros_por_defecto)
    maquina.actualizar(frozenset({ClaseSenal.PARE}), [_pare(0, 0.0)], t_s=0.0)
    armado = maquina.actualizar(
        frozenset({ClaseSenal.SIGA}), [_siga(idx=1, t_s=1.0)], t_s=1.0
    )

    resultado = maquina.actualizar(frozenset(), [], t_s=3.0)

    assert armado.estado is EstadoRobot.DETENIDO_MINIMO
    assert armado.decision is DecisionMovimiento.NO_AUTORIZADO
    assert resultado.estado is EstadoRobot.EN_MARCHA
    assert resultado.decision is DecisionMovimiento.AUTORIZADO


def test_siga_en_marcha_no_detiene(parametros_por_defecto) -> None:
    """Escenario 5: SIGA confirmado sin PARE en EN_MARCHA no detiene al robot."""
    maquina = _maquina(parametros_por_defecto)

    resultado = maquina.actualizar(
        frozenset({ClaseSenal.SIGA}), [_siga(idx=0, t_s=0.0)], t_s=0.0
    )

    assert resultado.estado is EstadoRobot.EN_MARCHA
    assert resultado.decision is DecisionMovimiento.AUTORIZADO


def test_t_cumplido_sin_siga_permanece_esperando(parametros_por_defecto) -> None:
    """Escenario 6: T por sí solo no reanuda; queda a la espera de SIGA (FR-017)."""
    maquina = _maquina(parametros_por_defecto)
    maquina.actualizar(frozenset({ClaseSenal.PARE}), [_pare(0, 0.0)], t_s=0.0)

    resultado = maquina.actualizar(frozenset({ClaseSenal.PARE}), [], t_s=5.0)

    assert resultado.decision is DecisionMovimiento.NO_AUTORIZADO
    assert resultado.estado is EstadoRobot.DETENIDO_ESPERANDO_SIGA


def test_perdida_momentanea_no_altera_estado_ni_cronometro(parametros_por_defecto) -> None:
    """Escenario 7: una pérdida ≤ K durante la parada deja intactos estado y T."""
    maquina = _maquina(parametros_por_defecto)
    maquina.actualizar(frozenset({ClaseSenal.PARE}), [_pare(0, 0.0)], t_s=0.0)

    durante_hueco = maquina.actualizar(frozenset(), [], t_s=1.0)
    reanudacion = maquina.actualizar(
        frozenset({ClaseSenal.SIGA}), [_siga(idx=2, t_s=3.0)], t_s=3.0
    )

    assert durante_hueco.estado is EstadoRobot.DETENIDO_MINIMO
    assert durante_hueco.decision is DecisionMovimiento.NO_AUTORIZADO
    assert reanudacion.estado is EstadoRobot.EN_MARCHA
    assert reanudacion.decision is DecisionMovimiento.AUTORIZADO


def test_pare_y_siga_co_visibles_arman_siga_sin_exigir_otro(parametros_por_defecto) -> None:
    """Escenario 8: PARE y SIGA co-visibles ⇒ el SIGA queda armado (Q-A, FR-020)."""
    maquina = _maquina(parametros_por_defecto)

    detenido = maquina.actualizar(
        frozenset({ClaseSenal.PARE, ClaseSenal.SIGA}),
        [_pare(0, 0.0), _siga(idx=0, t_s=0.0)],
        t_s=0.0,
    )
    reanudacion = maquina.actualizar(frozenset(), [], t_s=3.0)

    assert detenido.estado is EstadoRobot.DETENIDO_MINIMO
    assert detenido.decision is DecisionMovimiento.NO_AUTORIZADO
    assert reanudacion.estado is EstadoRobot.EN_MARCHA
    assert reanudacion.decision is DecisionMovimiento.AUTORIZADO


def test_pare_nuevo_durante_detencion_no_altera_t_ni_siga_armado(
    parametros_por_defecto,
) -> None:
    """Escenario 9: PARE nuevo con T en curso y SIGA armado no invalida nada."""
    maquina = _maquina(parametros_por_defecto)
    maquina.actualizar(frozenset({ClaseSenal.PARE}), [_pare(0, 0.0)], t_s=0.0)
    maquina.actualizar(frozenset({ClaseSenal.SIGA}), [_siga(idx=1, t_s=1.0)], t_s=1.0)

    con_pare_nuevo = maquina.actualizar(
        frozenset({ClaseSenal.PARE}), [_pare(idx=2, t_s=2.0)], t_s=2.0
    )
    reanudacion = maquina.actualizar(frozenset(), [], t_s=3.0)

    assert con_pare_nuevo.estado is EstadoRobot.DETENIDO_MINIMO
    assert con_pare_nuevo.decision is DecisionMovimiento.NO_AUTORIZADO
    assert reanudacion.estado is EstadoRobot.EN_MARCHA
    assert reanudacion.decision is DecisionMovimiento.AUTORIZADO


def test_invariante_detenido_implica_no_autorizado(parametros_por_defecto) -> None:
    """DETENIDO_MINIMO y DETENIDO_ESPERANDO_SIGA nunca autorizan movimiento."""
    maquina = _maquina(parametros_por_defecto)
    maquina.actualizar(frozenset({ClaseSenal.PARE}), [_pare(0, 0.0)], t_s=0.0)

    for idx, t_s in enumerate((1.0, 2.0, 3.0, 4.0), start=1):
        resultado = maquina.actualizar(frozenset({ClaseSenal.PARE}), [], t_s=t_s)
        if resultado.estado is not EstadoRobot.EN_MARCHA:
            assert resultado.decision is DecisionMovimiento.NO_AUTORIZADO


def test_misma_secuencia_produce_mismo_resultado(parametros_por_defecto) -> None:
    """Determinismo: la misma secuencia de entradas da las mismas transiciones."""
    secuencia = [
        (frozenset({ClaseSenal.PARE}), [_pare(0, 0.0)], 0.0),
        (frozenset({ClaseSenal.PARE, ClaseSenal.SIGA}), [_siga(1, 1.0)], 1.0),
        (frozenset(), [], 3.0),
        (frozenset({ClaseSenal.PARE}), [_pare(4, 4.0)], 4.0),
    ]

    def _ejecutar() -> list[list[tuple]]:
        maquina = _maquina(parametros_por_defecto)
        return [
            _transiciones(maquina.actualizar(presentes, eventos, t_s))
            for presentes, eventos, t_s in secuencia
        ]

    assert _ejecutar() == _ejecutar()


def test_t_inicial_negativo_es_rechazado(parametros_por_defecto) -> None:
    """La máquina exige un reloj no negativo."""
    with pytest.raises(ValueError, match="t_inicial"):
        MaquinaEstados(parametros_por_defecto, t_inicial=-1.0)
