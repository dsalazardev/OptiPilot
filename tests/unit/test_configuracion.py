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
    assert parametros.roi_linea == RectanguloNormalizado(0.05, 0.10, 0.90, 0.45)
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
        {"t_parada_s": 5.0, "n_confirmacion": 4, "roi_linea": {"h": 0.30}},
    )
    parametros = cargar_parametros(ruta)
    assert parametros.t_parada_s == 5.0
    assert parametros.n_confirmacion == 4
    assert parametros.roi_linea.h == 0.30
    # El ancho no se tocó: conserva el default (ROI ensanchada para las curvas).
    assert parametros.roi_linea.w == 0.90
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


# ---------------------------------------------------------------------------
# Control de trayectoria (specs/002 — T008)
# ---------------------------------------------------------------------------

# (nombre, valor por defecto)
PARAMETROS_CONTROL = [
    ("x_objetivo", 0.5),
    ("frac_anticipacion", 0.40),
    ("frac_pico", 0.50),
    ("umbral_confianza", 0.35),
    ("zona_muerta", 0.10),
    ("histeresis", 0.03),
    ("n_gracia_busqueda", 5),
    ("mac_bluetooth", "00:1B:10:21:2D:C0"),
    ("timeout_transporte_s", 0.20),
]


@pytest.mark.parametrize("campo,esperado", PARAMETROS_CONTROL)
def test_control_tiene_los_diez_parametros_con_su_default(campo: str, esperado: object) -> None:
    assert getattr(ParametrosConfiguracion.por_defecto(), campo) == esperado


def test_los_diez_parametros_de_control_estan_en_config_vision_json() -> None:
    """El JSON versionado y los defaults del código deben coincidir (T006).

    La MAC de Bluetooth queda fuera de la comparación: es un valor por robot que
    el equipo edita para cada mBot (``config/vision.json``), no un default que
    deba coincidir con el código. Su formato sí se valida (regla V5 de
    ``configuracion.py``).
    """
    parametros = cargar_parametros("config/vision.json")
    for campo, esperado in PARAMETROS_CONTROL:
        if campo == "mac_bluetooth":
            continue
        assert getattr(parametros, campo) == esperado, campo


def test_control_no_altera_los_parametros_de_001() -> None:
    """FR-026 / decisión del equipo: ``t_parada_s`` y los umbrales de 001 siguen."""
    parametros = ParametrosConfiguracion.por_defecto()
    assert parametros.t_parada_s == 3.0
    assert (parametros.n_confirmacion, parametros.k_tolerancia, parametros.x_rearme) == (3, 2, 5)
    assert parametros.rango_hsv_linea == RangoHSV(0, 179, 0, 255, 0, 110)
    assert parametros.vertices_objetivo == 8
    assert parametros.roi_linea == RectanguloNormalizado(0.05, 0.10, 0.90, 0.45)


def test_control_se_puede_sobreescribir_desde_json(tmp_path: Path) -> None:
    """Cada parámetro se puede cambiar desde el JSON con un valor válido."""
    valores = {
        "x_objetivo": 0.42,
        "frac_anticipacion": 0.25,
        "frac_pico": 0.6,
        "umbral_confianza": 0.5,
        "zona_muerta": 0.08,
        "histeresis": 0.02,
        "n_gracia_busqueda": 9,
        "mac_bluetooth": "AA:BB:CC:DD:EE:FF",
        "timeout_transporte_s": 0.5,
    }
    parametros = cargar_parametros(_escribir(tmp_path, valores))
    for campo, esperado in valores.items():
        assert getattr(parametros, campo) == esperado, campo


def test_mac_bluetooth_rechaza_un_numero(tmp_path: Path) -> None:
    with pytest.raises(ConfiguracionInvalidaError) as exc:
        cargar_parametros(_escribir(tmp_path, {"mac_bluetooth": 7}))
    assert exc.value.campo == "mac_bluetooth"


def test_mac_bluetooth_rechaza_null_explicito(tmp_path: Path) -> None:
    """A diferencia del puerto COM, la MAC del mBot no es opcional (V5)."""
    with pytest.raises(ConfiguracionInvalidaError) as exc:
        cargar_parametros(_escribir(tmp_path, {"mac_bluetooth": None}))
    assert exc.value.campo == "mac_bluetooth"


# V1–V6 del contrato: cada regla cruzada, con el campo al que se atribuye el rechazo.
REGLAS_CRUZADAS = [
    ("V1 zona_muerta + histeresis <= 0.5", {"zona_muerta": 0.50, "histeresis": 0.05}, "zona_muerta"),
    ("V2 zona_muerta - histeresis >= 0.0", {"zona_muerta": 0.05, "histeresis": 0.10}, "histeresis"),
    ("V3 frac_anticipacion < 1.0", {"frac_anticipacion": 1.0}, "frac_anticipacion"),
    ("V4 frac_pico > 0.0", {"frac_pico": 0.0}, "frac_pico"),
    ("V5 mac_bluetooth con formato MAC", {"mac_bluetooth": "00-1B-10-21-2C-1B"}, "mac_bluetooth"),
    ("V6 timeout_transporte_s > 0.0", {"timeout_transporte_s": 0.0}, "timeout_transporte_s"),
]


@pytest.mark.parametrize("nombre,datos,campo", REGLAS_CRUZADAS)
def test_reglas_cruzadas_V1_V6(
    tmp_path: Path, nombre: str, datos: dict, campo: str
) -> None:
    with pytest.raises(ConfiguracionInvalidaError) as exc:
        cargar_parametros(_escribir(tmp_path, datos))
    assert exc.value.campo == campo, nombre
    assert exc.value.motivo


RANGOS_RECHAZADOS = [
    ("x_objetivo", -0.01),
    ("x_objetivo", 1.01),
    ("frac_anticipacion", -0.1),
    ("frac_pico", 1.5),
    ("umbral_confianza", 1.2),
    ("zona_muerta", 1.2),
    ("histeresis", -0.01),
    ("n_gracia_busqueda", -1),
    ("mac_bluetooth", "   "),
    ("mac_bluetooth", "00:1B:10:21:2C"),
    ("mac_bluetooth", "00:1B:10:21:2C:1B:7F"),
    ("mac_bluetooth", "ZZ:1B:10:21:2C:1B"),
]


@pytest.mark.parametrize("campo,valor", RANGOS_RECHAZADOS)
def test_rangos_de_control_rechazan(campo: str, valor: object) -> None:
    with pytest.raises(ConfiguracionInvalidaError) as exc:
        ParametrosConfiguracion(**{campo: valor})
    assert exc.value.campo == campo


def test_n_gracia_cero_es_valido_though_no_recomendado() -> None:
    """``n_gracia_busqueda = 0`` significa DETENER inmediato, no un error."""
    assert ParametrosConfiguracion(n_gracia_busqueda=0).n_gracia_busqueda == 0


def test_banda_de_histresesis_valida_al_limite() -> None:
    """Los bordes exactos de V1/V2 se aceptan: la pertenencia es inclusiva."""
    parametros = ParametrosConfiguracion(zona_muerta=0.47, histeresis=0.03)
    assert abs((parametros.zona_muerta + parametros.histeresis) - 0.5) < 1e-9
    assert ParametrosConfiguracion(zona_muerta=0.03, histeresis=0.03)
