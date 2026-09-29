"""Tests de ``MetricasControl`` (T032).

Comprueban que las métricas del control derivan de la secuencia de decisiones lo
que la rúbrica necesita para el análisis (criterio 11): cuándo se corrige, cuándo
se pierde la línea, si se recupera, y con qué latencia. No tocan ninguna imagen.
"""

from __future__ import annotations

from src.vision.metricas import MetricasControl
from src.vision.modelos import (
    CausaComando,
    ComandoMovimiento,
    DecisionCompuesta,
    PermisoMovimiento,
    PosicionLinea,
)

ANCHO = 478.0


def _pos(x_px: float = 239.0, *, valida: bool = True) -> PosicionLinea:
    if not valida:
        return PosicionLinea(
            x_px=None, x_norm=None, error_norm=None, ancho_banda_px=0.0, confianza=0.0, valida=False
        )
    return PosicionLinea(
        x_px=x_px,
        x_norm=x_px / ANCHO,
        error_norm=x_px / ANCHO - 0.5,
        ancho_banda_px=55.0,
        confianza=0.9,
        valida=True,
    )


def _decision(
    comando: ComandoMovimiento,
    causa: CausaComando,
    pos: PosicionLinea,
    *,
    permitido: PermisoMovimiento = PermisoMovimiento.AUTORIZADO,
) -> DecisionCompuesta:
    return DecisionCompuesta(comando=comando, causa=causa, posicion=pos, permitido=permitido)


def test_resumen_tiene_todas_las_claves_aunque_no_haya_datos() -> None:
    resumen = MetricasControl().resumen()
    for clave in (
        "correcciones",
        "fotogramas_por_comando",
        "perdidas_linea",
        "recuperaciones_ok",
        "recuperaciones_fallidas",
        "velocidad_error_px_media",
        "velocidad_error_px_p95",
        "velocidad_error_px_max",
        "latencia_decision_ms_media",
    ):
        assert clave in resumen
    assert resumen["correcciones"] == 0
    assert set(resumen["fotogramas_por_comando"]) == {str(c) for c in ComandoMovimiento}


def test_cuenta_fotogramas_por_comando() -> None:
    metricas = MetricasControl()
    metricas.registrar(_decision(ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO, _pos()))
    metricas.registrar(_decision(ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO, _pos()))
    metricas.registrar(
        _decision(ComandoMovimiento.DERECHA, CausaComando.CORRECCION_DERECHA, _pos(300.0))
    )
    assert metricas.resumen()["fotogramas_por_comando"]["AVANZAR"] == 2
    assert metricas.resumen()["fotogramas_por_comando"]["DERECHA"] == 1


def test_las_correcciones_son_transiciones_entre_avanzar_y_lateral() -> None:
    metricas = MetricasControl()
    secuencia = [
        (ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO),
        (ComandoMovimiento.DERECHA, CausaComando.CORRECCION_DERECHA),
        (ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO),
        (ComandoMovimiento.IZQUIERDA, CausaComando.CORRECCION_IZQUIERDA),
    ]
    for comando, causa in secuencia:
        metricas.registrar(_decision(comando, causa, _pos()))
    # AVANZAR->DERECHA, DERECHA->AVANZAR, AVANZAR->IZQUIERDA = 3
    assert metricas.resumen()["correcciones"] == 3


def test_permanecer_en_un_lateral_no_suma_correcciones_extra() -> None:
    """El robot girando durante 10 fotogramas es UNA corrección, no diez."""
    metricas = MetricasControl()
    metricas.registrar(_decision(ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO, _pos()))
    for _ in range(10):
        metricas.registrar(
            _decision(ComandoMovimiento.DERECHA, CausaComando.CORRECCION_DERECHA, _pos(300.0))
        )
    assert metricas.resumen()["correcciones"] == 1


def test_una_sola_perdida_cuenta_aunque_dure_varios_fotogramas() -> None:
    metricas = MetricasControl()
    metricas.registrar(_decision(ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO, _pos()))
    for _ in range(3):
        metricas.registrar(
            _decision(ComandoMovimiento.DETENER, CausaComando.PERDIDA_SIN_MEMORIA, _pos(valida=False))
        )
    assert metricas.resumen()["perdidas_linea"] == 1


def test_recuperacion_ok_cuenta_al_reaparecer_la_linea() -> None:
    metricas = MetricasControl()
    metricas.registrar(_decision(ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO, _pos()))
    metricas.registrar(
        _decision(ComandoMovimiento.IZQUIERDA, CausaComando.RECUPERACION, _pos(valida=False))
    )
    metricas.registrar(_decision(ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO, _pos()))
    resumen = metricas.resumen()
    assert resumen["perdidas_linea"] == 1
    assert resumen["recuperaciones_ok"] == 1
    assert resumen["recuperaciones_fallidas"] == 0


def test_recuperacion_fallida_cuenta_al_agotar_la_gracia() -> None:
    metricas = MetricasControl()
    metricas.registrar(_decision(ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO, _pos()))
    metricas.registrar(
        _decision(ComandoMovimiento.DERECHA, CausaComando.RECUPERACION, _pos(valida=False))
    )
    metricas.registrar(
        _decision(ComandoMovimiento.DETENER, CausaComando.GRACIA_AGOTADA, _pos(valida=False))
    )
    resumen = metricas.resumen()
    assert resumen["recuperaciones_fallidas"] == 1
    assert resumen["recuperaciones_ok"] == 0


def test_la_velocidad_de_error_mide_el_cambio_de_x_entre_fotogramas_validos() -> None:
    metricas = MetricasControl()
    metricas.registrar(_decision(ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO, _pos(200.0)))
    metricas.registrar(_decision(ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO, _pos(215.0)))
    metricas.registrar(_decision(ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO, _pos(205.0)))
    resumen = metricas.resumen()
    assert resumen["velocidades_error_px"] == [15.0, 10.0]
    assert resumen["velocidad_error_px_max"] == 15.0


def test_un_fotograma_invalido_no_aporta_velocidad_y_corta_la_serie() -> None:
    metricas = MetricasControl()
    metricas.registrar(_decision(ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO, _pos(200.0)))
    metricas.registrar(
        _decision(ComandoMovimiento.DETENER, CausaComando.PERDIDA_SIN_MEMORIA, _pos(valida=False))
    )
    metricas.registrar(_decision(ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO, _pos(400.0)))
    # El cambio 200 -> 400 no se cuenta: hubo una pérdida en medio.
    assert metricas.resumen()["velocidades_error_px"] == []


def test_registra_la_latencia_de_decision_cuando_se_informa() -> None:
    metricas = MetricasControl()
    metricas.registrar(
        _decision(ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO, _pos()), latencia_decision_ms=0.5
    )
    metricas.registrar(
        _decision(ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO, _pos()), latencia_decision_ms=1.5
    )
    resumen = metricas.resumen()
    assert resumen["latencias_decision_ms"] == [0.5, 1.5]
    assert resumen["latencia_decision_ms_media"] == 1.0


def test_sin_latencia_informada_la_lista_queda_vacia() -> None:
    metricas = MetricasControl()
    metricas.registrar(_decision(ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO, _pos()))
    assert metricas.resumen()["latencias_decision_ms"] == []


def test_las_metricas_de_control_no_tocan_metricas_corrida() -> None:
    """FR-026: ``MetricasCorrida`` conserva su resumen exacto de 001."""
    from src.vision.metricas import MetricasCorrida

    resumen = MetricasCorrida("c", "f").resumen()
    assert "correcciones" not in resumen
    assert set(resumen) == {
        "corrida_id",
        "fuente",
        "frames_procesados",
        "ocurrencias_pare",
        "ocurrencias_siga",
        "detecciones_correctas",
        "falsos_positivos",
        "confusiones",
        "latencias_frames",
        "latencias_ms",
        "paradas",
        "fps_promedio",
        "latencia_media_ms",
        "latencia_p95_ms",
    }
