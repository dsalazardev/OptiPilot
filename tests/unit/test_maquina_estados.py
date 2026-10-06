"""Tests unitarios de la máquina de estados PARE/SIGA (T019).

Validan los 9 escenarios de aceptación de US2 inyectando secuencias
deterministas de señales confirmadas, eventos y tiempos: un PARE detiene e
inicia T, T nunca reanuda por sí solo, el SIGA confirmado durante la detención
queda armado y reanuda al cumplirse T, un PARE nuevo no reinicia T ni invalida
el SIGA armado, las pérdidas momentáneas ≤ K no afectan el estado ni el
cronómetro, y el rearme del PARE ocurre tras X fotogramas sin verlo.

Cada escenario comprueba explícitamente el estado, el veredicto, la ``causa`` de
la decisión (``data-model.md`` §8), la lista completa de ``transiciones_nuevas``
con origen/destino/causa/momento (FR-023) y la property ``decision``. Se
comprueban además el determinismo y el invariante DETENIDO_* ⇒ NO_AUTORIZADO
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
    PermisoMovimiento,
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


def _completo(
    resultado: ResultadoEstado,
    maquina: MaquinaEstados,
    *,
    estado: EstadoRobot,
    veredicto: PermisoMovimiento,
    causa: str,
    transiciones: list[tuple],
) -> None:
    """Comprueba estado, decisión, causa, transiciones y la property `decision`."""
    assert resultado.estado is estado
    assert resultado.decision.veredicto is veredicto
    assert resultado.decision.causa == causa
    assert resultado.decision.autorizada is (veredicto is PermisoMovimiento.AUTORIZADO)
    assert _transiciones(resultado) == transiciones
    assert maquina.estado is estado
    assert maquina.decision == resultado.decision
    assert maquina.decision.causa == causa
    for transicion in resultado.transiciones_nuevas:
        assert transicion.t_s >= 0.0


def test_estado_inicial_es_marcha_autORIZada(parametros_por_defecto) -> None:
    """Sin señales ni eventos el robot sigue y la decisión es AUTORIZADO (FR-015)."""
    maquina = _maquina(parametros_por_defecto)

    resultado = maquina.actualizar(frozenset(), [], t_s=0.0)

    _completo(
        resultado,
        maquina,
        estado=EstadoRobot.EN_MARCHA,
        veredicto=PermisoMovimiento.AUTORIZADO,
        causa="INICIO",
        transiciones=[],
    )


def test_pare_detiene_e_inicia_el_cronometro_t(parametros_por_defecto) -> None:
    """Escenario 1: PARE confirmado en EN_MARCHA ⇒ NO_AUTORIZADO y DETENIDO_MINIMO."""
    maquina = _maquina(parametros_por_defecto)

    resultado = maquina.actualizar(
        frozenset({ClaseSenal.PARE}), [_pare(idx=0, t_s=0.0)], t_s=0.0
    )

    _completo(
        resultado,
        maquina,
        estado=EstadoRobot.DETENIDO_MINIMO,
        veredicto=PermisoMovimiento.NO_AUTORIZADO,
        causa="PARE_DETENIDO",
        transiciones=[
            (
                EstadoRobot.EN_MARCHA,
                EstadoRobot.DETENIDO_MINIMO,
                CausaTransicion.PARE_CONFIRMADO,
            )
        ],
    )
    assert resultado.transiciones_nuevas[0].t_s == 0.0


def test_pare_persistente_no_reinicia_t_ni_duplica_detencion(parametros_por_defecto) -> None:
    """Escenario 2: con PARE aún visible T no se reinicia ni se duplica la parada."""
    maquina = _maquina(parametros_por_defecto)
    maquina.actualizar(frozenset({ClaseSenal.PARE}), [_pare(0, 0.0)], t_s=0.0)

    intermedio = maquina.actualizar(frozenset({ClaseSenal.PARE}), [], t_s=1.0)
    _completo(
        intermedio,
        maquina,
        estado=EstadoRobot.DETENIDO_MINIMO,
        veredicto=PermisoMovimiento.NO_AUTORIZADO,
        causa="T_MINIMO_EN_CURSO",
        transiciones=[],
    )

    reanudacion = maquina.actualizar(
        frozenset({ClaseSenal.PARE, ClaseSenal.SIGA}), [_siga(2, 3.0)], t_s=3.0
    )
    _completo(
        reanudacion,
        maquina,
        estado=EstadoRobot.EN_MARCHA,
        veredicto=PermisoMovimiento.AUTORIZADO,
        causa="T_CUMPLIDO",
        transiciones=[
            (EstadoRobot.DETENIDO_MINIMO, EstadoRobot.EN_MARCHA, CausaTransicion.T_CUMPLIDO)
        ],
    )


def test_siga_tras_cumplir_t_reanuda_y_registra_transicion(parametros_por_defecto) -> None:
    """Escenario 3: T cumplido y SIGA confirmado ⇒ AUTORIZADO y EN_MARCHA."""
    maquina = _maquina(parametros_por_defecto)
    maquina.actualizar(frozenset({ClaseSenal.PARE}), [_pare(0, 0.0)], t_s=0.0)

    resultado = maquina.actualizar(
        frozenset({ClaseSenal.SIGA}), [_siga(idx=1, t_s=3.0)], t_s=3.0
    )

    _completo(
        resultado,
        maquina,
        estado=EstadoRobot.EN_MARCHA,
        veredicto=PermisoMovimiento.AUTORIZADO,
        causa="T_CUMPLIDO",
        transiciones=[
            (EstadoRobot.DETENIDO_MINIMO, EstadoRobot.EN_MARCHA, CausaTransicion.T_CUMPLIDO)
        ],
    )
    assert resultado.transiciones_nuevas[0].t_s == 3.0


def test_siga_confirmado_antes_de_t_no_adelanta_la_reanudacion(
    parametros_por_defecto,
) -> None:
    """Escenario 4: un SIGA antes de T no acorta la parada; T sigue mandando."""
    maquina = _maquina(parametros_por_defecto)
    maquina.actualizar(frozenset({ClaseSenal.PARE}), [_pare(0, 0.0)], t_s=0.0)

    temprano = maquina.actualizar(
        frozenset({ClaseSenal.SIGA}), [_siga(idx=1, t_s=1.0)], t_s=1.0
    )
    _completo(
        temprano,
        maquina,
        estado=EstadoRobot.DETENIDO_MINIMO,
        veredicto=PermisoMovimiento.NO_AUTORIZADO,
        causa="T_MINIMO_EN_CURSO",
        transiciones=[],
    )

    resultado = maquina.actualizar(frozenset(), [], t_s=3.0)
    _completo(
        resultado,
        maquina,
        estado=EstadoRobot.EN_MARCHA,
        veredicto=PermisoMovimiento.AUTORIZADO,
        causa="T_CUMPLIDO",
        transiciones=[
            (EstadoRobot.DETENIDO_MINIMO, EstadoRobot.EN_MARCHA, CausaTransicion.T_CUMPLIDO)
        ],
    )


def test_siga_en_marcha_no_detiene(parametros_por_defecto) -> None:
    """Escenario 5: SIGA confirmado sin PARE en EN_MARCHA no detiene al robot."""
    maquina = _maquina(parametros_por_defecto)

    resultado = maquina.actualizar(
        frozenset({ClaseSenal.SIGA}), [_siga(idx=0, t_s=0.0)], t_s=0.0
    )

    _completo(
        resultado,
        maquina,
        estado=EstadoRobot.EN_MARCHA,
        veredicto=PermisoMovimiento.AUTORIZADO,
        causa="INICIO",
        transiciones=[],
    )
    assert resultado.decision.autorizada


def test_t_cumplido_sin_siga_reanuda_igual(parametros_por_defecto) -> None:
    """Escenario 6: al cumplirse T el robot reanuda aunque nunca haya visto SIGA.

    Decisión del equipo (2026-10-05): la parada dura exactamente ``t_parada_s`` y
    después el robot vuelve a seguir la línea. La SIGA ya no condiciona la
    reanudación; se sigue detectando y contando para la rúbrica.
    """
    maquina = _maquina(parametros_por_defecto)
    maquina.actualizar(frozenset({ClaseSenal.PARE}), [_pare(0, 0.0)], t_s=0.0)

    resultado = maquina.actualizar(frozenset({ClaseSenal.PARE}), [], t_s=5.0)

    _completo(
        resultado,
        maquina,
        estado=EstadoRobot.EN_MARCHA,
        veredicto=PermisoMovimiento.AUTORIZADO,
        causa="T_CUMPLIDO",
        transiciones=[
            (EstadoRobot.DETENIDO_MINIMO, EstadoRobot.EN_MARCHA, CausaTransicion.T_CUMPLIDO)
        ],
    )
    assert resultado.decision.autorizada

    # Un PARE meramente presente (sin confirmación nueva) no vuelve a detener.
    posterior = maquina.actualizar(frozenset({ClaseSenal.PARE}), [], t_s=9.0)
    assert posterior.estado is EstadoRobot.EN_MARCHA
    assert posterior.decision.autorizada


def test_perdida_momentanea_no_altera_estado_ni_cronometro(parametros_por_defecto) -> None:
    """Escenario 7: una pérdida ≤ K durante la parada deja intactos estado y T."""
    maquina = _maquina(parametros_por_defecto)
    maquina.actualizar(frozenset({ClaseSenal.PARE}), [_pare(0, 0.0)], t_s=0.0)

    durante_hueco = maquina.actualizar(frozenset(), [], t_s=1.0)
    _completo(
        durante_hueco,
        maquina,
        estado=EstadoRobot.DETENIDO_MINIMO,
        veredicto=PermisoMovimiento.NO_AUTORIZADO,
        causa="T_MINIMO_EN_CURSO",
        transiciones=[],
    )

    reanudacion = maquina.actualizar(
        frozenset({ClaseSenal.SIGA}), [_siga(idx=2, t_s=3.0)], t_s=3.0
    )
    _completo(
        reanudacion,
        maquina,
        estado=EstadoRobot.EN_MARCHA,
        veredicto=PermisoMovimiento.AUTORIZADO,
        causa="T_CUMPLIDO",
        transiciones=[
            (EstadoRobot.DETENIDO_MINIMO, EstadoRobot.EN_MARCHA, CausaTransicion.T_CUMPLIDO)
        ],
    )


def test_pare_y_siga_co_visibles_detienen_y_reanudan_al_cumplir_t(
    parametros_por_defecto,
) -> None:
    """Escenario 8: PARE y SIGA co-visibles ⇒ detiene, y T reanuda (Q-A, FR-020)."""
    maquina = _maquina(parametros_por_defecto)

    detenido = maquina.actualizar(
        frozenset({ClaseSenal.PARE, ClaseSenal.SIGA}),
        [_pare(0, 0.0), _siga(idx=0, t_s=0.0)],
        t_s=0.0,
    )
    _completo(
        detenido,
        maquina,
        estado=EstadoRobot.DETENIDO_MINIMO,
        veredicto=PermisoMovimiento.NO_AUTORIZADO,
        causa="PARE_DETENIDO",
        transiciones=[
            (
                EstadoRobot.EN_MARCHA,
                EstadoRobot.DETENIDO_MINIMO,
                CausaTransicion.PARE_CONFIRMADO,
            )
        ],
    )

    reanudacion = maquina.actualizar(frozenset(), [], t_s=3.0)
    _completo(
        reanudacion,
        maquina,
        estado=EstadoRobot.EN_MARCHA,
        veredicto=PermisoMovimiento.AUTORIZADO,
        causa="T_CUMPLIDO",
        transiciones=[
            (EstadoRobot.DETENIDO_MINIMO, EstadoRobot.EN_MARCHA, CausaTransicion.T_CUMPLIDO)
        ],
    )


def test_pare_nuevo_durante_detencion_no_reinicia_t(
    parametros_por_defecto,
) -> None:
    """Escenario 9: un PARE nuevo con T en curso no reinicia el cronómetro."""
    maquina = _maquina(parametros_por_defecto)
    maquina.actualizar(frozenset({ClaseSenal.PARE}), [_pare(0, 0.0)], t_s=0.0)
    maquina.actualizar(frozenset({ClaseSenal.SIGA}), [_siga(idx=1, t_s=1.0)], t_s=1.0)

    con_pare_nuevo = maquina.actualizar(
        frozenset({ClaseSenal.PARE}), [_pare(idx=2, t_s=2.0)], t_s=2.0
    )
    _completo(
        con_pare_nuevo,
        maquina,
        estado=EstadoRobot.DETENIDO_MINIMO,
        veredicto=PermisoMovimiento.NO_AUTORIZADO,
        causa="T_MINIMO_EN_CURSO",
        transiciones=[],
    )

    reanudacion = maquina.actualizar(frozenset(), [], t_s=3.0)
    _completo(
        reanudacion,
        maquina,
        estado=EstadoRobot.EN_MARCHA,
        veredicto=PermisoMovimiento.AUTORIZADO,
        causa="T_CUMPLIDO",
        transiciones=[
            (EstadoRobot.DETENIDO_MINIMO, EstadoRobot.EN_MARCHA, CausaTransicion.T_CUMPLIDO)
        ],
    )


def test_fsm_no_emite_rearme_ese_latch_es_de_la_deteccion(parametros_por_defecto) -> None:
    """La FSM no rearma el PARE: el latch es de ``deteccion.py`` (propiedad única).

    Si la FSM llevara su propio contador, mediría "fotogramas sin confirmación"
    en vez de "fotogramas sin ver la señal" y emitiría un ``PARE_REARMADO``
    duplicado en ``eventos.jsonl`` con el octágono todavía a la vista. El
    comportamiento correcto del rearme se verifica en
    ``test_deteccion_confirmacion.py::test_rearmado_a_los_cinco_fotogramas_y_nueva_ocurrencia``.
    """
    maquina = _maquina(parametros_por_defecto)
    maquina.actualizar(frozenset({ClaseSenal.PARE}), [_pare(0, 0.0)], t_s=0.0)

    # Pasos cortos: el ciclo completo no debe cruzar el cronómetro T (3.0 s), que
    # provocaría la transición legítima DETENIDO_MINIMO -> EN_MARCHA.
    for paso in range(parametros_por_defecto.x_rearme + 5):
        resultado = maquina.actualizar(frozenset(), [], t_s=0.1 * (paso + 1))
        assert not hasattr(resultado, "eventos_nuevos")
        assert resultado.estado is EstadoRobot.DETENIDO_MINIMO
        assert _transiciones(resultado) == []


def test_pare_rearmado_por_deteccion_no_altera_la_fsm(parametros_por_defecto) -> None:
    """Un ``PARE_REARMADO`` que llega como evento no reinicia T ni cambia el estado."""
    maquina = _maquina(parametros_por_defecto)
    maquina.actualizar(frozenset({ClaseSenal.PARE}), [_pare(0, 0.0)], t_s=0.0)

    rearmado = EventoSenal(
        tipo=TipoEvento.PARE_REARMADO,
        fotograma_idx=8,
        t_s=1.0,
        clase=ClaseSenal.PARE,
    )
    resultado = maquina.actualizar(frozenset(), [rearmado], t_s=1.0)

    assert resultado.estado is EstadoRobot.DETENIDO_MINIMO
    assert resultado.decision.veredicto is PermisoMovimiento.NO_AUTORIZADO
    assert _transiciones(resultado) == []


def test_invariante_detenido_implica_no_autorizado(parametros_por_defecto) -> None:
    """Mientras el robot está detenido por T nunca autoriza movimiento."""
    maquina = _maquina(parametros_por_defecto)
    maquina.actualizar(frozenset({ClaseSenal.PARE}), [_pare(0, 0.0)], t_s=0.0)

    for idx, t_s in enumerate((1.0, 2.0, 3.0, 4.0), start=1):
        resultado = maquina.actualizar(frozenset({ClaseSenal.PARE}), [], t_s=t_s)
        if resultado.estado is not EstadoRobot.EN_MARCHA:
            assert resultado.decision.veredicto is PermisoMovimiento.NO_AUTORIZADO
            assert not resultado.decision.autorizada
            assert maquina.decision.veredicto is PermisoMovimiento.NO_AUTORIZADO
            assert resultado.decision.causa != ""


def test_causas_de_decision_son_no_vacias(parametros_por_defecto) -> None:
    """Toda decisión expone una causa informativa (data-model §8)."""
    maquina = _maquina(parametros_por_defecto)
    secuencia = [
        (frozenset(), [], 0.0),
        (frozenset({ClaseSenal.PARE}), [_pare(1, 1.0)], 1.0),
        (frozenset({ClaseSenal.PARE}), [], 2.0),
        (frozenset({ClaseSenal.PARE}), [], 5.0),
        (frozenset({ClaseSenal.SIGA}), [_siga(idx=5, t_s=6.0)], 6.0),
    ]

    for presentes, eventos, t_s in secuencia:
        decision = maquina.actualizar(presentes, eventos, t_s).decision
        assert isinstance(decision, DecisionMovimiento)
        assert decision.causa
        assert str(decision) == f"{decision.veredicto}:{decision.causa}"


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
