"""Tests unitarios de configuración (T008).

Cubren los defaults del contrato, la fusión de JSON parcial (incluidos rangos
anidados), la inmutabilidad y cada regla de validación con su campo/motivo.
"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from src.vision.configuracion import (
    ConfiguracionInvalidaError,
    ParametrosConfiguracion,
    RangoHSV,
    RectanguloNormalizado,
    cargar_parametros,
)


def _escribir(tmp_path: Path, datos: dict) -> Path:
    ruta = tmp_path / "vision.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


def test_por_defecto_tiene_los_valores_del_contrato() -> None:
    parametros = ParametrosConfiguracion.por_defecto()
    assert parametros.t_parada_s == 3.0
    assert (parametros.n_confirmacion, parametros.k_tolerancia, parametros.x_rearme) == (3, 2, 5)
    assert (parametros.vertices_objetivo, parametros.tolerancia_vertices) == (8, 1)
    assert parametros.presupuesto_latencia_frames == 8
    assert parametros.kernel_morfologico_px == 5
    assert parametros.roi_linea == RectanguloNormalizado(0.15, 0.55, 0.70, 0.45)
    assert parametros.roi_senales == RectanguloNormalizado(0.10, 0.05, 0.80, 0.55)
    assert parametros.rangos_hsv_rojo == (
        RangoHSV(0, 10, 120, 255, 90, 255),
        RangoHSV(170, 179, 120, 255, 90, 255),
    )
    assert parametros.rango_hsv_verde == RangoHSV(45, 85, 100, 255, 70, 255)
    assert parametros.rango_hsv_linea == RangoHSV(0, 179, 0, 255, 0, 110)


def test_cargar_sin_ruta_devuelve_defaults() -> None:
    assert cargar_parametros(None) == ParametrosConfiguracion.por_defecto()


def test_fusion_parcial_conserva_defaults(tmp_path: Path) -> None:
    ruta = _escribir(
        tmp_path,
        {"t_parada_s": 5.0, "n_confirmacion": 4, "roi_linea": {"x": 0.2}},
    )
    parametros = cargar_parametros(ruta)
    assert parametros.t_parada_s == 5.0
    assert parametros.n_confirmacion == 4
    assert parametros.roi_linea.x == 0.2
    assert parametros.roi_linea.w == 0.70
    assert parametros.rango_hsv_linea == ParametrosConfiguracion.por_defecto().rango_hsv_linea


def test_fusion_rango_anidado_parcial(tmp_path: Path) -> None:
    ruta = _escribir(tmp_path, {"rango_hsv_verde": {"v_min": 60}})
    parametros = cargar_parametros(ruta)
    assert parametros.rango_hsv_verde.v_min == 60
    assert parametros.rango_hsv_verde.h_min == 45


def test_config_versionado_carga_sin_error() -> None:
    raiz = Path(__file__).resolve().parents[2]
    parametros = cargar_parametros(raiz / "config" / "vision.json")
    assert parametros.t_parada_s == 3.0
    assert parametros.vertices_objetivo == 8


def test_archivo_inexistente_rechazado(tmp_path: Path) -> None:
    with pytest.raises(ConfiguracionInvalidaError) as exc:
        cargar_parametros(tmp_path / "no-existe.json")
    assert exc.value.campo == "<archivo>"
    assert exc.value.motivo


def test_json_invalido_rechazado(tmp_path: Path) -> None:
    ruta = tmp_path / "vision.json"
    ruta.write_text("{ no es json", encoding="utf-8")
    with pytest.raises(ConfiguracionInvalidaError) as exc:
        cargar_parametros(ruta)
    assert exc.value.campo == "<archivo>"


def test_inmutabilidad_de_parametros() -> None:
    parametros = ParametrosConfiguracion.por_defecto()
    with pytest.raises(FrozenInstanceError):
        parametros.t_parada_s = 1.0  # type: ignore[misc]


CASOS_INVALIDOS = [
    ({"kernel_morfologico_px": 4}, "kernel_morfologico_px"),
    ({"kernel_morfologico_px": 1}, "kernel_morfologico_px"),
    ({"area_minima_rel": 0}, "area_minima_rel"),
    ({"area_minima_rel": 1}, "area_minima_rel"),
    ({"n_confirmacion": 0}, "n_confirmacion"),
    ({"k_tolerancia": -1}, "k_tolerancia"),
    ({"x_rearme": -1}, "x_rearme"),
    ({"t_parada_s": -0.5}, "t_parada_s"),
    ({"presupuesto_latencia_frames": 0}, "presupuesto_latencia_frames"),
    ({"fps_objetivo": 0}, "fps_objetivo"),
    ({"vertices_objetivo": 7}, "vertices_objetivo"),
    ({"tolerancia_vertices": -1}, "tolerancia_vertices"),
    ({"aspecto_min": 0.0}, "aspecto_min"),
    ({"aspecto_min": 1.5, "aspecto_max": 1.4}, "aspecto_min"),
    ({"roi_linea": {"x": 0.9, "w": 0.2}}, "roi_linea"),
    ({"roi_senales": {"y": -0.1}}, "roi_senales"),
    ({"roi_linea": {"w": 0.0}}, "roi_linea"),
    ({"rango_hsv_linea": {"h_max": 180}}, "rango_hsv_linea"),
    ({"rango_hsv_linea": {"h_min": 10, "h_max": 5}}, "rango_hsv_linea"),
    ({"rango_hsv_verde": {"s_max": 256}}, "rango_hsv_verde"),
    ({"rango_hsv_verde": {"h_min": 5, "h_max": 20}}, "rango_hsv_verde"),
    (
        {
            "rangos_hsv_rojo": [
                {"h_min": 0, "h_max": 10, "s_min": 120, "s_max": 255, "v_min": 90, "v_max": 255}
            ]
        },
        "rangos_hsv_rojo",
    ),
    ({"campo_desconocido": 1}, "campo_desconocido"),
]


@pytest.mark.parametrize("datos,campo", CASOS_INVALIDOS)
def test_reglas_de_validacion_rechazan(tmp_path: Path, datos: dict, campo: str) -> None:
    ruta = _escribir(tmp_path, datos)
    with pytest.raises(ConfiguracionInvalidaError) as exc:
        cargar_parametros(ruta)
    assert exc.value.campo == campo
    assert exc.value.motivo
