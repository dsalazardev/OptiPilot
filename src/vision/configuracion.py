"""Parámetros centralizados del módulo de visión (FR-024, Constitución §IV).

Todos los umbrales, zonas y tiempos del pipeline provienen de este módulo:
``ParametrosConfiguracion`` es inmutable, valida sus reglas al construirse y se
puede poblar desde ``config/vision.json`` (contrato
``contracts/esquema-configuracion.md``). La fusión es campo por campo: lo que no
aparece en el JSON conserva el valor por defecto.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "ConfiguracionInvalidaError",
    "ParametrosConfiguracion",
    "RangoHSV",
    "RectanguloNormalizado",
    "cargar_parametros",
]

CAMPO_ARCHIVO = "<archivo>"


class ConfiguracionInvalidaError(ValueError):
    """Configuración inválida: expone el ``campo`` y el ``motivo`` del rechazo."""

    def __init__(self, campo: str, motivo: str) -> None:
        self.campo = campo
        self.motivo = motivo
        super().__init__(f"Configuración inválida en '{campo}': {motivo}")


@dataclass(frozen=True)
class RangoHSV:
    """Rango inclusivo en HSV tal como lo usa OpenCV (H 0–179; S/V 0–255)."""

    h_min: int
    h_max: int
    s_min: int
    s_max: int
    v_min: int
    v_max: int

    def limites(self) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
        """Devuelve ``(inferior, superior)`` listos para ``cv2.inRange``."""
        return (self.h_min, self.s_min, self.v_min), (self.h_max, self.s_max, self.v_max)

    def solapa_tono(self, otro: "RangoHSV") -> bool:
        """True si los intervalos de tono (H) se intersecan."""
        return self.h_min <= otro.h_max and otro.h_min <= self.h_max


@dataclass(frozen=True)
class RectanguloNormalizado:
    """Región de interés en fracciones del fotograma (x, y, w, h dentro de [0, 1])."""

    x: float
    y: float
    w: float
    h: float


ROI_LINEA_POR_DEFECTO = RectanguloNormalizado(x=0.15, y=0.55, w=0.70, h=0.45)
ROI_SENALES_POR_DEFECTO = RectanguloNormalizado(x=0.10, y=0.05, w=0.80, h=0.55)
RANGO_HSV_LINEA_POR_DEFECTO = RangoHSV(h_min=0, h_max=179, s_min=0, s_max=255, v_min=0, v_max=110)
RANGOS_HSV_ROJO_POR_DEFECTO = (
    RangoHSV(h_min=0, h_max=10, s_min=120, s_max=255, v_min=90, v_max=255),
    RangoHSV(h_min=170, h_max=179, s_min=120, s_max=255, v_min=90, v_max=255),
)
RANGO_HSV_VERDE_POR_DEFECTO = RangoHSV(
    h_min=45, h_max=85, s_min=100, s_max=255, v_min=70, v_max=255
)
KERNEL_MORFOLOGICO_PX_POR_DEFECTO = 5
AREA_MINIMA_REL_POR_DEFECTO = 0.001
N_CONFIRMACION_POR_DEFECTO = 3
K_TOLERANCIA_POR_DEFECTO = 2
X_REARME_POR_DEFECTO = 5
T_PARADA_S_POR_DEFECTO = 3.0  # provisional: confirmar con el docente (FR-017)
PRESUPUESTO_LATENCIA_FRAMES_POR_DEFECTO = 8
FPS_OBJETIVO_POR_DEFECTO = 30.0
VERTICES_OBJETIVO_POR_DEFECTO = 8
TOLERANCIA_VERTICES_POR_DEFECTO = 1
ASPECTO_MIN_POR_DEFECTO = 0.70
ASPECTO_MAX_POR_DEFECTO = 1.40

_RECT_CLAVES = ("x", "y", "w", "h")
_RANGO_CLAVES = ("h_min", "h_max", "s_min", "s_max", "v_min", "v_max")
_CAMPOS_CONOCIDOS = frozenset(
    {
        "roi_linea",
        "roi_senales",
        "rango_hsv_linea",
        "rangos_hsv_rojo",
        "rango_hsv_verde",
        "kernel_morfologico_px",
        "area_minima_rel",
        "n_confirmacion",
        "k_tolerancia",
        "x_rearme",
        "t_parada_s",
        "presupuesto_latencia_frames",
        "fps_objetivo",
        "vertices_objetivo",
        "tolerancia_vertices",
        "aspecto_min",
        "aspecto_max",
    }
)


@dataclass(frozen=True)
class ParametrosConfiguracion:
    """Parámetros inmutables del pipeline; se validan en la construcción."""

    roi_linea: RectanguloNormalizado = ROI_LINEA_POR_DEFECTO
    roi_senales: RectanguloNormalizado = ROI_SENALES_POR_DEFECTO
    rango_hsv_linea: RangoHSV = RANGO_HSV_LINEA_POR_DEFECTO
    rangos_hsv_rojo: tuple[RangoHSV, RangoHSV] = RANGOS_HSV_ROJO_POR_DEFECTO
    rango_hsv_verde: RangoHSV = RANGO_HSV_VERDE_POR_DEFECTO
    kernel_morfologico_px: int = KERNEL_MORFOLOGICO_PX_POR_DEFECTO
    area_minima_rel: float = AREA_MINIMA_REL_POR_DEFECTO
    n_confirmacion: int = N_CONFIRMACION_POR_DEFECTO
    k_tolerancia: int = K_TOLERANCIA_POR_DEFECTO
    x_rearme: int = X_REARME_POR_DEFECTO
    t_parada_s: float = T_PARADA_S_POR_DEFECTO
    presupuesto_latencia_frames: int = PRESUPUESTO_LATENCIA_FRAMES_POR_DEFECTO
    fps_objetivo: float = FPS_OBJETIVO_POR_DEFECTO
    vertices_objetivo: int = VERTICES_OBJETIVO_POR_DEFECTO
    tolerancia_vertices: int = TOLERANCIA_VERTICES_POR_DEFECTO
    aspecto_min: float = ASPECTO_MIN_POR_DEFECTO
    aspecto_max: float = ASPECTO_MAX_POR_DEFECTO

    def __post_init__(self) -> None:
        _validar(self)

    @classmethod
    def por_defecto(cls) -> "ParametrosConfiguracion":
        """Instancia con los valores por defecto del contrato."""
        return cls()


def _validar(p: ParametrosConfiguracion) -> None:
    _validar_rectangulo("roi_linea", p.roi_linea)
    _validar_rectangulo("roi_senales", p.roi_senales)
    _validar_rango("rango_hsv_linea", p.rango_hsv_linea)
    _validar_rango("rango_hsv_verde", p.rango_hsv_verde)

    if len(p.rangos_hsv_rojo) != 2:
        raise ConfiguracionInvalidaError(
            "rangos_hsv_rojo", "se esperaban exactamente 2 rangos de tono para el rojo"
        )
    for indice, rango in enumerate(p.rangos_hsv_rojo):
        _validar_rango(f"rangos_hsv_rojo[{indice}]", rango)
    if p.rangos_hsv_rojo[0].solapa_tono(p.rangos_hsv_rojo[1]):
        raise ConfiguracionInvalidaError(
            "rangos_hsv_rojo", "los dos rangos de tono del rojo se solapan"
        )
    for indice, rango in enumerate(p.rangos_hsv_rojo):
        if rango.solapa_tono(p.rango_hsv_verde):
            raise ConfiguracionInvalidaError(
                "rango_hsv_verde",
                f"el tono del verde se solapa con rangos_hsv_rojo[{indice}]: señales ambiguas",
            )

    if p.kernel_morfologico_px < 3 or p.kernel_morfologico_px % 2 == 0:
        raise ConfiguracionInvalidaError(
            "kernel_morfologico_px", "debe ser un entero impar ≥ 3"
        )
    if not 0 < p.area_minima_rel < 1:
        raise ConfiguracionInvalidaError(
            "area_minima_rel", "debe estar en (0, 1) como fracción del área de la ROI"
        )
    if p.n_confirmacion < 1:
        raise ConfiguracionInvalidaError("n_confirmacion", "debe ser ≥ 1")
    if p.k_tolerancia < 0:
        raise ConfiguracionInvalidaError("k_tolerancia", "debe ser ≥ 0")
    if p.x_rearme < 0:
        raise ConfiguracionInvalidaError("x_rearme", "debe ser ≥ 0")
    if p.t_parada_s < 0:
        raise ConfiguracionInvalidaError("t_parada_s", "debe ser ≥ 0")
    if p.presupuesto_latencia_frames < 1:
        raise ConfiguracionInvalidaError("presupuesto_latencia_frames", "debe ser ≥ 1")
    if p.fps_objetivo <= 0:
        raise ConfiguracionInvalidaError("fps_objetivo", "debe ser > 0")
    if p.vertices_objetivo != 8:
        raise ConfiguracionInvalidaError("vertices_objetivo", "un octágono tiene 8 vértices")
    if p.tolerancia_vertices < 0:
        raise ConfiguracionInvalidaError("tolerancia_vertices", "debe ser ≥ 0")
    if not 0 < p.aspecto_min <= p.aspecto_max:
        raise ConfiguracionInvalidaError(
            "aspecto_min", "se requiere 0 < aspecto_min ≤ aspecto_max"
        )


def _validar_rectangulo(campo: str, rectangulo: RectanguloNormalizado) -> None:
    for nombre, valor in (
        ("x", rectangulo.x),
        ("y", rectangulo.y),
        ("w", rectangulo.w),
        ("h", rectangulo.h),
    ):
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ConfiguracionInvalidaError(campo, f"'{nombre}' debe ser numérico")
    if not (0.0 <= rectangulo.x <= 1.0 and 0.0 <= rectangulo.y <= 1.0):
        raise ConfiguracionInvalidaError(campo, "el origen (x, y) debe estar en [0, 1]")
    if rectangulo.w <= 0 or rectangulo.h <= 0:
        raise ConfiguracionInvalidaError(campo, "el ancho y el alto deben ser > 0")
    if rectangulo.x + rectangulo.w > 1.0 + 1e-9 or rectangulo.y + rectangulo.h > 1.0 + 1e-9:
        raise ConfiguracionInvalidaError(
            campo, "la ROI excede el marco del fotograma (x+w ≤ 1, y+h ≤ 1)"
        )


def _validar_rango(campo: str, rango: RangoHSV) -> None:
    for nombre, valor, limite in (
        ("h_min", rango.h_min, 179),
        ("h_max", rango.h_max, 179),
        ("s_min", rango.s_min, 255),
        ("s_max", rango.s_max, 255),
        ("v_min", rango.v_min, 255),
        ("v_max", rango.v_max, 255),
    ):
        if isinstance(valor, bool) or not isinstance(valor, int):
            raise ConfiguracionInvalidaError(campo, f"'{nombre}' debe ser entero")
        if not 0 <= valor <= limite:
            raise ConfiguracionInvalidaError(campo, f"'{nombre}' debe estar en [0, {limite}]")
    if rango.h_min > rango.h_max:
        raise ConfiguracionInvalidaError(campo, "h_min no puede ser mayor que h_max")
    if rango.s_min > rango.s_max:
        raise ConfiguracionInvalidaError(campo, "s_min no puede ser mayor que s_max")
    if rango.v_min > rango.v_max:
        raise ConfiguracionInvalidaError(campo, "v_min no puede ser mayor que v_max")


def _como_entero(campo: str, valor: Any) -> int:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ConfiguracionInvalidaError(campo, "debe ser un entero")
    if isinstance(valor, float):
        if not valor.is_integer():
            raise ConfiguracionInvalidaError(campo, "debe ser un entero")
        return int(valor)
    return int(valor)


def _como_numero(campo: str, valor: Any) -> float:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ConfiguracionInvalidaError(campo, "debe ser numérico")
    return float(valor)


def _construir_rectangulo(campo: str, bruto: Any, base: RectanguloNormalizado) -> RectanguloNormalizado:
    if not isinstance(bruto, Mapping):
        raise ConfiguracionInvalidaError(campo, "se esperaba un objeto JSON con x, y, w, h")
    extra = sorted(set(bruto) - set(_RECT_CLAVES))
    if extra:
        raise ConfiguracionInvalidaError(campo, f"campo desconocido '{extra[0]}'")
    valores = {
        clave: _como_numero(campo, bruto[clave]) if clave in bruto else getattr(base, clave)
        for clave in _RECT_CLAVES
    }
    return RectanguloNormalizado(**valores)


def _construir_rango(campo: str, bruto: Any, base: RangoHSV) -> RangoHSV:
    if not isinstance(bruto, Mapping):
        raise ConfiguracionInvalidaError(campo, "se esperaba un objeto JSON con los límites HSV")
    extra = sorted(set(bruto) - set(_RANGO_CLAVES))
    if extra:
        raise ConfiguracionInvalidaError(campo, f"campo desconocido '{extra[0]}'")
    valores = {
        clave: _como_entero(campo, bruto[clave]) if clave in bruto else getattr(base, clave)
        for clave in _RANGO_CLAVES
    }
    return RangoHSV(**valores)


def _leer_rectangulo(
    datos: Mapping[str, Any], campo: str, defecto: RectanguloNormalizado
) -> RectanguloNormalizado:
    if campo not in datos:
        return defecto
    return _construir_rectangulo(campo, datos[campo], defecto)


def _leer_rango(datos: Mapping[str, Any], campo: str, defecto: RangoHSV) -> RangoHSV:
    if campo not in datos:
        return defecto
    return _construir_rango(campo, datos[campo], defecto)


def _leer_rangos_rojo(
    datos: Mapping[str, Any], defecto: tuple[RangoHSV, RangoHSV]
) -> tuple[RangoHSV, RangoHSV]:
    campo = "rangos_hsv_rojo"
    if campo not in datos:
        return defecto
    bruto = datos[campo]
    if not isinstance(bruto, list) or len(bruto) != 2:
        raise ConfiguracionInvalidaError(
            campo, "se esperaban exactamente 2 rangos de tono para el rojo"
        )
    return (
        _construir_rango(campo, bruto[0], defecto[0]),
        _construir_rango(campo, bruto[1], defecto[1]),
    )


def _leer_entero(datos: Mapping[str, Any], campo: str, defecto: int) -> int:
    if campo not in datos:
        return defecto
    return _como_entero(campo, datos[campo])


def _leer_numero(datos: Mapping[str, Any], campo: str, defecto: float) -> float:
    if campo not in datos:
        return defecto
    return _como_numero(campo, datos[campo])


def _fusionar(datos: Mapping[str, Any]) -> ParametrosConfiguracion:
    desconocidos = sorted(set(datos) - _CAMPOS_CONOCIDOS)
    if desconocidos:
        raise ConfiguracionInvalidaError(desconocidos[0], "campo desconocido en la configuración")
    defecto = ParametrosConfiguracion.por_defecto()
    return ParametrosConfiguracion(
        roi_linea=_leer_rectangulo(datos, "roi_linea", defecto.roi_linea),
        roi_senales=_leer_rectangulo(datos, "roi_senales", defecto.roi_senales),
        rango_hsv_linea=_leer_rango(datos, "rango_hsv_linea", defecto.rango_hsv_linea),
        rangos_hsv_rojo=_leer_rangos_rojo(datos, defecto.rangos_hsv_rojo),
        rango_hsv_verde=_leer_rango(datos, "rango_hsv_verde", defecto.rango_hsv_verde),
        kernel_morfologico_px=_leer_entero(
            datos, "kernel_morfologico_px", defecto.kernel_morfologico_px
        ),
        area_minima_rel=_leer_numero(datos, "area_minima_rel", defecto.area_minima_rel),
        n_confirmacion=_leer_entero(datos, "n_confirmacion", defecto.n_confirmacion),
        k_tolerancia=_leer_entero(datos, "k_tolerancia", defecto.k_tolerancia),
        x_rearme=_leer_entero(datos, "x_rearme", defecto.x_rearme),
        t_parada_s=_leer_numero(datos, "t_parada_s", defecto.t_parada_s),
        presupuesto_latencia_frames=_leer_entero(
            datos, "presupuesto_latencia_frames", defecto.presupuesto_latencia_frames
        ),
        fps_objetivo=_leer_numero(datos, "fps_objetivo", defecto.fps_objetivo),
        vertices_objetivo=_leer_entero(datos, "vertices_objetivo", defecto.vertices_objetivo),
        tolerancia_vertices=_leer_entero(
            datos, "tolerancia_vertices", defecto.tolerancia_vertices
        ),
        aspecto_min=_leer_numero(datos, "aspecto_min", defecto.aspecto_min),
        aspecto_max=_leer_numero(datos, "aspecto_max", defecto.aspecto_max),
    )


def cargar_parametros(ruta: str | Path | None = None) -> ParametrosConfiguracion:
    """Carga y valida la configuración.

    Sin ``ruta`` devuelve los valores por defecto. Con ``ruta``, mezcla el JSON
    indicado sobre los defaults y valida el resultado.
    """
    if ruta is None:
        return ParametrosConfiguracion.por_defecto()

    camino = Path(ruta)
    try:
        texto = camino.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfiguracionInvalidaError(
            CAMPO_ARCHIVO, f"no se pudo leer '{camino}': {exc}"
        ) from exc
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError as exc:
        raise ConfiguracionInvalidaError(
            CAMPO_ARCHIVO, f"JSON inválido en '{camino}': {exc}"
        ) from exc
    if not isinstance(datos, dict):
        raise ConfiguracionInvalidaError(
            CAMPO_ARCHIVO, f"la raíz de '{camino}' debe ser un objeto JSON"
        )
    return _fusionar(datos)
