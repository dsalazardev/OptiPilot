"""Tests del compositor: el árbitro de seguridad entre control y FSM (T024).

Por qué este módulo existe
--------------------------
En cada fotograma hay **dos** fuentes que quieren decidir el comando del robot:
la ley de control de trayectoria y la máquina de estados PARE/SIGA. Si ambas
tuvieran el mismo rango, un PARE confirmado en el fotograma 812 podría ser
pisado por una corrección de dirección en el mismo instante, y el robot
**giraría en vez de detenerse**. Eso es un fallo de seguridad directo y un
«No cumple» en el criterio PARE de la rúbrica.

El compositor no inventa lógica: aplica una precedencia de tres niveles y deja
constancia de por qué ganó cada comando. La rúbrica premia justamente que esa
precedencia sea demostrable, así que aquí se prueba exhaustivamente en lugar de
con unos pocos casos afortunados.

Norma que atraviesa todo el archivo: la propiedad central es **SC-007**, que
``NO_AUTORIZADO`` ⟹ ``DETENER`` en el 100 % de los casos. Por eso el test
principal barre el producto cartesiano completo, no una muestra.
"""

from __future__ import annotations

import dataclasses
import inspect
import itertools

import pytest

from src.vision.compositor import componer
from src.vision.modelos import (
    CausaComando,
    ComandoMovimiento,
    DecisionCompuesta,
    DecisionControl,
    DecisionMovimiento,
    Lado,
    LadoConocido,
    PermisoMovimiento,
    PosicionLinea,
)


# ---------------------------------------------------------------------------
# Ayudas de construcción
# ---------------------------------------------------------------------------

def posicion_valida(error: float = 0.0) -> PosicionLinea:
    """Posición con línea detectada y un ``error_norm`` dado."""
    x_norm = 0.5 + error
    return PosicionLinea(
        x_px=x_norm * 478.0,
        x_norm=x_norm,
        error_norm=error,
        ancho_banda_px=60.0,
        confianza=0.9,
        valida=True,
    )


def posicion_invalida() -> PosicionLinea:
    """Posición sin línea: por invariante no trae coordenadas (FR-006)."""
    return PosicionLinea(
        x_px=None,
        x_norm=None,
        error_norm=None,
        ancho_banda_px=0.0,
        confianza=0.0,
        valida=False,
    )


def decision(
    comando: ComandoMovimiento = ComandoMovimiento.AVANZAR,
    causa: CausaComando = CausaComando.SEGUIMIENTO,
    lateral: LadoConocido | None = None,
) -> DecisionControl:
    return DecisionControl(comando=comando, causa=causa, lateral=lateral)


def movimiento(veredicto: PermisoMovimiento, causa: str = "PARE_CONFIRMADO") -> DecisionMovimiento:
    return DecisionMovimiento(veredicto=veredicto, causa=causa)


#: Causas que el **control** puede proponer. ``VETO_FSM`` queda fuera a propósito:
#: es un valor reservado al compositor, y el modelo lo prohíbe explícitamente
#: (una decisión con ``VETO_FSM`` y un comando que no sea ``DETENER`` no se puede
#: ni construir). Tratarlo como una causa más del control sería falsear el
#: dominio, así que los barridos usan esta tupla.
CAUSAS_DE_CONTROL = tuple(c for c in CausaComando if c is not CausaComando.VETO_FSM)


# ---------------------------------------------------------------------------
# Nivel 1: el veto de la FSM gana siempre (SC-007, FR-024)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("veredicto", list(PermisoMovimiento))
@pytest.mark.parametrize("comando", list(ComandoMovimiento))
@pytest.mark.parametrize("causa", CAUSAS_DE_CONTROL)
def test_cualquier_veredicto_no_autorizado_produce_detener(
    veredicto: PermisoMovimiento, comando: ComandoMovimiento, causa: CausaComando
) -> None:
    """Barrido **completo**: 2 × 4 × 7 = 56 combinaciones, sin excepción.

    Un solo caso con PARE no probaría SC-007; la propiedad enunciada es
    "siempre", y por eso se comprueba sobre todo el dominio de entrada.
    """
    resultado = componer(decision(comando, causa), movimiento(veredicto), posicion_valida())
    if veredicto is PermisoMovimiento.NO_AUTORIZADO:
        assert resultado.comando is ComandoMovimiento.DETENER
    else:
        assert resultado.comando is comando


def test_el_veto_gana_a_una_correccion_de_direccion() -> None:
    """El caso de seguridad: PARE confirmado mientras el control corrige."""
    resultado = componer(
        decision(ComandoMovimiento.DERECHA, CausaComando.CORRECCION_DERECHA),
        movimiento(PermisoMovimiento.NO_AUTORIZADO, "PARE_CONFIRMADO"),
        posicion_valida(error=0.3),
    )
    assert resultado.comando is ComandoMovimiento.DETENER
    assert resultado.causa is CausaComando.VETO_FSM


def test_el_veto_gana_a_una_propuesta_de_recuperacion() -> None:
    """Buscar la línea con memoria tampoco puede pisar un PARE."""
    lateral = LadoConocido(lado=Lado.IZQUIERDA, fotograma=40, fotogramas_perdidos=2)
    resultado = componer(
        decision(ComandoMovimiento.IZQUIERDA, CausaComando.RECUPERACION, lateral),
        movimiento(PermisoMovimiento.NO_AUTORIZADO, "PARE_CONFIRMADO"),
        posicion_invalida(),
    )
    assert resultado.comando is ComandoMovimiento.DETENER
    assert resultado.causa is CausaComando.VETO_FSM


def test_el_veto_mantiene_la_causa_veto_fsm_aunque_el_control_ya_detuviera() -> None:
    """Precedencia entre las dos paradas: el veto es el que explica el comando.

    Ambos caminos terminan en ``DETENER``, pero la causa distingue *por qué*. Si
    el compositor devolviera aquí la causa del control, en el póster y en las
    métricas aparecerían paradas indistinguibles entre "el control se perdió" y
    "el PARE paró al robot", que es justo lo que SC-007 necesita demostrar.
    """
    resultado = componer(
        decision(ComandoMovimiento.DETENER, CausaComando.PERDIDA_SIN_MEMORIA),
        movimiento(PermisoMovimiento.NO_AUTORIZADO, "PARE_CONFIRMADO"),
        posicion_invalida(),
    )
    assert resultado.comando is ComandoMovimiento.DETENER
    assert resultado.causa is CausaComando.VETO_FSM


def test_la_causa_del_veto_es_siempre_veto_fsm() -> None:
    """FR-027: el motivo queda registrado, cualquiera que sea la causa de la FSM."""
    for causa_fsm in ("PARE_CONFIRMADO", "DETENIDO_MINIMO", "T_CUMPLIDO", "INICIO", ""):
        resultado = componer(
            decision(ComandoMovimiento.IZQUIERDA, CausaComando.CORRECCION_IZQUIERDA),
            movimiento(PermisoMovimiento.NO_AUTORIZADO, causa_fsm),
            posicion_valida(error=-0.3),
        )
        assert resultado.causa is CausaComando.VETO_FSM


# ---------------------------------------------------------------------------
# Nivel 2: con la FSM autorizando, manda el control
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("comando", list(ComandoMovimiento))
def test_autorizado_conserva_el_comando_del_control(comando: ComandoMovimiento) -> None:
    resultado = componer(
        decision(comando, CausaComando.SEGUIMIENTO),
        movimiento(PermisoMovimiento.AUTORIZADO, "INICIO"),
        posicion_valida(),
    )
    assert resultado.comando is comando


@pytest.mark.parametrize("causa", CAUSAS_DE_CONTROL)
def test_autorizado_conserva_la_causa_del_control(causa: CausaComando) -> None:
    """FR-027: sin veto, la causa del comando final es la del control."""
    resultado = componer(
        decision(ComandoMovimiento.DERECHA, causa),
        movimiento(PermisoMovimiento.AUTORIZADO),
        posicion_valida(error=0.2),
    )
    assert resultado.causa is causa


def test_el_control_que_propone_detener_pasa_su_causa_original() -> None:
    """Nivel 2 de la precedencia: la parada del control no se etiqueta como veto."""
    resultado = componer(
        decision(ComandoMovimiento.DETENER, CausaComando.GRACIA_AGOTADA),
        movimiento(PermisoMovimiento.AUTORIZADO, "T_CUMPLIDO"),
        posicion_invalida(),
    )
    assert resultado.comando is ComandoMovimiento.DETENER
    assert resultado.causa is CausaComando.GRACIA_AGOTADA
    assert resultado.causa is not CausaComando.VETO_FSM


@pytest.mark.parametrize(
    "causa_detener",
    [
        CausaComando.PERDIDA_SIN_MEMORIA,
        CausaComando.GRACIA_AGOTADA,
        CausaComando.FALLO_SEGURO,
    ],
)
def test_las_tres_formas_de_detener_del_control_se_preservan(causa_detener: CausaComando) -> None:
    """Son fallos de seguridad distintos y cada uno debe quedar trazado."""
    resultado = componer(
        decision(ComandoMovimiento.DETENER, causa_detener),
        movimiento(PermisoMovimiento.AUTORIZADO),
        posicion_invalida(),
    )
    assert resultado.comando is ComandoMovimiento.DETENER
    assert resultado.causa is causa_detener


# ---------------------------------------------------------------------------
# Propagación de metadatos
# ---------------------------------------------------------------------------


def test_la_posicion_se_propaga_sin_modificarse() -> None:
    """La decisión compuesta lleva la posición tal cual la dio el estimador."""
    pos = posicion_valida(error=0.12)
    resultado = componer(decision(), movimiento(PermisoMovimiento.AUTORIZADO), pos)
    assert resultado.posicion is pos


def test_la_posicion_se_propaga_tambien_con_veto() -> None:
    pos = posicion_valida(error=0.12)
    resultado = componer(decision(), movimiento(PermisoMovimiento.NO_AUTORIZADO), pos)
    assert resultado.posicion is pos


def test_el_permiso_refleja_el_veredicto_de_la_fsm() -> None:
    """``permitido`` documenta si la FSM autorizó, para métricas y evidencia."""
    assert (
        componer(decision(), movimiento(PermisoMovimiento.AUTORIZADO), posicion_valida()).permitido
        is PermisoMovimiento.AUTORIZADO
    )
    assert (
        componer(decision(), movimiento(PermisoMovimiento.NO_AUTORIZADO), posicion_valida()).permitido
        is PermisoMovimiento.NO_AUTORIZADO
    )


# ---------------------------------------------------------------------------
# Invariantes generales (Q16, Q17)
# ---------------------------------------------------------------------------


def test_la_causa_siempre_esta_registrada() -> None:
    """Ninguna decisión compuesta sale sin motivo: siempre auditable."""
    for veredicto, comando, causa in itertools.product(
        PermisoMovimiento, ComandoMovimiento, CAUSAS_DE_CONTROL
    ):
        resultado = componer(decision(comando, causa), movimiento(veredicto), posicion_valida())
        assert isinstance(resultado.causa, CausaComando)
        assert str(resultado.causa)


def test_el_compositor_no_inventa_comandos() -> None:
    """Q17: la salida es el comando del control o ``DETENER``, nunca un quinto valor."""
    for veredicto, comando, causa in itertools.product(
        PermisoMovimiento, ComandoMovimiento, CAUSAS_DE_CONTROL
    ):
        resultado = componer(decision(comando, causa), movimiento(veredicto), posicion_valida())
        assert resultado.comando in {comando, ComandoMovimiento.DETENER}


def test_la_salida_es_inmutable() -> None:
    """``DecisionCompuesta`` es frozen: nadie la reescribe por el camino."""
    resultado = componer(decision(), movimiento(PermisoMovimiento.AUTORIZADO), posicion_valida())
    with pytest.raises(dataclasses.FrozenInstanceError):
        resultado.comando = ComandoMovimiento.DETENER  # type: ignore[misc]


def test_el_compositor_no_muta_sus_entradas() -> None:
    """El compositor es una función pura: ni la decisión ni el movimiento se tocan."""
    entrada_control = decision(ComandoMovimiento.DERECHA, CausaComando.CORRECCION_DERECHA)
    entrada_movimiento = movimiento(PermisoMovimiento.NO_AUTORIZADO)
    antes_control = dataclasses.replace(entrada_control)
    antes_movimiento = dataclasses.replace(entrada_movimiento)

    componer(entrada_control, entrada_movimiento, posicion_valida())

    assert entrada_control == antes_control
    assert entrada_movimiento == antes_movimiento


def test_la_firma_acepta_las_tres_entradas_que_nee_sita_el_resultado() -> None:
    """``DecisionCompuesta`` exige ``posicion``, así que la firma debe recibirla.

    La firma original del contrato era ``componer(decision, movimiento)``, que
    no puede construir el resultado: le faltaba la posición. Este test deja la
    corrección explícita y comprobable en vez de implícita.
    """
    parametros = list(inspect.signature(componer).parameters)
    assert parametros == ["decision", "movimiento", "posicion"]


# ---------------------------------------------------------------------------
# El invariante vive también en el modelo (FR-024, defensa de datos)
# ---------------------------------------------------------------------------


def test_veto_fsm_esta_reservado_al_compositor() -> None:
    """``VETO_FSM`` describe una decisión del compositor, nunca una del control.

    Descubierto al escribir estos tests: barrer ``CausaComando`` entero como
    "causa que el control puede proponer" es incorrecto. El modelo impide
    construir una decisión con ``VETO_FSM`` y un comando distinto de
    ``DETENER``, así que el control no puede emitirlo. Este test deja la
    reserva explícita para que nadie la descubra de nuevo por un ``ValueError``.
    """
    assert CausaComando.VETO_FSM not in CAUSAS_DE_CONTROL
    assert len(CAUSAS_DE_CONTROL) == len(CausaComando) - 1


def test_el_compositor_es_el_unico_productor_de_veto_fsm() -> None:
    """Con veto, la causa siempre es ``VETO_FSM``; sin veto, nunca lo es."""
    for comando in ComandoMovimiento:
        veteado = componer(
            decision(comando, CausaComando.SEGUIMIENTO),
            movimiento(PermisoMovimiento.NO_AUTORIZADO),
            posicion_valida(),
        )
        assert veteado.causa is CausaComando.VETO_FSM

        libre = componer(
            decision(comando, CausaComando.SEGUIMIENTO),
            movimiento(PermisoMovimiento.AUTORIZADO),
            posicion_valida(),
        )
        assert libre.causa is not CausaComando.VETO_FSM


def test_el_modelo_prohibe_construir_un_veto_que_no_sea_detener() -> None:
    """``DecisionCompuesta`` se defiende solo, aunque nadie pase por el compositor."""
    with pytest.raises(ValueError, match="veto"):
        DecisionCompuesta(
            comando=ComandoMovimiento.AVANZAR,
            causa=CausaComando.VETO_FSM,
            posicion=posicion_valida(),
            permitido=PermisoMovimiento.NO_AUTORIZADO,
        )


# ---------------------------------------------------------------------------
# FR-026: ``DecisionMovimiento`` de 001 queda intacto
# ---------------------------------------------------------------------------


def test_decision_movimiento_conserva_su_contrato_de_001() -> None:
    """El compositor consume el tipo de 001, no lo reescribe.

    ``DecisionMovimiento`` es el contrato que consumen las 167 pruebas de la
    feature 001. Si este test falla, se ha roto la frontera entre features.
    """
    campos = [f.name for f in dataclasses.fields(DecisionMovimiento)]
    assert campos == ["veredicto", "causa"]
    assert DecisionMovimiento(PermisoMovimiento.AUTORIZADO, "INICIO").autorizada is True
    assert DecisionMovimiento(PermisoMovimiento.NO_AUTORIZADO, "PARE").autorizada is False
    assert str(DecisionMovimiento(PermisoMovimiento.AUTORIZADO, "INICIO")) == "AUTORIZADO:INICIO"


def test_el_compositor_no_añade_campos_al_veredicto_de_la_fsm() -> None:
    """El veredicto viaja intacto dentro de ``permitido``; no se le añade nada."""
    resultado = componer(
        decision(), movimiento(PermisoMovimiento.NO_AUTORIZADO, "PARE_CONFIRMADO"), posicion_valida()
    )
    assert resultado.permitido is PermisoMovimiento.NO_AUTORIZADO
    assert not hasattr(resultado, "veredicto")


# ---------------------------------------------------------------------------
# Secuencia completa: una vuelta a la pista con PARE y SIGA
# ---------------------------------------------------------------------------


def test_secuencia_de_pista_el_robot_solo_gira_cuando_la_fsm_lo_permite() -> None:
    """Prueba de STORY, no de unidad: la precedencia se sostiene a lo largo del tiempo.

    Reproduce el guion del enunciado (seguir, corregir, perder la línea, recuperar,
    PARE, reanudar con SIGA) y comprueba la propiedad de seguridad sobre la
    secuencia completa, no sobre casos sueltos.
    """
    guion = [
        # (comando del control, causa del control, veredicto FSM, comando esperado, causa esperada)
        (ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO, PermisoMovimiento.AUTORIZADO,
         ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO),
        (ComandoMovimiento.DERECHA, CausaComando.CORRECCION_DERECHA, PermisoMovimiento.AUTORIZADO,
         ComandoMovimiento.DERECHA, CausaComando.CORRECCION_DERECHA),
        (ComandoMovimiento.DETENER, CausaComando.PERDIDA_SIN_MEMORIA, PermisoMovimiento.AUTORIZADO,
         ComandoMovimiento.DETENER, CausaComando.PERDIDA_SIN_MEMORIA),
        (ComandoMovimiento.IZQUIERDA, CausaComando.RECUPERACION, PermisoMovimiento.AUTORIZADO,
         ComandoMovimiento.IZQUIERDA, CausaComando.RECUPERACION),
        (ComandoMovimiento.DERECHA, CausaComando.CORRECCION_DERECHA, PermisoMovimiento.NO_AUTORIZADO,
         ComandoMovimiento.DETENER, CausaComando.VETO_FSM),
        (ComandoMovimiento.DERECHA, CausaComando.CORRECCION_DERECHA, PermisoMovimiento.NO_AUTORIZADO,
         ComandoMovimiento.DETENER, CausaComando.VETO_FSM),
        (ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO, PermisoMovimiento.AUTORIZADO,
         ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO),
    ]

    for comando, causa, veredicto, esperado_comando, esperada_causa in guion:
        resultado = componer(decision(comando, causa), movimiento(veredicto), posicion_valida())
        assert resultado.comando is esperado_comando, f"comando inesperado tras {comando}"
        assert resultado.causa is esperada_causa, f"causa inesperada tras {comando}"

    # La propiedad que sostiene todo el módulo: nunca se gira con PARE activo.
    for comando, causa, veredicto, _, _ in guion:
        if veredicto is PermisoMovimiento.NO_AUTORIZADO:
            salida = componer(decision(comando, causa), movimiento(veredicto), posicion_valida())
            assert salida.comando is ComandoMovimiento.DETENER
