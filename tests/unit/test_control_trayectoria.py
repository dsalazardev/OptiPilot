"""Tests de la ley de control de trayectoria con zona muerta e histéresis.

Cubre el Objetivo 4 del Reto 1: convertir la posición lateral estimada en un
comando de movimiento, sin chattering y con un fallo seguro.

El módulo bajo prueba es ``ControlTrayectoria.decidir``. Todos los umbrales que
usa salen de la configuración (``zona_muerta``, ``histeresis``,
``n_gracia_busqueda``); los tests los fijan explícitamente para que un cambio de
default se note aquí.

Grupos:
- T016: la tabla de decisión completa, included/excluded en los bordes
- T017: histéresis (el test que falla si se implementa sin ella)
- T018: sostenimiento del comando con error grande y constante
- T019: fallo seguro
- T020: recuperación y memoria del último lado
- 003: cruce de señal (la señal tapa la línea; no es una pérdida de pista)
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from src.vision.configuracion import ParametrosConfiguracion
from src.vision.control_trayectoria import ControlTrayectoria
from src.vision.modelos import (
    CausaComando,
    ClaseSenal,
    ComandoMovimiento,
    Lado,
    PosicionLinea,
)

# Parámetros del test. Con estos valores: z - h = 0.07 y z + h = 0.13.
ZONA = 0.10
HIST = 0.03
GRACIA = 5
X_OBJETIVO = 0.5
ANCHO = 478

UMBRAL_BAJO = ZONA - HIST  # 0.07 -> por debajo, AVANZAR
UMBRAL_ALTO = ZONA + HIST  # 0.13 -> por encima, corrección

#: ``x_rearme`` por defecto (fotogramas sin ver la señal antes de rearmar) y la
#: gracia larga del cruce, en tamaños cortos para los tests.
SIN_VER = 5
AUSENCIA_LARGA = 12


def _control(**kw: object) -> ControlTrayectoria:
    valores: dict[str, object] = {
        "x_objetivo": X_OBJETIVO,
        "zona_muerta": ZONA,
        "histeresis": HIST,
        "n_gracia_busqueda": GRACIA,
        "x_rearme_cruce": AUSENCIA_LARGA,
    }
    valores.update(kw)
    return ControlTrayectoria(ParametrosConfiguracion(**valores))  # type: ignore[arg-type]


def _pos(error: float) -> PosicionLinea:
    """Posición **válida** con el error normalizado indicado."""
    x_norm = X_OBJETIVO + error
    return PosicionLinea(
        x_px=x_norm * ANCHO,
        x_norm=x_norm,
        error_norm=error,
        ancho_banda_px=55.0,
        confianza=0.9,
        valida=True,
    )


def _perdida() -> PosicionLinea:
    """Posición **inválida**: la línea no está (invariante FR-006)."""
    return PosicionLinea(
        x_px=None,
        x_norm=None,
        error_norm=None,
        ancho_banda_px=0.0,
        confianza=0.0,
        valida=False,
    )


# ---------------------------------------------------------------------------
# T016 — la tabla de decisión completa
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("error", [0.0, 0.01, -0.01, 0.05, -0.05, UMBRAL_BAJO, -UMBRAL_BAJO])
def test_dentro_de_la_zona_muerta_avanza(error: float) -> None:
    """|e| <= z - h ⟹ AVANZAR, con pertenencia **inclusiva** en el borde."""
    d = _control().decidir(_pos(error))
    assert d.comando is ComandoMovimiento.AVANZAR
    assert d.causa is CausaComando.SEGUIMIENTO


@pytest.mark.parametrize("error", [UMBRAL_ALTO, 0.2, 0.45, -UMBRAL_ALTO, -0.2, -0.45])
def test_fuera_de_la_banda_corrige_hacia_el_lado_del_error(error: float) -> None:
    """|e| >= z + h ⟹ corrección, y el lado lo fija el **signo** del error."""
    d = _control().decidir(_pos(error))
    esperado = ComandoMovimiento.DERECHA if error > 0 else ComandoMovimiento.IZQUIERDA
    esperado_causa = (
        CausaComando.CORRECCION_DERECHA if error > 0 else CausaComando.CORRECCION_IZQUIERDA
    )
    assert d.comando is esperado
    assert d.causa is esperado_causa


def test_error_positivo_significa_linea_a_la_derecha_del_objetivo() -> None:
    """``e = x_norm - x_objetivo > 0`` ⟹ la línea está a la derecha (FR-004)."""
    d = _control().decidir(_pos(0.30))
    assert d.comando is ComandoMovimiento.DERECHA
    assert d.lateral is not None and d.lateral.lado is Lado.DERECHA


def test_error_negativo_significa_linea_a_la_izquierda_del_objetivo() -> None:
    d = _control().decidir(_pos(-0.30))
    assert d.comando is ComandoMovimiento.IZQUIERDA
    assert d.lateral is not None and d.lateral.lado is Lado.IZQUIERDA


@pytest.mark.parametrize(
    "error_de_banda",
    [0.0701, 0.09, 0.11, 0.1299, -0.0701, -0.09, -0.11, -0.1299],
)
def test_en_la_banda_intermedia_se_mantiene_el_comando_anterior(error_de_banda: float) -> None:
    """z - h < |e| < z + h ⟹ se mantiene el comando previo (Q12)."""
    control = _control()
    control.decidir(_pos(0.0))  # AVANZAR como historial
    d = control.decidir(_pos(error_de_banda))
    assert d.comando is ComandoMovimiento.AVANZAR
    assert d.causa is CausaComando.SEGUIMIENTO


def test_el_borde_exterior_de_la_banda_ya_corrige() -> None:
    """z + h es inclusivo por fuera: a partir de ahí se corrige."""
    control = _control()
    control.decidir(_pos(0.0))
    d = control.decidir(_pos(UMBRAL_ALTO))
    assert d.comando is ComandoMovimiento.DERECHA
    assert d.causa is CausaComando.CORRECCION_DERECHA


def test_sin_historia_previa_la_banda_arranca_en_avanzar() -> None:
    """Primer fotograma y error en la banda: avanzar es la salida segura.

    La tabla de decisión deja este caso con «—» en la columna de memoria, así
    que el comportamiento se fija explícitamente aquí: sin un comando anterior
    que mantener, no se inventa una corrección.
    """
    d = _control().decidir(_pos(0.10))
    assert d.comando is ComandoMovimiento.AVANZAR
    assert d.causa is CausaComando.SEGUIMIENTO


# ---------------------------------------------------------------------------
# T017 — histéresis
# ---------------------------------------------------------------------------


def test_alternar_en_la_banda_no_produce_ningun_cambio_de_comando() -> None:
    """50 fotogramas alternando 0.09 y 0.11 dentro de la banda: cero cambios.

    Es el test que falla si se implementa la zona muerta sin histéresis: con un
    solo umbral, el error cruzaría el umbral de corrección en cada pico y el
    comando alternaría entre AVANZAR y DERECHA docenas de veces.
    """
    control = _control()
    control.decidir(_pos(0.0))
    comandos = [control.decidir(_pos(0.09 if i % 2 else 0.11)).comando for i in range(50)]
    assert set(comandos) == {ComandoMovimiento.AVANZAR}
    assert len(comandos) == 50


def test_la_correccion_se_mantiene_al_volver_a_la_banda() -> None:
    """La histéresis también frena el regreso prematuro a AVANZAR (Q12)."""
    control = _control()
    assert control.decidir(_pos(0.25)).comando is ComandoMovimiento.DERECHA
    #|Baja a la banda sin cruzar z - h: sigue corrigiendo.
    for error in (0.12, 0.10, 0.08, 0.071):
        assert control.decidir(_pos(error)).comando is ComandoMovimiento.DERECHA
    # Al cruzar z - h sí vuelve a avanzar.
    assert control.decidir(_pos(UMBRAL_BAJO)).comando is ComandoMovimiento.AVANZAR


def test_la_histeresis_impide_la_alternancia_entre_lados() -> None:
    """Un error que cruza el cero dentro de la banda no hace girar el comando."""
    control = _control()
    control.decidir(_pos(0.20))  # DERECHA
    comandos = [control.decidir(_pos(0.08 if i % 2 else -0.08)).comando for i in range(20)]
    assert set(comandos) == {ComandoMovimiento.DERECHA}


# ---------------------------------------------------------------------------
# T018 — sostenimiento (FR-015)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("error,esperado", [(0.30, ComandoMovimiento.DERECHA), (-0.30, ComandoMovimiento.IZQUIERDA)])
def test_error_grande_y_constante_mantiene_un_unico_comando(error: float, esperado: ComandoMovimiento) -> None:
    """Con error grande y constante no hay alternancia entre lados (FR-015)."""
    control = _control()
    comandos = [control.decidir(_pos(error)) for _ in range(20)]
    assert {d.comando for d in comandos} == {esperado}
    assert len({d.comando for d in comandos}) == 1


def test_la_causa_no_alterna_con_el_error_constante() -> None:
    control = _control()
    causas = {control.decidir(_pos(0.30)).causa for _ in range(20)}
    assert causas == {CausaComando.CORRECCION_DERECHA}


# ---------------------------------------------------------------------------
# T019 — fallo seguro (FR-025, Q8/Q9)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "posicion_rota",
    [
        object(),
        SimpleNamespace(valida=True),
        SimpleNamespace(valida=True, error_norm=None),
        SimpleNamespace(valida=True, error_norm=float("nan")),
        SimpleNamespace(valida=True, error_norm="0.2"),
        SimpleNamespace(valida=True, error_norm=True),
    ],
)
def test_un_estado_inconsistente_produce_detener_con_fallo_seguro(posicion_rota: object) -> None:
    """Nada de lo que llegue con forma de posición puede romper el control.

    ``PosicionLinea`` garantiza que una posición válida trae ``error_norm``, así
    que estos casos no se pueden construir por la vía normal: se fabrican a
    propósito, porque el requisito (FR-025) es que el control sea robusto
    frente a lo que le llegue, no frente a lo que su propio contrato permite.
    """
    d = _control().decidir(posicion_rota)  # type: ignore[arg-type]
    assert d.comando is ComandoMovimiento.DETENER
    assert d.causa is CausaComando.FALLO_SEGURO


def test_una_excepcion_interna_se_convierte_en_fallo_seguro() -> None:
    """Q8: una excepción interna nunca llega al consumidor."""

    class PosicionQueExplota:
        valida = True

        @property
        def error_norm(self) -> float:
            raise RuntimeError("fallo interno simulado")

    d = _control().decidir(PosicionQueExplota())  # type: ignore[arg-type]
    assert d.comando is ComandoMovimiento.DETENER
    assert d.causa is CausaComando.FALLO_SEGURO


def test_decidir_siempre_devuelve_una_decision() -> None:
    """Q9: nunca ``None``, ni en la posición inválida ni en la válida."""
    control = _control()
    for posicion in (_pos(0.0), _pos(0.4), _perdida(), _pos(0.1)):
        d = control.decidir(posicion)
        assert isinstance(d.comando, ComandoMovimiento)
        assert isinstance(d.causa, CausaComando)


def test_un_error_no_finito_se_trata_como_fallo_seguro() -> None:
    """Un error infinito o NaN no puede compararse con los umbrales."""
    for error in (math.inf, -math.inf, math.nan):
        d = _control().decidir(SimpleNamespace(valida=True, error_norm=error))  # type: ignore[arg-type]
        assert d.comando is ComandoMovimiento.DETENER
        assert d.causa is CausaComando.FALLO_SEGURO


def test_el_control_solo_acepta_una_posicion_valida_como_tal() -> None:
    """``valida=False`` con error presente también es estado inconsistente."""
    d = _control().decidir(SimpleNamespace(valida=False, error_norm=0.2))  # type: ignore[arg-type]
    # La ruta inválida no necesita el error, así que se trata como pérdida normal.
    assert d.comando is ComandoMovimiento.DETENER
    assert d.causa is CausaComando.PERDIDA_SIN_MEMORIA


# ---------------------------------------------------------------------------
# T020 — recuperación (US3) y memoria del último lado
# ---------------------------------------------------------------------------


def test_perdida_sin_memoria_detiene_de_inmediato() -> None:
    """Sin lado conocido no hay hacia dónde buscar: parada segura."""
    d = _control().decidir(_perdida())
    assert d.comando is ComandoMovimiento.DETENER
    assert d.causa is CausaComando.PERDIDA_SIN_MEMORIA
    assert d.lateral is None


def test_busca_hacia_el_ultimo_lado_durante_la_gracia() -> None:
    """N fotogramas de gracia: un comando de búsqueda, no una parada."""
    control = _control()
    control.decidir(_pos(0.30))  # memoria: DERECHA
    for n in range(1, GRACIA + 1):
        d = control.decidir(_perdida())
        assert d.comando is ComandoMovimiento.DERECHA
        assert d.causa is CausaComando.RECUPERACION
        assert d.lateral is not None
        assert d.lateral.lado is Lado.DERECHA
        assert d.lateral.fotogramas_perdidos == n


def test_la_gracia_es_exactamente_n_fotogramas_y_luego_detiene() -> None:
    """En el fotograma N+1 se emite DETENER con GRACIA_AGOTADA (FR-020)."""
    control = _control()
    control.decidir(_pos(0.30))
    for _ in range(GRACIA):
        assert control.decidir(_perdida()).causa is CausaComando.RECUPERACION
    d = control.decidir(_perdida())
    assert d.comando is ComandoMovimiento.DETENER
    assert d.causa is CausaComando.GRACIA_AGOTADA


def test_la_memoria_queda_congelada_tras_agotar_la_gracia() -> None:
    """El contador no sigue creciendo: N+1 es el dato del fallo (data-model §3)."""
    control = _control()
    control.decidir(_pos(0.30))
    for _ in range(GRACIA + 1):
        control.decidir(_perdida())
    d = control.decidir(_perdida())
    assert d.lateral is not None
    assert d.lateral.fotogramas_perdidos == GRACIA + 1
    assert d.lateral.lado is Lado.DERECHA  # se conserva para diagnóstico


def test_la_memoria_no_se_descarta_durante_la_perdida() -> None:
    """Q11: perder la línea no borra el lado conocido."""
    control = _control()
    control.decidir(_pos(-0.30))  # memoria: IZQUIERDA
    for _ in range(GRACIA + 2):
        d = control.decidir(_perdida())
        assert d.lateral is not None and d.lateral.lado is Lado.IZQUIERDA


def test_reaparecer_devuelve_el_mando_normal_y_actualiza_la_memoria() -> None:
    """Volver a ver la línea reinicia el contador y vuelve al mando normal."""
    control = _control()
    control.decidir(_pos(0.30))  # DERECHA
    for _ in range(3):
        control.decidir(_perdida())
    d = control.decidir(_pos(0.30))
    assert d.comando is ComandoMovimiento.DERECHA
    assert d.causa is CausaComando.CORRECCION_DERECHA  # ya no RECUPERACION
    assert d.lateral is not None and d.lateral.fotogramas_perdidos == 0


def test_reaparecer_en_la_banda_no_reinicia_el_mando_de_busqueda() -> None:
    """Tras una recuperación, un error en la banda vuelve a AVANZAR.

    El mando de búsqueda no es un mando de seguimiento: si se guardara como
    «comando anterior», la banda de histéresis reemitiría ``DERECHA`` con causa
    ``RECUPERACION`` aunque la línea ya esté centrada.
    """
    control = _control()
    control.decidir(_pos(0.30))
    for _ in range(2):
        control.decidir(_perdida())
    d = control.decidir(_pos(0.10))  # dentro de la banda
    assert d.comando is ComandoMovimiento.AVANZAR
    assert d.causa is CausaComando.SEGUIMIENTO


def test_reaparecer_en_el_lado_opuesto_invierte_en_el_siguiente_fotograma() -> None:
    """La búsqueda apuntaba a un lado; la línea volvió al otro."""
    control = _control()
    control.decidir(_pos(0.30))  # memoria: DERECHA
    control.decidir(_perdida())  # buscando a la derecha
    d = control.decidir(_pos(-0.30))  # la línea está a la izquierda
    assert d.comando is ComandoMovimiento.IZQUIERDA
    assert d.causa is CausaComando.CORRECCION_IZQUIERDA
    assert d.lateral is not None and d.lateral.lado is Lado.IZQUIERDA


def test_reiniciar_vacia_la_memoria_entre_corridas() -> None:
    """Q13 / FR-023: la memoria no sobrevive de una corrida a otra."""
    control = _control()
    control.decidir(_pos(0.30))
    control.reiniciar()
    d = control.decidir(_perdida())
    assert d.comando is ComandoMovimiento.DETENER
    assert d.causa is CausaComando.PERDIDA_SIN_MEMORIA


def test_reiniciar_tambien_olvida_el_comando_de_seguimiento() -> None:
    """La histéresis tampoco arrastra comandos de la corrida anterior."""
    control = _control()
    control.decidir(_pos(0.30))  # DERECHA
    control.reiniciar()
    d = control.decidir(_pos(0.10))  # banda: sin historial debe avançar
    assert d.comando is ComandoMovimiento.AVANZAR


def test_la_memoria_registra_el_fotograma_de_la_ultima_deteccion() -> None:
    """``fotograma`` es el índice de la última vez que se vio la línea."""
    control = _control()
    for i in range(4):
        d = control.decidir(_pos(0.30))
        assert d.lateral is not None and d.lateral.fotograma == i


def test_error_exacto_cero_no_inventa_un_lado() -> None:
    """Con ``e = 0`` no hay información de lado: el comando es AVANZAR."""
    control = _control()
    d = control.decidir(_pos(0.0))
    assert d.comando is ComandoMovimiento.AVANZAR
    assert d.lateral is None


def test_la_gracia_cero_detiene_en_el_primer_fotograma_perdido() -> None:
    """``n_gracia_busqueda = 0`` significa ``DETENER`` inmediato (data-model)."""
    control = _control(n_gracia_busqueda=0)
    control.decidir(_pos(0.30))
    d = control.decidir(_perdida())
    assert d.comando is ComandoMovimiento.DETENER
    assert d.causa is CausaComando.GRACIA_AGOTADA


# ---------------------------------------------------------------------------
# Feature 003 — cruce de señal: la señal tapa la línea, no es una pérdida
# ---------------------------------------------------------------------------


def test_una_ocurrencia_solo_arma_el_cruce_una_vez() -> None:
    """``ocurrencia_id`` repetido no vuelve a armar el cruce (anti-reproceso)."""
    control = _control()
    assert control.iniciar_cruce(ClaseSenal.PARE, 7) is True
    assert control.cruce_activo is True
    assert control.iniciar_cruce(ClaseSenal.PARE, 7) is False
    assert control.cruce_activo is True
    assert control.iniciar_cruce(ClaseSenal.PARE, 8) is True


def test_en_cruce_la_linea_tapada_avanza_recto_sin_buscar() -> None:
    """Mientras el cartel está encima no hay tope de fotogramas ni búsqueda.

    Sin llamar a ``observar_senal`` la señal se considera siempre presente: el
    cruce sigue y el comando es ``AVANZAR`` conservando la última lateral, nunca
    una recuperación.
    """
    control = _control()
    control.decidir(_pos(0.30))  # memoria: DERECHA
    control.iniciar_cruce(ClaseSenal.SIGA, 0)
    for _ in range(500):
        d = control.decidir(_perdida())
        assert d.comando is ComandoMovimiento.AVANZAR
        assert d.causa is CausaComando.CRUCE_SENAL
        assert d.lateral is not None and d.lateral.lado is Lado.DERECHA
    assert control.cruce_activo is True


def test_en_cruce_no_existen_recuperacion_ni_gracia_agotada() -> None:
    """Ni con la gracia más corta posible: durante el cruce no hay búsqueda."""
    control = _control(n_gracia_busqueda=0)
    control.decidir(_pos(-0.30))
    control.iniciar_cruce(ClaseSenal.PARE, 0)
    causas = {control.decidir(_perdida()).causa for _ in range(50)}
    assert causas == {CausaComando.CRUCE_SENAL}


def test_mientras_la_senal_se_ve_el_cruce_no_termina_aunque_haya_linea() -> None:
    """El cruce no muere al ver la línea: el cartel sigue en pantalla.

    Es el caso del PARE/SIGA que el robot lento tarda en atravesar: la línea
    asoma por un lado, pero si se volviera al seguimiento el cartel taparía la
    pista otra vez y el robot se pondría a girar encima de la señal.
    """
    control = _control()
    control.iniciar_cruce(ClaseSenal.SIGA, 0)
    for _ in range(200):
        control.observar_senal(frozenset({ClaseSenal.SIGA}))
        d = control.decidir(_pos(0.30))  # línea perfectamente visible
        assert d.comando is ComandoMovimiento.AVANZAR
        assert d.causa is CausaComando.CRUCE_SENAL
    assert control.cruce_activo is True


def test_el_cruce_termina_cuando_la_senal_sale_de_pantalla() -> None:
    """Cartel fuera (``x_rearme``) y línea de vuelta: seguimiento normal."""
    control = _control()
    control.iniciar_cruce(ClaseSenal.SIGA, 0)
    control.decidir(_perdida())
    for _ in range(SIN_VER):
        control.observar_senal(frozenset())
    d = control.decidir(_pos(0.30))
    assert control.cruce_activo is False
    assert d.comando is ComandoMovimiento.DERECHA
    assert d.causa is CausaComando.CORRECCION_DERECHA


def test_sin_linea_y_sin_senal_el_cruce_se_corta_por_la_gracia_larga() -> None:
    """Red de seguridad: si la pista no vuelve, el cruce no empuja sin fin."""
    control = _control()
    control.iniciar_cruce(ClaseSenal.SIGA, 0)
    for _ in range(AUSENCIA_LARGA):
        control.observar_senal(frozenset())
        d = control.decidir(_perdida())
    assert control.cruce_activo is False
    assert d.causa is CausaComando.PERDIDA_SIN_MEMORIA


def test_el_cruce_sobrevive_a_la_parada_del_pare() -> None:
    """El veto renueva el aviso y reinicia la ausencia durante los 3 s."""
    control = _control()
    control.iniciar_cruce(ClaseSenal.PARE, 0)
    for _ in range(90):  # 3 s a 30 fps
        assert control.decidir(_pos(0.30)).causa is CausaComando.CRUCE_SENAL
        control.observar_senal(frozenset())  # el cartel ni siquiera se ve
        control.sostener()  # el compositor avisa en cada fotograma vetado
    # Primer fotograma tras T: aún sostenido, sigue el avance del cruce.
    assert control.decidir(_pos(0.30)).causa is CausaComando.CRUCE_SENAL
    # Sin cartel y con línea a la vista, el cruce termina y manda el seguimiento.
    for _ in range(SIN_VER):
        control.observar_senal(frozenset())
    d = control.decidir(_pos(0.30))
    assert d.causa is CausaComando.CORRECCION_DERECHA
    assert control.cruce_activo is False


def test_tras_un_pare_la_gracia_larga_sobrevive_al_fin_del_cruce() -> None:
    """Cerrado el cruce, el PARE sigue bloqueado hasta perderlo de vista."""
    control = _control()
    control.iniciar_cruce(ClaseSenal.PARE, 0)
    control.observar_senal(frozenset({ClaseSenal.PARE}))
    for _ in range(SIN_VER):
        control.observar_senal(frozenset())
        control.decidir(_pos(0.30))
    assert control.cruce_activo is False  # la línea volvió
    assert control.rearme_bloqueado is True  # pero el PARE sigue recordado
    for _ in range(AUSENCIA_LARGA):
        control.observar_senal(frozenset())
        control.decidir(_pos(0.30))
    assert control.rearme_bloqueado is False


def test_un_pare_que_no_se_pierde_de_vista_nunca_desbloquea_el_rearme() -> None:
    """Mientras el cartel se vea (aunque parpadee) no se acepta otro PARE."""
    control = _control()
    control.iniciar_cruce(ClaseSenal.PARE, 0)
    for _ in range(300):
        control.observar_senal(frozenset({ClaseSenal.PARE}))
        control.decidir(_perdida())
        assert control.rearme_bloqueado is True


def test_una_ocurrencia_ya_atendida_no_rearma_el_cruce() -> None:
    """Cerrado el cruce, la misma ocurrencia no vuelve a proteger."""
    control = _control()
    control.iniciar_cruce(ClaseSenal.PARE, 3)
    control.decidir(_perdida())
    for _ in range(SIN_VER):
        control.observar_senal(frozenset())
    control.decidir(_pos(0.0))  # cartel fuera y línea de nuevo: cruce cerrado
    assert control.cruce_activo is False
    assert control.iniciar_cruce(ClaseSenal.PARE, 3) is False
    d = control.decidir(_perdida())
    assert d.causa is CausaComando.PERDIDA_SIN_MEMORIA


def test_una_ocurrencia_nueva_si_arma_un_cruce_nuevo() -> None:
    """Una señal distinta (otro ``ocurrencia_id``) vuelve a proteger."""
    control = _control()
    control.iniciar_cruce(ClaseSenal.PARE, 1)
    control.decidir(_perdida())
    for _ in range(SIN_VER):
        control.observar_senal(frozenset())
    control.decidir(_pos(0.0))
    assert control.iniciar_cruce(ClaseSenal.PARE, 2) is True
    assert control.decidir(_perdida()).causa is CausaComando.CRUCE_SENAL


def test_reiniciar_olvida_el_cruce_y_las_ocurrencias_atendidas() -> None:
    """Entre corridas no sobrevive ni el cruce ni su histórico de ocurrencias."""
    control = _control()
    control.iniciar_cruce(ClaseSenal.PARE, 0)
    control.observar_senal(frozenset({ClaseSenal.PARE}))
    control.reiniciar()
    assert control.cruce_activo is False
    assert control.rearme_bloqueado is False
    assert control.iniciar_cruce(ClaseSenal.PARE, 0) is True
