"""Test de integración de rendimiento y robustez (T028).

Verifica el presupuesto de cómputo por fotograma (SC-002, SC-003) y que el
pipeline degrada sin fallar cuando la imagen no tiene guía (FR-026, FR-027).

Decisión de diseño importante: **el presupuesto se expresa en fotogramas**, no
en milisegundos (``presupuesto_latencia_frames``). El reto evalúa el tiempo de
recorrido del robot, así que el presupuesto se define en la misma unidad del
sistema y se convierte a milisegundos sólo para compararlo con el reloj. Aquí se
hacen las dos conversiones de forma explícita para que la aserción sea legible.

Alcance honesto de estas mediciones: se ejecutan sobre fotogramas sintéticos
640×480, sin decodificar vídeo real. Muestran el coste de la etapa de visión con
margen amplio, pero **no** sustituyen la evidencia de T027 con footage de pista
(latencia de lectura, decodificación y captura incluidas). Por eso el módulo
lleva el marcador ``perf``: se puede excluir con ``-m "not perf"`` sin perder
cobertura funcional.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace

import numpy as np
import pytest

from src.vision.configuracion import ParametrosConfiguracion
from src.vision.pipeline import PipelineVision
from tests.fixtures.generador_sintetico import (
    aplicar_ruido,
    crear_fondo,
    dibujar_linea_vertical,
)

pytestmark = pytest.mark.perf

#: Fotogramas de calentamiento, descartados para no medir el coste de la
#: inicialización perezosa de OpenCV (la primera llamada paga el dispatcher).
FOTOGRAMAS_DE_CALENTAMIENTO = 5
FOTOGRAMAS_MEDIDOS = 60

X_LINEA = 320
GROSOR_LINEA = 24
SEMILLA = 1234
SIGMA_RUIDO = 30.0

ConstructorImagen = Callable[[int], np.ndarray]


def presupuesto_en_ms(params: ParametrosConfiguracion) -> float:
    """Convierte el presupuesto de fotogramas a milisegundos."""
    return params.presupuesto_latencia_frames / params.fps_objetivo * 1000.0


def _percentil(valores: list[float], percentil: float) -> float:
    """Percentil por índice sobre la lista ordenada (sin interpolación)."""
    ordenados = sorted(valores)
    if not ordenados:
        raise ValueError("no hay valores para calcular el percentil")
    posicion = percentil / 100.0 * (len(ordenados) - 1)
    return ordenados[int(round(posicion))]


def medir_latencias(
    params: ParametrosConfiguracion,
    construir: ConstructorImagen,
    medicion: int = FOTOGRAMAS_MEDIDOS,
    calentamiento: int = FOTOGRAMAS_DE_CALENTAMIENTO,
) -> tuple[list[float], list]:
    """Procesa la secuencia y devuelve ``(latencias_ms, resultados)``.

    El reloj es externo al pipeline a propósito: así se puede contrastar la
    latencia que el propio módulo declara con una medida independiente.
    """
    pipeline = PipelineVision(params)
    for indice in range(calentamiento):
        pipeline.procesar(indice, indice / params.fps_objetivo, construir(indice))

    latencias: list[float] = []
    resultados: list = []
    for indice in range(medicion):
        imagen = construir(indice)
        t_s = indice / params.fps_objetivo
        inicio = time.perf_counter()
        resultado = pipeline.procesar(indice, t_s, imagen)
        latencias.append((time.perf_counter() - inicio) * 1000.0)
        resultados.append(resultado)
    return latencias, resultados


def _fotograma_con_linea() -> np.ndarray:
    imagen = crear_fondo()
    dibujar_linea_vertical(imagen, X_LINEA, GROSOR_LINEA)
    return imagen


def _con_ruido(indice: int) -> np.ndarray:
    return aplicar_ruido(_fotograma_con_linea(), SIGMA_RUIDO, SEMILLA + indice)


# --------------------------------------------------------------------------
# Presupuesto: definición y conversión de unidades
# --------------------------------------------------------------------------


def test_el_presupuesto_se_declara_en_fotogramas(
    parametros_por_defecto: ParametrosConfiguracion,
) -> None:
    """La unidad del contrato es el fotograma, no el milisegundo."""
    presupuesto = parametros_por_defecto.presupuesto_latencia_frames
    assert isinstance(presupuesto, int)
    assert presupuesto >= 1
    assert parametros_por_defecto.fps_objetivo == 30.0


def test_la_conversion_de_unidades_es_consistente(
    parametros_por_defecto: ParametrosConfiguracion,
) -> None:
    """8 fotogramas a 30 fps son 266,67 ms de presupuesto por fotograma."""
    assert presupuesto_en_ms(parametros_por_defecto) == pytest.approx(
        parametros_por_defecto.presupuesto_latencia_frames / 30.0 * 1000.0
    )
    assert presupuesto_en_ms(parametros_por_defecto) == pytest.approx(266.67, abs=0.01)


# --------------------------------------------------------------------------
# Presupuesto: margen real
# --------------------------------------------------------------------------


def test_la_latencia_p95_respeta_el_presupuesto(
    parametros_por_defecto: ParametrosConfiguracion,
) -> None:
    latencias, _ = medir_latencias(parametros_por_defecto, lambda _i: _fotograma_con_linea())
    p95 = _percentil(latencias, 95.0)
    presupuesto = presupuesto_en_ms(parametros_por_defecto)
    assert p95 <= presupuesto, f"p95={p95:.2f} ms supera el presupuesto {presupuesto:.2f} ms"


def test_la_latencia_p95_respeta_el_presupuesto_con_ruido(
    parametros_por_defecto: ParametrosConfiguracion,
) -> None:
    """El ruido encarece la morfología pero no debe romper el presupuesto."""
    latencias, _ = medir_latencias(parametros_por_defecto, _con_ruido)
    p95 = _percentil(latencias, 95.0)
    presupuesto = presupuesto_en_ms(parametros_por_defecto)
    assert p95 <= presupuesto, (
        f"p95={p95:.2f} ms con ruido sigma={SIGMA_RUIDO}, "
        f"presupuesto {presupuesto:.2f} ms"
    )


def test_se_inclusive_el_presupuesto_minimo_legal(
    parametros_por_defecto: ParametrosConfiguracion,
) -> None:
    """Aun con el presupuesto más pequeño que admite la validación (1 fotograma)
    el pipeline limpia la imagen sin ruido con holgura."""
    params = replace(parametros_por_defecto, presupuesto_latencia_frames=1)
    latencias, _ = medir_latencias(params, lambda _i: _fotograma_con_linea())
    p95 = _percentil(latencias, 95.0)
    assert p95 <= presupuesto_en_ms(params), (
        f"p95={p95:.2f} ms no cabe en un fotograma ({presupuesto_en_ms(params):.2f} ms)"
    )


def test_el_throughput_real_supera_el_fps_objetivo(
    parametros_por_defecto: ParametrosConfiguracion,
) -> None:
    """Capacidad de cómputo: fotogramas por segundo que el pipeline sostiene.

    Se deriva de la latencia media, no de ``fps_promedio`` (que es una propiedad
    de la línea de tiempo del vídeo; ver el test siguiente).
    """
    for etiqueta, construir in (("limpio", lambda _i: _fotograma_con_linea()), ("con ruido", _con_ruido)):
        latencias, _ = medir_latencias(parametros_por_defecto, construir)
        media_ms = sum(latencias) / len(latencias)
        fps_alcanzados = 1000.0 / media_ms
        assert fps_alcanzados >= parametros_por_defecto.fps_objetivo, (
            f"{etiqueta}: {fps_alcanzados:.0f} fps por debajo del objetivo "
            f"{parametros_por_defecto.fps_objetivo:.0f}"
        )


def test_fps_promedio_describe_el_video_y_no_el_rendimiento() -> None:
    """``fps_promedio`` es ``frames / t_último``: propiedad de la fuente, no del reloj.

    Con ``n`` muestras espaciadas ``1/fps`` el denominador son ``n-1`` intervalos,
    así que el valor excede al nominal en el factor ``n/(n-1)``: 30 muestras a
    30 fps dan 31,03. Es la definición que fija el contrato (y el ejemplo
    ``29.8`` de ``esquema-eventos-metricas.md``), no un error de redondeo, pero
    **no** sirve como prueba de rendimiento. Este test la fija para que nadie la
    cite luego como evidencia de tiempo real; el throughput está en
    ``test_el_throughput_real_supera_el_fps_objetivo``.
    """
    from src.vision.metricas import MetricasCorrida

    metricas = MetricasCorrida(corrida_id="t028", fuente="sintetico")
    for indice in range(30):
        metricas.registrar_fotograma(latencia_ms=1.0, t_s=indice / 30.0)
    resumen = metricas.resumen()

    # 30 muestras sobre 29 intervalos (t_último = 29/30 s).
    assert resumen["fps_promedio"] == pytest.approx(30.0 * 30 / 29, abs=0.01)
    # Aun con latencias de 1 ms el valor no se mueve: no mide el reloj.
    assert resumen["latencia_media_ms"] == pytest.approx(1.0)


def test_fps_promedio_es_cero_sin_avance_de_tiempo() -> None:
    """Sin ``t_s`` no hay línea de tiempo y el valor degrada a 0, no revienta."""
    from src.vision.metricas import MetricasCorrida

    metricas = MetricasCorrida(corrida_id="t028", fuente="sintetico")
    for _ in range(5):
        metricas.registrar_fotograma(latencia_ms=1.0)
    assert metricas.resumen()["fps_promedio"] == 0.0


def test_la_latencia_declarada_por_el_pipeline_es_creible(
    parametros_por_defecto: ParametrosConfiguracion,
) -> None:
    """El pipeline se auto-declara su coste; debe estar dentro del presupuesto."""
    _, resultados = medir_latencias(parametros_por_defecto, lambda _i: _fotograma_con_linea())
    declaradas = [resultado.latencia_ms for resultado in resultados]
    assert declaradas, "el pipeline debe declarar latencia en cada fotograma"
    assert all(valor > 0.0 for valor in declaradas)
    assert max(declaradas) <= presupuesto_en_ms(parametros_por_defecto)


# --------------------------------------------------------------------------
# Degradación sin guía y con entradas hostiles
# --------------------------------------------------------------------------


def test_sin_linea_el_pipeline_no_falla_ni_detecta_senales(
    parametros_por_defecto: ParametrosConfiguracion,
) -> None:
    """Fondo claro: la segmentación de línea sale vacía y no hay señales.

    El fondo por defecto (225,225,225) queda fuera del rango HSV de la línea
    (``v_max=110``), así que la máscara no debe encender ningún píxel.
    """
    _, resultados = medir_latencias(
        parametros_por_defecto, lambda _i: crear_fondo(), medicion=20
    )
    for resultado in resultados:
        assert resultado.senales_confirmadas == []
        assert resultado.eventos == []
        assert not resultado.segmentacion.mascara_linea.any()
        assert not resultado.segmentacion.mascara_roja.any()
        assert not resultado.segmentacion.mascara_verde.any()


def test_sin_linea_la_latencia_sigue_dentro_del_presupuesto(
    parametros_por_defecto: ParametrosConfiguracion,
) -> None:
    """La ausencia de guía es el caso barato: no debe costar más que la línea."""
    latencias, _ = medir_latencias(
        parametros_por_defecto, lambda _i: crear_fondo(), medicion=20
    )
    assert _percentil(latencias, 95.0) <= presupuesto_en_ms(parametros_por_defecto)


def test_el_ruido_no_provoca_detecciones_espurias(
    parametros_por_defecto: ParametrosConfiguracion,
) -> None:
    """Ruido intenso sin señal alguna ⇒ cero ocurrencias (sin falsos positivos)."""
    _, resultados = medir_latencias(
        parametros_por_defecto,
        lambda i: aplicar_ruido(crear_fondo(), SIGMA_RUIDO, SEMILLA + i),
        medicion=30,
    )
    for resultado in resultados:
        assert resultado.senales_confirmadas == []
        assert not [e for e in resultado.eventos if e.tipo.value.endswith("_CONFIRMADO")]


def test_un_fotograma_de_tamano_reducido_no_rompe_el_pipeline(
    parametros_por_defecto: ParametrosConfiguracion,
) -> None:
    """La ROI es normalizada: una imagen pequeña se recorta proporcionalmente."""
    pipeline = PipelineVision(parametros_por_defecto)
    resultado = pipeline.procesar(0, 0.0, np.zeros((10, 10, 3), dtype=np.uint8))
    assert resultado.senales_confirmadas == []
    assert resultado.segmentacion.mascara_linea.shape == (10, 10)
    # roi_linea (0.15, 0.10, 0.70, 0.45) sobre 10×10 ⇒ origen (2, 1) y la caja
    # recortada al borde de la imagen.
    x, y, ancho, alto = resultado.segmentacion.roi_linea
    assert (x, y) == (2, 1)
    assert x + ancho <= 10 and y + alto <= 10


def test_un_fotograma_negro_no_rompe_el_pipeline(
    parametros_por_defecto: ParametrosConfiguracion,
) -> None:
    pipeline = PipelineVision(parametros_por_defecto)
    resultado = pipeline.procesar(0, 0.0, np.zeros((480, 640, 3), dtype=np.uint8))
    assert resultado.senales_confirmadas == []


# --------------------------------------------------------------------------
# Etapas nuevas del control (T042): estimador, control+compositor y cola
# --------------------------------------------------------------------------

#: Umbrales del contrato (``quickstart.md`` §5): el estimador por debajo de 1 ms,
#: control + compositor por debajo de 0.1 ms, ``encolar`` en O(1).
UMBRAL_ESTIMADOR_MS = 1.0
UMBRAL_CONTROL_MS = 0.1
UMBRAL_ENCOLAR_MS = 0.01
UMBRAL_FOTOGRAMA_MS = 33.0  # 30 fps


def test_el_estimador_de_posicion_cuesta_menos_de_un_milisegundo(
    parametros_por_defecto: ParametrosConfiguracion,
) -> None:
    from src.vision.posicion_linea import EstimadorLinea

    pipeline = PipelineVision(parametros_por_defecto)
    estimador = EstimadorLinea(parametros_por_defecto)
    resultados = [
        pipeline.procesar(i, i / 30.0, _con_ruido(i)) for i in range(FOTOGRAMAS_DE_CALENTAMIENTO)
    ] + [pipeline.procesar(i, i / 30.0, _con_ruido(i)) for i in range(FOTOGRAMAS_MEDIDOS)]

    inicio = time.perf_counter()
    for resultado in resultados:
        estimador.aplicar(resultado.segmentacion)
    media_ms = (time.perf_counter() - inicio) * 1000.0 / len(resultados)
    assert media_ms < UMBRAL_ESTIMADOR_MS, f"estimador: {media_ms:.3f} ms"


def test_control_y_compositor_cuestan_menos_de_una_decima_de_milisegundo(
    parametros_por_defecto: ParametrosConfiguracion,
) -> None:
    from src.vision.compositor import componer
    from src.vision.control_trayectoria import ControlTrayectoria
    from src.vision.modelos import DecisionMovimiento, PermisoMovimiento

    pipeline = PipelineVision(parametros_por_defecto)
    control = ControlTrayectoria(parametros_por_defecto)
    movimiento = DecisionMovimiento(PermisoMovimiento.AUTORIZADO, "INICIO")

    preparados = [pipeline.procesar(i, i / 30.0, _fotograma_con_linea()) for i in range(80)]

    inicio = time.perf_counter()
    for resultado in preparados:
        decision = control.decidir(resultado.posicion)
        componer(decision, movimiento, resultado.posicion)
    media_ms = (time.perf_counter() - inicio) * 1000.0 / len(preparados)
    assert media_ms < UMBRAL_CONTROL_MS, f"control+compositor: {media_ms:.4f} ms"


def test_encolar_es_o_uno_y_sin_io(
    parametros_por_defecto: ParametrosConfiguracion,
) -> None:
    from src.transporte.cola import ColaTransporte
    from src.vision.modelos import ComandoMovimiento

    cola = ColaTransporte()
    comandos = list(ComandoMovimiento)
    inicio = time.perf_counter()
    for i in range(1000):
        cola.encolar(comandos[i % len(comandos)])
    media_ms = (time.perf_counter() - inicio) * 1000.0 / 1000
    assert media_ms < UMBRAL_ENCOLAR_MS, f"encolar: {media_ms:.5f} ms"
    # No se drenó nada: encolar no hace E/S.
    assert cola.pendientes() > 0


def test_el_fotograma_completo_cabe_en_33_ms(
    parametros_por_defecto: ParametrosConfiguracion,
) -> None:
    """Presupuesto de tiempo real del contrato: 33 ms por fotograma a 30 fps."""
    latencias, _ = medir_latencias(parametros_por_defecto, _con_ruido)
    p95 = _percentil(latencias, 95.0)
    assert p95 <= UMBRAL_FOTOGRAMA_MS, f"p95={p95:.2f} ms supera los 33 ms"
