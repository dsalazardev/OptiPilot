"""Tests unit de métricas y evidencia por corrida (T023, US4).

Cubren lo que exige el contrato de eventos/métricas: conteos de ocurrencias,
``retardo_s``, la presencia de **todas** las claves con 0 y listas vacías cuando
no aplica, y la serialización de una línea JSON por evento —incluidas las
transiciones ``TRANSICION`` con origen, destino y causa.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.vision.metricas import MetricasCorrida, _percentil
from src.vision.modelos import (
    CausaTransicion,
    ClaseSenal,
    EstadoRobot,
    EventoSenal,
    MarcadorVisibilidadPlena,
    Parada,
    SenalConfirmada,
    TipoEvento,
    TransicionEstado,
)

CLAVES_RESUMEN = {
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


def _senal(clase: str = "PARE", ocurrencia_id: int = 0, indice: int = 10, t_s: float = 0.3) -> SenalConfirmada:
    return SenalConfirmada(
        clase=ClaseSenal(clase),
        centro_px=(320, 140),
        area_rel=0.04,
        fotograma_idx=indice,
        t_s=t_s,
        ocurrencia_id=ocurrencia_id,
    )


def _transicion(desde: str = "EN_MARCHA", hacia: str = "DETENIDO_MINIMO", t_s: float = 1.0) -> TransicionEstado:
    return TransicionEstado(
        desde=EstadoRobot(desde),
        hacia=EstadoRobot(hacia),
        causa=CausaTransicion.PARE_CONFIRMADO,
        fotograma_idx=30,
        t_s=t_s,
    )


def _leer_eventos(ruta: Path) -> list[dict]:
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    return [json.loads(linea) for linea in lineas]


# -- claves y valores por defecto -------------------------------------------


def test_resumen_vacio_no_omite_ninguna_clave() -> None:
    """Regla 2 del contrato: contadores en 0 y listas vacías, nunca sin clave."""
    resumen = MetricasCorrida("demo_01", "videos/pista.mp4").resumen()

    assert set(resumen) == CLAVES_RESUMEN
    assert resumen["corrida_id"] == "demo_01"
    assert resumen["fuente"] == "videos/pista.mp4"
    assert resumen["frames_procesados"] == 0
    assert resumen["ocurrencias_pare"] == 0
    assert resumen["ocurrencias_siga"] == 0
    assert resumen["detecciones_correctas"] == 0
    assert resumen["falsos_positivos"] == 0
    assert resumen["confusiones"] == 0
    assert resumen["latencias_frames"] == []
    assert resumen["latencias_ms"] == []
    assert resumen["paradas"] == []
    assert resumen["fps_promedio"] == 0.0
    assert resumen["latencia_media_ms"] == 0.0
    assert resumen["latencia_p95_ms"] == 0.0


# -- conteos de ocurrencias -------------------------------------------------


def test_conteo_de_ocurrencias_por_clase() -> None:
    metricas = MetricasCorrida("demo_01", "videos/pista.mp4")
    metricas.registrar_senal(_senal("PARE", ocurrencia_id=0))
    metricas.registrar_senal(_senal("PARE", ocurrencia_id=1, indice=200))
    metricas.registrar_senal(_senal("SIGA", ocurrencia_id=2, indice=400))

    resumen = metricas.resumen()

    assert resumen["ocurrencias_pare"] == 2
    assert resumen["ocurrencias_siga"] == 1


def test_ocurrencias_se_deduplican_por_ocurrencia_id() -> None:
    """Las ocurrencias están delimitadas por re-armado, no por fotograma."""
    metricas = MetricasCorrida("demo_01", "videos/pista.mp4")
    for indice in (10, 11, 12):
        metricas.registrar_senal(_senal("PARE", ocurrencia_id=7, indice=indice))

    assert metricas.resumen()["ocurrencias_pare"] == 1


def test_sin_anotacion_no_juzga_acierto_ni_error() -> None:
    """Sin referencia el módulo solo aporta conteos (Regla 3 del contrato)."""
    metricas = MetricasCorrida("demo_01", "videos/pista.mp4")
    metricas.registrar_senal(_senal("PARE"))
    metricas.registrar_senal(_senal("SIGA", ocurrencia_id=1, indice=200))

    resumen = metricas.resumen()

    assert resumen["ocurrencias_pare"] == 1
    assert resumen["ocurrencias_siga"] == 1
    assert resumen["detecciones_correctas"] == 0
    assert resumen["falsos_positivos"] == 0
    assert resumen["confusiones"] == 0


def test_confronta_con_anotacion_correcta_falsa_positiva_y_confusion() -> None:
    metricas = MetricasCorrida("demo_01", "videos/pista.mp4")
    metricas.registrar_senal(_senal("PARE", ocurrencia_id=0), anotada=True)
    metricas.registrar_senal(_senal("SIGA", ocurrencia_id=1, indice=200), anotada=False)
    metricas.registrar_senal(
        _senal("PARE", ocurrencia_id=2, indice=400),
        anotada=True,
        clase_anotada=ClaseSenal.SIGA,
    )

    resumen = metricas.resumen()

    assert resumen["detecciones_correctas"] == 1
    assert resumen["falsos_positivos"] == 1
    assert resumen["confusiones"] == 1


# -- paradas y retardo_s ----------------------------------------------------


def test_parada_calcula_retardo_respecto_al_cumplimiento_de_t() -> None:
    """``retardo_s`` es la espera de SIGA **después** de cumplirse T (SC-008)."""
    parada = Parada.crear(inicio_t=2.0, t_configurado_s=3.0, fin_t=7.5)

    assert parada.retardo_s == pytest.approx(2.5)


def test_parada_sin_retardo_cuando_reanuda_al_cumplirse_t() -> None:
    assert Parada.crear(inicio_t=1.4, t_configurado_s=3.0, fin_t=4.4).retardo_s == 0.0


def test_parada_rechaza_fin_anterior_al_inicio() -> None:
    with pytest.raises(ValueError, match="fin_t no puede ser anterior"):
        Parada(inicio_t=5.0, t_configurado_s=3.0, fin_t=1.0, retardo_s=0.0)


def test_resumen_serializa_las_paradas_completas() -> None:
    metricas = MetricasCorrida("demo_01", "videos/pista.mp4")
    metricas.registrar_parada(Parada.crear(inicio_t=2.0, t_configurado_s=3.0, fin_t=7.5))

    assert metricas.resumen()["paradas"] == [
        {"inicio_t": 2.0, "t_configurado_s": 3.0, "fin_t": 7.5, "retardo_s": 2.5}
    ]


# -- latencias --------------------------------------------------------------


def test_latencia_desde_marcador_de_visibilidad_plena() -> None:
    """La latencia se mide desde visibilidad plena, no desde la primera sighting (Q2)."""
    metricas = MetricasCorrida("demo_01", "videos/pista.mp4")
    marcador = MarcadorVisibilidadPlena(clase=ClaseSenal.PARE, fotograma_idx=10, t_s=1.0)

    metricas.registrar_latencia_desde_marcador(marcador, fotograma_idx=18, t_s=1.6)

    resumen = metricas.resumen()
    assert resumen["latencias_frames"] == [8]
    assert resumen["latencias_ms"] == [pytest.approx(600.0)]


def test_latencia_rechaza_decision_anterior_a_la_visibilidad_plena() -> None:
    metricas = MetricasCorrida("demo_01", "videos/pista.mp4")
    marcador = MarcadorVisibilidadPlena(clase=ClaseSenal.PARE, fotograma_idx=10, t_s=1.0)

    with pytest.raises(ValueError, match="no puede preceder"):
        metricas.registrar_latencia_desde_marcador(marcador, fotograma_idx=4, t_s=0.5)


def test_registrar_fotograma_rechaza_latencia_negativa() -> None:
    with pytest.raises(ValueError, match="latencia_ms debe ser >= 0"):
        MetricasCorrida("demo_01", "videos/pista.mp4").registrar_fotograma(-1.0)


def test_fps_promedio_usa_el_avance_de_t_s() -> None:
    metricas = MetricasCorrida("demo_01", "videos/pista.mp4")
    for indice in range(30):
        metricas.registrar_fotograma(latencia_ms=5.0, t_s=indice / 30.0)

    # 30 fotogramas en ~0.967 s de footage => ~31 fps
    assert metricas.resumen()["fps_promedio"] == pytest.approx(31.0, abs=0.5)
    assert metricas.resumen()["latencia_media_ms"] == pytest.approx(5.0)


def test_percentil_p95_por_interpolacion_lineal() -> None:
    assert _percentil([], 95.0) == 0.0
    assert _percentil([7.0], 95.0) == 7.0
    assert _percentil([float(n) for n in range(1, 101)], 95.0) == pytest.approx(95.05)


# -- exportación ------------------------------------------------------------


def test_exportar_escribe_una_linea_json_por_evento(tmp_path: Path) -> None:
    metricas = MetricasCorrida("demo_01", "videos/pista.mp4")
    metricas.registrar_evento(
        EventoSenal(
            tipo=TipoEvento.PARE_CONFIRMADO,
            fotograma_idx=370,
            t_s=12.34,
            clase=ClaseSenal.PARE,
            ocurrencia_id=3,
            centro_px=(318, 122),
        )
    )
    metricas.registrar_fotograma(20.0, t_s=12.34)

    ruta_eventos, ruta_metricas = metricas.exportar(tmp_path)

    eventos = _leer_eventos(ruta_eventos)
    assert len(eventos) == 1
    assert eventos[0] == {
        "ts": 12.34,
        "frame": 370,
        "tipo": "PARE_CONFIRMADO",
        "clase": "PARE",
        "ocurrencia_id": 3,
        "centro": [318, 122],
    }
    assert json.loads(ruta_metricas.read_text(encoding="utf-8"))["frames_procesados"] == 1


def test_transicion_se_vuelca_como_evento_transicion(tmp_path: Path) -> None:
    """Cada transición de estado se serializa con origen, destino y causa (FR-023)."""
    metricas = MetricasCorrida("demo_01", "videos/pista.mp4")
    metricas.registrar_transicion(_transicion())

    ruta_eventos, _ = metricas.exportar(tmp_path)

    eventos = _leer_eventos(ruta_eventos)
    assert len(eventos) == 1
    assert eventos[0]["tipo"] == "TRANSICION"
    assert eventos[0]["origen"] == "EN_MARCHA"
    assert eventos[0]["destino"] == "DETENIDO_MINIMO"
    assert eventos[0]["causa"] == "PARE_CONFIRMADO"
    assert eventos[0]["clase"] is None
    assert eventos[0]["ocurrencia_id"] is None
    assert eventos[0]["centro"] is None


def test_eventos_no_transicion_omiten_origen_destino_y_causa(tmp_path: Path) -> None:
    metricas = MetricasCorrida("demo_01", "videos/pista.mp4")
    metricas.registrar_evento(
        EventoSenal(
            tipo=TipoEvento.PARE_REARMADO,
            fotograma_idx=12,
            t_s=0.4,
            clase=ClaseSenal.PARE,
        )
    )

    eventos = _leer_eventos(metricas.exportar(tmp_path)[0])

    assert set(eventos[0]) == {"ts", "frame", "tipo", "clase", "ocurrencia_id", "centro"}


def test_eventos_quedan_ordenados_en_el_tiempo(tmp_path: Path) -> None:
    metricas = MetricasCorrida("demo_01", "videos/pista.mp4")
    metricas.registrar_evento(
        EventoSenal(tipo=TipoEvento.SENAL_PERDIDA, fotograma_idx=90, t_s=3.0, clase=ClaseSenal.PARE)
    )
    metricas.registrar_evento(
        EventoSenal(
            tipo=TipoEvento.PARE_CONFIRMADO,
            fotograma_idx=10,
            t_s=0.3,
            clase=ClaseSenal.PARE,
        )
    )
    metricas.registrar_transicion(_transicion(t_s=0.3))

    eventos = _leer_eventos(metricas.exportar(tmp_path)[0])

    assert [evento["ts"] for evento in eventos] == [0.3, 0.3, 3.0]


def test_metricas_json_no_omite_claves_y_crea_el_directorio(tmp_path: Path) -> None:
    destino = tmp_path / "anidado" / "corrida"
    _, ruta_metricas = MetricasCorrida("demo_01", "videos/pista.mp4").exportar(destino)

    assert set(json.loads(ruta_metricas.read_text(encoding="utf-8"))) == CLAVES_RESUMEN
    assert ruta_metricas.parent.is_dir()
