# Contrato — Esquema de configuración (`config/vision.json`)

**Feature**: `specs/001-cv-sign-detection` | **Date**: 2026-09-24

Archivo JSON UTF-8; los campos omitidos toman el valor por defecto embebido. Todos los parámetros de
FR-024 están aquí (única fuente de verdad). No contiene secretos.

## Esquema

```jsonc
{
  "roi_linea":      { "x": 0.15, "y": 0.55, "w": 0.70, "h": 0.45 }, // fracciones del fotograma
  "roi_senales":    { "x": 0.10, "y": 0.05, "w": 0.80, "h": 0.55 },
  "rango_hsv_linea": { "h_min": 0,   "h_max": 179, "s_min": 0,   "s_max": 255, "v_min": 0,   "v_max": 110 },
  "rangos_hsv_rojo": [
    { "h_min": 0,   "h_max": 10,  "s_min": 120, "s_max": 255, "v_min": 90,  "v_max": 255 },
    { "h_min": 170, "h_max": 179, "s_min": 120, "s_max": 255, "v_min": 90,  "v_max": 255 }
  ],
  "rango_hsv_verde": { "h_min": 45,  "h_max": 85,  "s_min": 100, "s_max": 255, "v_min": 70,  "v_max": 255 },
  "kernel_morfologico_px": 5,
  "area_minima_rel": 0.001,
  "n_confirmacion": 3,
  "k_tolerancia": 2,
  "x_rearme": 5,
  "t_parada_s": 3.0,
  "presupuesto_latencia_frames": 8,
  "fps_objetivo": 30.0,
  "vertices_objetivo": 8,
  "tolerancia_vertices": 1,
  "aspecto_min": 0.70,
  "aspecto_max": 1.40
}
```

## Reglas de validación

| Regla | Error si se incumple |
|-------|----------------------|
| `h_min`/`h_max` de todo rango en [0,179]; `s_*`/`v_*` en [0,255]; `h_min ≤ h_max` | `ConfiguracionInvalidaError`: rango fuera de límites |
| `rango_hsv_linea` no se solapa con `rangos_hsv_rojo` ni con `rango_hsv_verde` | hue de línea ambiguo (calibrar) |
| ROI en [0,1] y `w,h > 0`; `x+w ≤ 1`, `y+h ≤ 1` | ROI fuera del fotograma |
| `kernel_morfologico_px` entero impar ≥ 3 | kernel inválido |
| `0 < area_minima_rel < 1` | área mínima inválida |
| `n_confirmacion ≥ 1`; `k_tolerancia ≥ 0`; `x_rearme ≥ 0` | contadores inválidos |
| `t_parada_s ≥ 0`; `presupuesto_latencia_frames ≥ 1`; `fps_objetivo > 0` | tiempos inválidos |
| `vertices_objetivo = 8`; `tolerancia_vertices ≥ 0`; `0 < aspecto_min ≤ aspecto_max` | geometría inválida |

## Notas

- **Línea**: el rango por defecto asume una línea oscura sobre pista clara; es un valor provisional
  que el cambio implementa y la tarea de calibración ajusta con los videos de práctica.
- **T (`t_parada_s`)**: valor definido por el docente; 3.0 s es un provisional documentado, no una
  asunción definitiva (FR-017). Confirmar antes de la competencia.
- **Área mínima**: se expresa como fracción del área de la ROI, para ser independiente de la
  resolución de la cámara.
- **Morfología**: si aparece `kernel_morfologico_px` distinto entre máscaras de línea y señales, se
  permitirá un campo por grupo en una revisión futura (no en v1).
