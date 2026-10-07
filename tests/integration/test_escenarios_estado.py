"""Test de integración de escenarios de estado (T025).

Verifica sobre secuencias **end-to-end** las cuatro reglas de la máquina de
estados que gobiernan la parada, alimentándola con la salida real del pipeline
y no con eventos inyectados a mano (que es lo que hace
``tests/unit/test_maquina_estados.py``).

Los escenarios son los que describen la realidad del laboratorio:

1. **Co-visible**: PARE y SIGA visibles a la vez. El PARE detiene; al cumplirse T
   el robot reanuda.
2. **SIGA antes de T**: el SIGA se confirma durante la parada pero no la acorta;
   el robot reanuda al cumplirse T, no antes (FR-017, FR-022).
3. **PARE nuevo durante la detención**: una segunda señal roja no reinicia el
   cronómetro T (spec §Clarifications Q sobre PARE nuevo).
4. **Pérdida ≤ K**: un hueco de hasta K fotogramas no interrumpe la confirmación
   ni reinicia el cronómetro (FR-011, SC-005).

En los cuatro se comprueba el invariante que define el reto: mientras el robot
esté DETENIDO no puede autorizarse a sí mismo, y la única vía de regreso a
EN_MARCHA es que se cumpla el cronómetro T.
"""

from __future__ import annotations

import pytest

from src.vision.configuracion import ParametrosConfiguracion
from src.vision.modelos import EstadoRobot, PermisoMovimiento
from tests.integration._escenarios import (
    TrazaEscenario,
    correr_escenario,
    tramos_a_clases,
)

FPS = 30.0
N_CONFIRMACION = 3
K_TOLERANCIA = 2
TOTAL = 220

#: Fotograma en que se cumple T, con el PARE confirmado en el 12 (t=0,4 s).
F_T_CUMPLIDO = 102


def _t_en(fotograma: int) -> float:
    return fotograma / FPS


@pytest.fixture()
def co_visible(parametros_por_defecto: ParametrosConfiguracion) -> TrazaEscenario:
    """PARE y SIGA visibles simultáneamente desde el fotograma 10."""
    guion = tramos_a_clases(TOTAL, [(10, 200, ["PARE", "SIGA"])])
    return correr_escenario(parametros_por_defecto, guion)


@pytest.fixture()
def siga_antes_de_t(parametros_por_defecto: ParametrosConfiguracion) -> TrazaEscenario:
    """PARE de 10 a 26; el SIGA entra en 40, ya detenida pero antes de cumplir T."""
    guion = tramos_a_clases(TOTAL, [(10, 26, "PARE"), (40, 60, "SIGA")])
    return correr_escenario(parametros_por_defecto, guion)


@pytest.fixture()
def pare_nuevo_durante_parada(
    parametros_por_defecto: ParametrosConfiguracion,
) -> TrazaEscenario:
    """Segundo PARE (86-110) ya pasada la gracia, pero con el robot aún detenido.

    El cartel reaparece después de estar fuera más de ``x_rearme_cruce``
    fotogramas; aun así **no** se convierte en ocurrencia nueva: el cruce sigue
    vivo durante toda la parada (``sostener`` reinicia la ausencia) y la
    reaparición se funde con él. Es el caso del robot lento que vuelve a ver el
    mismo cartel mientras acaba de pasar por encima.
    """
    guion = tramos_a_clases(
        TOTAL, [(10, 26, "PARE"), (86, 110, "PARE"), (150, 170, "SIGA")]
    )
    return correr_escenario(parametros_por_defecto, guion)


@pytest.fixture()
def perdida_dentro_de_k(parametros_por_defecto: ParametrosConfiguracion) -> TrazaEscenario:
    """PARE visible salvo un hueco de K fotogramas (25 y 26)."""
    guion = tramos_a_clases(TOTAL, [(10, 25, "PARE"), (27, 45, "PARE")])
    return correr_escenario(parametros_por_defecto, guion)


def _invariante_sin_autorizacion_espuria(traza: TrazaEscenario) -> None:
    """Ningún fotograma detenido puede autorizar movimiento; solo T reanuda."""
    for indice, estado in enumerate(traza.estados):
        if estado is not EstadoRobot.EN_MARCHA:
            assert traza.veredictos[indice] is PermisoMovimiento.NO_AUTORIZADO, (
                f"autorización espuria en el fotograma {indice} ({estado.value})"
            )
    reanuda = [
        indice
        for indice in range(1, len(traza.estados))
        if traza.estados[indice] is EstadoRobot.EN_MARCHA
        and traza.estados[indice - 1] is not EstadoRobot.EN_MARCHA
    ]
    for indice in reanuda:
        assert traza.causas[indice] == "T_CUMPLIDO", (
            f"reanudación en el fotograma {indice} por causa inesperada "
            f"{traza.causas[indice]!r}"
        )


# --------------------------------------------------------------------------
# 1. Co-visibilidad
# --------------------------------------------------------------------------


def test_co_visible_confirma_ambas_clases_en_el_mismo_fotograma(
    co_visible: TrazaEscenario,
) -> None:
    """Con PARE y SIGA a la vista, las dos confirmaciones salen juntas (N)."""
    assert co_visible.confirmados_por_fotograma[12] == ("PARE", "SIGA")
    assert co_visible.fotogramas_de("PARE_CONFIRMADO") == [12]
    assert co_visible.fotogramas_de("SIGA_CONFIRMADO") == [12]
    for indice in range(10, 12):
        assert co_visible.confirmados_por_fotograma[indice] == ()


def test_co_visible_el_pare_detiene_aunque_haya_siga(co_visible: TrazaEscenario) -> None:
    """El SIGA visible no cancela la parada: el PARE manda (FR-015)."""
    cambios = co_visible.cambios_de_estado()
    assert cambios == [
        (0, "EN_MARCHA", "INICIO"),
        (12, "DETENIDO_MINIMO", "PARE_DETENIDO"),
        (F_T_CUMPLIDO, "EN_MARCHA", "T_CUMPLIDO"),
    ]
    assert co_visible.veredictos[12] is PermisoMovimiento.NO_AUTORIZADO
    _invariante_sin_autorizacion_espuria(co_visible)


def test_co_visible_reanuda_al_cumplir_t(
    co_visible: TrazaEscenario,
) -> None:
    """Con PARE y SIGA a la vista, el robot reanuda en cuanto T se cumple."""
    assert co_visible.causas[F_T_CUMPLIDO] == "T_CUMPLIDO"
    assert co_visible.estados[F_T_CUMPLIDO] is EstadoRobot.EN_MARCHA


# --------------------------------------------------------------------------
# 2. SIGA confirmado antes de cumplir T
# --------------------------------------------------------------------------


def test_siga_antes_de_t_no_interrumpe_la_parada(
    siga_antes_de_t: TrazaEscenario,
) -> None:
    """El SIGA de f42 no reanuda al instante: T es la parada exigida."""
    assert siga_antes_de_t.fotogramas_de("PARE_CONFIRMADO") == [12]
    assert siga_antes_de_t.fotogramas_de("SIGA_CONFIRMADO") == [42]

    for indice in range(42, F_T_CUMPLIDO):
        assert siga_antes_de_t.estados[indice] is EstadoRobot.DETENIDO_MINIMO
        assert siga_antes_de_t.veredictos[indice] is PermisoMovimiento.NO_AUTORIZADO


def test_siga_antes_de_t_reanuda_exactamente_al_cumplir_t(
    siga_antes_de_t: TrazaEscenario,
) -> None:
    """Al cumplirse T el robot reanuda (SC-009)."""
    assert siga_antes_de_t.causas[F_T_CUMPLIDO] == "T_CUMPLIDO"
    assert siga_antes_de_t.estados[F_T_CUMPLIDO] is EstadoRobot.EN_MARCHA
    _invariante_sin_autorizacion_espuria(siga_antes_de_t)


# --------------------------------------------------------------------------
# 3. PARE nuevo durante la detención
# --------------------------------------------------------------------------


def test_pare_nuevo_no_reinicia_el_cronometro_t(
    pare_nuevo_durante_parada: TrazaEscenario,
) -> None:
    """Un segundo PARE se confirma pero T sigue corriendo desde el primero.

    Si el cronómetro se reiniciara, el robot quedaría detenido 3 s más y la
    duración de la parada crecería; el requisito es que T no se reinicia.
    """
    assert pare_nuevo_durante_parada.fotogramas_de("PARE_CONFIRMADO") == [12]
    # T se cumple 3,0 s después del PRIMER PARE (f12 → t 0,4 s), no del segundo.
    assert pare_nuevo_durante_parada.causas[F_T_CUMPLIDO] == "T_CUMPLIDO"
    transiciones_al_cumplir_t = [
        tr for tr in pare_nuevo_durante_parada.transiciones if tr[0] == F_T_CUMPLIDO
    ]
    assert transiciones_al_cumplir_t == [
        (
            F_T_CUMPLIDO,
            "DETENIDO_MINIMO",
            "EN_MARCHA",
            "T_CUMPLIDO",
        )
    ]


def test_pare_nuevo_no_adelanta_la_reanudacion(
    parametros_por_defecto: ParametrosConfiguracion,
) -> None:
    """Un PARE nuevo durante la parada no acorta ni alarga el cronómetro."""
    guion = tramos_a_clases(
        TOTAL, [(10, 26, "PARE"), (40, 60, "SIGA"), (86, 100, "PARE")]
    )
    traza = correr_escenario(parametros_por_defecto, guion)

    assert traza.fotogramas_de("PARE_CONFIRMADO") == [12]
    assert traza.fotogramas_de("SIGA_CONFIRMADO") == [42]
    # El PARE que reaparece se funde con la ocurrencia abierta: T no se reinicia.
    assert traza.causas[F_T_CUMPLIDO] == "T_CUMPLIDO"
    _invariante_sin_autorizacion_espuria(traza)


def test_pare_nuevo_tras_cumplir_t_no_vuelve_a_detener(
    pare_nuevo_durante_parada: TrazaEscenario,
) -> None:
    """Tras reanudar por T, un PARE meramente presente no vuelve a detener."""
    cambios = pare_nuevo_durante_parada.cambios_de_estado()
    assert cambios == [
        (0, "EN_MARCHA", "INICIO"),
        (12, "DETENIDO_MINIMO", "PARE_DETENIDO"),
        (F_T_CUMPLIDO, "EN_MARCHA", "T_CUMPLIDO"),
    ]


# --------------------------------------------------------------------------
# 4. Pérdida dentro de la tolerancia K
# --------------------------------------------------------------------------


def test_perdida_dentro_de_k_no_emite_senal_perdida(
    perdida_dentro_de_k: TrazaEscenario,
) -> None:
    """Un hueco de K=2 fotogramas no cierra la ocurrencia (FR-011, SC-005)."""
    tipos = perdida_dentro_de_k.tipos_de_evento()
    perdidas = [
        indice
        for indice, tipo, clase in perdida_dentro_de_k.eventos
        if tipo == "SENAL_PERDIDA" and clase == "PARE"
    ]
    # La única pérdida corresponde a cuando el PARE sale de verdad (f45 + K).
    assert perdidas == [47]
    assert 25 not in perdidas and 26 not in perdidas
    assert tipos.count("PARE_CONFIRMADO") == 1


def test_perdida_dentro_de_k_no_reinicia_el_cronometro(
    perdida_dentro_de_k: TrazaEscenario,
) -> None:
    """El hueco no altera el estado ni el cronómetro: T se cumple a su tiempo."""
    cambios = perdida_dentro_de_k.cambios_de_estado()
    assert cambios == [
        (0, "EN_MARCHA", "INICIO"),
        (12, "DETENIDO_MINIMO", "PARE_DETENIDO"),
        (F_T_CUMPLIDO, "EN_MARCHA", "T_CUMPLIDO"),
    ]
    _invariante_sin_autorizacion_espuria(perdida_dentro_de_k)


def test_perdida_mayor_que_k_si_interrumpe_la_confirmacion(
    parametros_por_defecto: ParametrosConfiguracion,
) -> None:
    """Con un hueco mayor que K la señal se pierde y debe rearmarse después."""
    guion = tramos_a_clases(
        TOTAL, [(10, 25, "PARE"), (25 + K_TOLERANCIA + 3, 60, "PARE")]
    )
    traza = correr_escenario(parametros_por_defecto, guion)

    perdidas = [
        indice
        for indice, tipo, clase in traza.eventos
        if tipo == "SENAL_PERDIDA" and clase == "PARE"
    ]
    assert perdidas, "un hueco mayor que K debe producir SENAL_PERDIDA"
    assert traza.tipos_de_evento().count("PARE_REARMADO") >= 1
    # La reaparición genera una nueva ocurrencia ⇒ T tampoco se reinicia.
    assert traza.causas[F_T_CUMPLIDO] == "T_CUMPLIDO"


# --------------------------------------------------------------------------
# Invariante común a los cuatro escenarios
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "nombre_escenario",
    [
        "co_visible",
        "siga_antes_de_t",
        "pare_nuevo_durante_parada",
        "perdida_dentro_de_k",
    ],
)
def test_ningun_escenario_autoriza_movimiento_detenido(
    request: pytest.FixtureRequest, nombre_escenario: str
) -> None:
    """En los cuatro escenarios, DETENIDO_* implica NO AUTORIZADO sin excepción."""
    traza: TrazaEscenario = request.getfixturevalue(nombre_escenario)
    _invariante_sin_autorizacion_espuria(traza)

    detenidos = [e for e in traza.estados if e is not EstadoRobot.EN_MARCHA]
    assert detenidos, f"el escenario {nombre_escenario} nunca detiene al robot"
