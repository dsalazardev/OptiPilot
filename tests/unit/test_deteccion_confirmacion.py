"""Tests unitarios de detección y confirmación temporal (T016).

Validan el consenso N/K/X del ``Detector`` sobre candidatos sintéticos:
confirmación en ≤ 3 fotogramas con flanco de subida único, pérdidas ≤ 2 que no
revocan, re-armado a los 5 fotogramas (cierra la ocurrencia y permite una
nueva) y ausencia de confusión PARE↔SIGA (FR-011, FR-021, FR-013).
"""

from __future__ import annotations

import pytest

from src.vision.deteccion import Detector
from src.vision.modelos import CandidatoSenal, ClaseSenal, EstadoOcurrencia, TipoEvento


def _candidato(
    clase: ClaseSenal,
    area_rel: float = 0.05,
    valido: bool = True,
) -> CandidatoSenal:
    """Candidato sintético con los campos mínimos del contrato."""
    return CandidatoSenal(
        clase_estimada=clase,
        centro_px=(320, 140),
        area_px=7000,
        area_rel=area_rel,
        n_vertices=8,
        caja_px=(280, 100, 80, 80),
        aspecto=1.0,
        es_valido=valido,
        motivo_invalidez=None if valido else "inválido de prueba",
    )


def _tipos(eventos) -> list[TipoEvento]:
    return [e.tipo for e in eventos]


def _avanzar(
    detector: Detector,
    fotogramas,
    inicio: int = 0,
    permitir_rearme: bool = True,
):
    """Alimenta el detector con una secuencia de listas de candidatos."""
    eventos = []
    presentes = []
    for desplazamiento, candidatos in enumerate(fotogramas):
        indice = inicio + desplazamiento
        resultado = detector.actualizar(
            candidatos, indice, indice * 0.033, permitir_rearme=permitir_rearme
        )
        eventos.extend(resultado.eventos)
        presentes.append(resultado.presentes)
    return eventos, presentes


# ---------------------------------------------------------------------------
# T016 — Confirmación y flanco de subida (US1)
# ---------------------------------------------------------------------------


def test_confirmacion_en_tres_fotogramas_con_flanco_unico(parametros_por_defecto) -> None:
    detector = Detector(parametros_por_defecto)
    eventos, presentes = _avanzar(
        detector,
        [
            [_candidato(ClaseSenal.PARE)],
            [_candidato(ClaseSenal.PARE)],
            [_candidato(ClaseSenal.PARE)],
        ],
    )
    assert presentes == [frozenset(), frozenset(), {ClaseSenal.PARE}]
    confirmaciones = [e for e in eventos if e.tipo is TipoEvento.PARE_CONFIRMADO]
    assert len(confirmaciones) == 1
    assert confirmaciones[0].ocurrencia_id == 0
    assert confirmaciones[0].clase is ClaseSenal.PARE
    assert confirmaciones[0].centro_px == (320, 140)
    assert detector.ocurrencias[0].fotograma_inicio == 2


def test_no_se_reenvia_la_confirmacion_mientras_persiste(parametros_por_defecto) -> None:
    detector = Detector(parametros_por_defecto)
    eventos, _ = _avanzar(detector, [[_candidato(ClaseSenal.PARE)]] * 5)
    assert _tipos(eventos).count(TipoEvento.PARE_CONFIRMADO) == 1
    assert TipoEvento.SENAL_PERDIDA not in _tipos(eventos)


def test_un_hueco_unico_no_reinicia_la_acumulacion(parametros_por_defecto) -> None:
    detector = Detector(parametros_por_defecto)
    eventos, _ = _avanzar(
        detector,
        [
            [_candidato(ClaseSenal.PARE)],
            [_candidato(ClaseSenal.PARE)],
            [],
            [_candidato(ClaseSenal.PARE)],
        ],
    )
    confirmaciones = [e for e in eventos if e.tipo is TipoEvento.PARE_CONFIRMADO]
    assert len(confirmaciones) == 1
    assert confirmaciones[0].fotograma_idx == 3


def test_candidato_invalido_no_confirmado(parametros_por_defecto) -> None:
    detector = Detector(parametros_por_defecto)
    eventos, presentes = _avanzar(
        detector,
        [[_candidato(ClaseSenal.PARE, valido=False)]] * 4,
    )
    assert TipoEvento.PARE_CONFIRMADO not in _tipos(eventos)
    assert presentes[-1] == frozenset()


# ---------------------------------------------------------------------------
# T016 — Pérdidas toleradas (FR-011)
# ---------------------------------------------------------------------------


def test_perdidas_hasta_k_no_revocan_la_confirmacion(parametros_por_defecto) -> None:
    detector = Detector(parametros_por_defecto)
    _avanzar(detector, [[_candidato(ClaseSenal.PARE)]] * 3)
    eventos, presentes = _avanzar(detector, [[], [], []], inicio=3)
    assert presentes == [{ClaseSenal.PARE}, {ClaseSenal.PARE}, frozenset()]
    perdidas = [e.fotograma_idx for e in eventos if e.tipo is TipoEvento.SENAL_PERDIDA]
    assert perdidas == [5]


def test_detecciones_acumuladas_cuenta_fotogramas_confirmados(parametros_por_defecto) -> None:
    detector = Detector(parametros_por_defecto)
    _avanzar(detector, [[_candidato(ClaseSenal.PARE)]] * 5)
    # La confirmación se completa en el fotograma 2: solo 3 de 5 cuentan.
    assert detector.ocurrencias[0].detecciones == 3


# ---------------------------------------------------------------------------
# T016 — Re-armado de ocurrencia (FR-021)
# ---------------------------------------------------------------------------


def test_rearmado_a_los_cinco_fotogramas_y_nueva_ocurrencia(parametros_por_defecto) -> None:
    detector = Detector(parametros_por_defecto)
    eventos = []
    for indice in range(3):
        eventos.extend(
            detector.actualizar([_candidato(ClaseSenal.PARE)], indice, indice * 0.033).eventos
        )
    for indice in range(3, 8):
        eventos.extend(detector.actualizar([], indice, indice * 0.033).eventos)
    rearmados = [e for e in eventos if e.tipo is TipoEvento.PARE_REARMADO]
    assert len(rearmados) == 1
    assert rearmados[0].ocurrencia_id == 0
    assert detector.ocurrencias[0].estado is EstadoOcurrencia.CERRADA
    assert detector.ocurrencias[0].fotograma_fin == 7

    for indice in range(8, 11):
        eventos.extend(
            detector.actualizar([_candidato(ClaseSenal.PARE)], indice, indice * 0.033).eventos
        )
    confirmaciones = [e for e in eventos if e.tipo is TipoEvento.PARE_CONFIRMADO]
    assert [e.ocurrencia_id for e in confirmaciones] == [0, 1]
    assert detector.ocurrencias[1].estado is EstadoOcurrencia.ACTIVA


# ---------------------------------------------------------------------------
# Feature 003 — rearme bloqueado mientras el robot cruza la señal
# ---------------------------------------------------------------------------


def test_sin_rearme_la_ocurrencia_no_se_cierra(parametros_por_defecto) -> None:
    """Con ``permitir_rearme=False`` la señal puede ocultarse sin re-armarse."""
    detector = Detector(parametros_por_defecto)
    _avanzar(detector, [[_candidato(ClaseSenal.PARE)]] * 3)
    eventos, _ = _avanzar(detector, [[]] * 10, inicio=3, permitir_rearme=False)
    assert TipoEvento.PARE_REARMADO not in _tipos(eventos)
    assert detector.ocurrencias[0].estado is EstadoOcurrencia.ACTIVA
    # Al terminar el cruce se permite el rearme y la ocurrencia se cierra.
    eventos, _ = _avanzar(detector, [[]], inicio=13, permitir_rearme=True)
    assert _tipos(eventos).count(TipoEvento.PARE_REARMADO) == 1
    assert detector.ocurrencias[0].estado is EstadoOcurrencia.CERRADA


def test_la_misma_senal_reaparecida_conserva_su_ocurrencia(parametros_por_defecto) -> None:
    """Con el rearme bloqueado, un parpadeo no fragmenta la ocurrencia.

    La re-confirmación se emite con el **mismo** ``ocurrencia_id``: es la misma
    señal física, no una nueva. El pipeline es quien la descarta aguas arriba
    para que no vuelva a detener al robot.
    """
    detector = Detector(parametros_por_defecto)
    _avanzar(detector, [[_candidato(ClaseSenal.PARE)]] * 3)
    _avanzar(detector, [[]] * 8, inicio=3, permitir_rearme=False)
    eventos, presentes = _avanzar(
        detector,
        [[_candidato(ClaseSenal.PARE)]] * 3,
        inicio=11,
        permitir_rearme=False,
    )
    confirmaciones = [e for e in eventos if e.tipo is TipoEvento.PARE_CONFIRMADO]
    assert [e.ocurrencia_id for e in confirmaciones] == [0]
    assert len(detector.ocurrencias) == 1
    assert presentes[-1] == {ClaseSenal.PARE}


# ---------------------------------------------------------------------------
# T016 — Sin confusión PARE↔SIGA
# ---------------------------------------------------------------------------


def test_no_hay_confusion_pare_siga(parametros_por_defecto) -> None:
    detector = Detector(parametros_por_defecto)
    eventos, presentes = _avanzar(detector, [[_candidato(ClaseSenal.PARE)]] * 5)
    assert TipoEvento.SIGA_CONFIRMADO not in _tipos(eventos)
    assert ClaseSenal.SIGA not in presentes[-1]

    detector_siga = Detector(parametros_por_defecto)
    eventos_siga, presentes_siga = _avanzar(
        detector_siga, [[_candidato(ClaseSenal.SIGA)]] * 5
    )
    assert TipoEvento.PARE_CONFIRMADO not in _tipos(eventos_siga)
    assert ClaseSenal.PARE not in presentes_siga[-1]
    assert _tipos(eventos_siga).count(TipoEvento.SIGA_CONFIRMADO) == 1