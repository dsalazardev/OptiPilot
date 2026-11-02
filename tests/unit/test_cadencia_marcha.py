"""Tests unitarios de la cadencia de marcha (specs/004)."""

from __future__ import annotations

from src.vision.cadencia_marcha import CadenciaMarcha
from src.vision.configuracion import ParametrosConfiguracion
from src.vision.modelos import ComandoMovimiento, ModoMarcha


def _cadencia() -> CadenciaMarcha:
    return CadenciaMarcha(ParametrosConfiguracion.por_defecto())


def test_primer_avanzar_sale_de_inmediato() -> None:
    cadencia = _cadencia()
    assert cadencia.debe_enviar(ComandoMovimiento.AVANZAR, ModoMarcha.SIGA, 0.0)


def test_siga_espacia_w_un_segundo() -> None:
    cadencia = _cadencia()
    assert cadencia.debe_enviar(ComandoMovimiento.AVANZAR, ModoMarcha.SIGA, 0.0)
    assert not cadencia.debe_enviar(ComandoMovimiento.AVANZAR, ModoMarcha.SIGA, 0.5)
    assert cadencia.debe_enviar(ComandoMovimiento.AVANZAR, ModoMarcha.SIGA, 1.0)


def test_zona_escolar_espacia_w_dos_segundos() -> None:
    cadencia = _cadencia()
    assert cadencia.debe_enviar(ComandoMovimiento.AVANZAR, ModoMarcha.ZONA_ESCOLAR, 0.0)
    assert not cadencia.debe_enviar(
        ComandoMovimiento.AVANZAR, ModoMarcha.ZONA_ESCOLAR, 1.9
    )
    assert cadencia.debe_enviar(
        ComandoMovimiento.AVANZAR, ModoMarcha.ZONA_ESCOLAR, 2.0
    )


def test_velocidad_60_espacia_w_medio_segundo() -> None:
    cadencia = _cadencia()
    assert cadencia.debe_enviar(
        ComandoMovimiento.AVANZAR, ModoMarcha.VELOCIDAD_60, 0.0
    )
    assert not cadencia.debe_enviar(
        ComandoMovimiento.AVANZAR, ModoMarcha.VELOCIDAD_60, 0.49
    )
    assert cadencia.debe_enviar(
        ComandoMovimiento.AVANZAR, ModoMarcha.VELOCIDAD_60, 0.5
    )


def test_una_correccion_permite_el_siguiente_w_inmediato() -> None:
    cadencia = _cadencia()
    assert cadencia.debe_enviar(ComandoMovimiento.AVANZAR, ModoMarcha.SIGA, 0.0)
    assert not cadencia.debe_enviar(ComandoMovimiento.AVANZAR, ModoMarcha.SIGA, 0.2)
    assert cadencia.debe_enviar(ComandoMovimiento.IZQUIERDA, ModoMarcha.SIGA, 0.3)
    assert cadencia.debe_enviar(ComandoMovimiento.AVANZAR, ModoMarcha.SIGA, 0.31)


def test_detener_resetea_la_espera() -> None:
    cadencia = _cadencia()
    assert cadencia.debe_enviar(ComandoMovimiento.AVANZAR, ModoMarcha.SIGA, 0.0)
    assert not cadencia.debe_enviar(ComandoMovimiento.AVANZAR, ModoMarcha.SIGA, 0.2)
    assert cadencia.debe_enviar(ComandoMovimiento.DETENER, ModoMarcha.SIGA, 0.3)
    assert cadencia.debe_enviar(ComandoMovimiento.AVANZAR, ModoMarcha.SIGA, 0.31)


def test_reiniciar_olvida_el_historial() -> None:
    cadencia = _cadencia()
    assert cadencia.debe_enviar(ComandoMovimiento.AVANZAR, ModoMarcha.SIGA, 0.0)
    cadencia.reiniciar()
    assert cadencia.debe_enviar(ComandoMovimiento.AVANZAR, ModoMarcha.SIGA, 0.0)


def test_intervalo_para_cada_modo() -> None:
    cadencia = _cadencia()
    assert cadencia.intervalo_para(ModoMarcha.SIGA) == 1.0
    assert cadencia.intervalo_para(ModoMarcha.ZONA_ESCOLAR) == 2.0
    assert cadencia.intervalo_para(ModoMarcha.VELOCIDAD_60) == 0.5
