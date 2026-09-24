# Phase 1 — Data Model: Módulo de Procesamiento de Imagen y Detección de Señales PARE/SIGA

**Feature**: `specs/001-cv-sign-detection` | **Date**: 2026-09-24 | **Spec**: [spec.md](./spec.md)

Convenciones: entidades en español; `dataclass` (frozen donde se indique); sin I/O dentro de las
entidades; coordenadas en píxeles; tiempos en segundos (float); sin campos aleatorios (determinismo,
Principio IV). Los esquemas de serialización se detallan en `contracts/`.

## Entidades

### 1. ParametrosConfiguracion (frozen, serializable a JSON) — FR-024

| Campo | Tipo | Default | Validación |
|-------|------|---------|------------|
| `roi_linea` | RectanguloNormalizado (x,y,w,h ∈ [0,1]) | (0.15, 0.55, 0.70, 0.45) | dentro del marco; w,h > 0 |
| `roi_senales` | RectanguloNormalizado | (0.10, 0.05, 0.80, 0.55) | dentro del marco; w,h > 0 |
| `rango_hsv_linea` | RangoHSV | V máx 110 (línea oscura provisional; calibrar con footage) | H 0–179, S/V 0–255 |
| `rangos_hsv_rojo` | lista de 2 RangoHSV (wrap de tono) | (0,10,120,255,90,255) y (170,179,120,255,90,255) | H 0–179; listas no solapadas con verde |
| `rango_hsv_verde` | RangoHSV | (45,85,100,255,70,255) | H 0–179; sin solape con rojo |
| `kernel_morfologico_px` | int | 5 | impar, ≥ 3 |
| `area_minima_rel` | float | 0.001 | 0 < a < 1 (fracción del área de ROI) |
| `n_confirmacion` | int | 3 | ≥ 1 (FR-011) |
| `k_tolerancia` | int | 2 | ≥ 0 (FR-011) |
| `x_rearme` | int | 5 | ≥ 0 (FR-021) |
| `t_parada_s` | float | 3.0 (provisional; confirmar con el docente) | ≥ 0 (FR-017) |
| `presupuesto_latencia_frames` | int | 8 | ≥ 1 (SC-006) |
| `fps_objetivo` | float | 30.0 | > 0 (SC-007; solo referencia de conversión) |
| `vertices_objetivo` | int | 8 | = 8 (octágono) |
| `tolerancia_vertices` | int | 1 | ≥ 0 (acepta 7–9 vértices) |
| `aspecto_min` / `aspecto_max` | float | 0.70 / 1.40 | 0 < min ≤ max |

- **Carga/validación**: `cargar_parametros(ruta)` mezcla defaults + archivo y valida; error claro
  (`ConfiguracionInvalidaError`) con campo y motivo.
- **Trazabilidad**: todo parámetro modificable sin tocar lógica (FR-024).

### 2. Fotograma (entrada, runtime)

| Campo | Tipo | Validación |
|-------|------|------------|
| `indice` | int | ≥ 0, monótono |
| `timestamp_s` | float | ≥ 0, no decreciente |
| `imagen` | np.ndarray (H×W×3, uint8, BGR) | no vacío, 3 canales |

### 3. ResultadoSegmentacion — FR-005/006/007/013

| Campo | Tipo | Notas |
|-------|------|-------|
| `mascara_linea` | np.ndarray uint8 {0,1}, tamaño completo H×W | morfología aplicada |
| `mascara_roja` | np.ndarray uint8 {0,1}, tamaño completo | unión de los 2 rangos de rojo |
| `mascara_verde` | np.ndarray uint8 {0,1}, tamaño completo | |
| `roi_linea` / `roi_senales` | tupla píxeles | ROI efectiva del fotograma |

### 4. CandidatoSenal — FR-008/009/010

| Campo | Tipo | Validación |
|-------|------|------------|
| `clase_estimada` | PARE \| SIGA | según máscara de origen |
| `centro_px` | (int, int) | dentro del fotograma |
| `area_px` / `area_rel` | int / float | area_px ≥ área mínima; area_rel = area_px/área ROI |
| `n_vertices` | int | de `approxPolyDP` |
| `caja_px` | (x, y, w, h) | w,h > 0 |
| `aspecto` | float | w/h |
| `es_valido` | bool | octágono: 8±1 vértices y aspecto en rango |
| `motivo_invalidez` | str \| None | presente si `es_valido` es falso |

### 5. SenalConfirmada (flanco de subida) — FR-011

| Campo | Tipo |
|-------|------|
| `clase` | PARE \| SIGA |
| `centro_px`, `area_rel` | (int, int) / float |
| `fotograma_idx`, `t_s` | int / float |
| `ocurrencia_id` | int (asociada) |

### 6. Ocurrencia — FR-021/FR-025

| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | int | secuencial por corrida |
| `clase` | PARE \| SIGA | |
| `fotograma_inicio`, `t_inicio` | int / float | primera confirmación |
| `fotograma_fin`, `t_fin` | int \| None / float \| None | al re-armar o cerrar la corrida |
| `estado` | ACTIVA \| CERRADA | |
| `anotada` | bool | corresponde a señal física de la anotación de referencia (métricas, Q3) |
| `detecciones` | int | fotogramas confirmados acumulados |

### 7. EstadoRobot (enum) — FR-015

- `EN_MARCHA`
- `DETENIDO_MINIMO` (T en curso)
- `DETENIDO_ESPERANDO_SIGA` (T cumplido, sin SIGA armado)

### 8. DecisionMovimiento (enum) — FR-015

- `AUTORIZADO` / `NO_AUTORIZADO` + `causa: str` (p. ej., `PARE_CONFIRMADO`, `T_CUMPLIDO_CON_SIGA`,
  `SIGA_CONFIRMADO`, `INICIO`).

### 9. TransicionEstado — FR-023

| Campo | Tipo |
|-------|------|
| `desde`, `hacia` | EstadoRobot |
| `causa` | PARE_CONFIRMADO \| T_CUMPLIDO \| SIGA_CONFIRMADO \| REANUDACION \| REARME \| INICIO |
| `fotograma_idx`, `t_s` | int / float |

### 10. EventoSenal — FR-013/FR-018/FR-021/FR-023

| Campo | Tipo | Notas |
|-------|------|-------|
| `tipo` | PARE_CONFIRMADO \| SIGA_CONFIRMADO \| SENAL_PERDIDA \| PARE_REARMADO \| FALSO_POSITIVO_SUPRIMIDO | |
| `clase` | PARE \| SIGA \| None | |
| `fotograma_idx`, `t_s` | int / float | |
| `centro_px` | (int, int) \| None | |
| `ocurrencia_id` | int \| None | |

### 11. EstadoMaquina (runtime, determinista)

| Campo | Tipo | Notas |
|-------|------|-------|
| `estado` | EstadoRobot | |
| `t_inicio_parada` | float \| None | cronómetro T |
| `siga_armado` | bool | se conserva aunque la señal salga de vista (FR-022) |
| `pare_activa_id` | int \| None | ocurrencia latcheada (FR-021) |

### 12. ResultadoProcesamiento (salida del pipeline por fotograma)

`segmentacion: ResultadoSegmentacion`, `candidatos: list[CandidatoSenal]`,
`senales_confirmadas: list[SenalConfirmada]`, `eventos: list[EventoSenal]`,
`latencia_ms: float` (medición interna, `time.perf_counter`) y el **marcador de visibilidad plena**
por señal (primer fotograma completamente dentro de la ROI y área ≥ mínima; base de la latencia de
decisión de SC-006).

### 13. MetricasCorrida — FR-025/SC-012

| Campo | Tipo | Notas |
|-------|------|-------|
| `corrida_id`, `fuente` | str | |
| `frames_procesados` | int | |
| `ocurrencias_pare`, `ocurrencias_siga` | int | delimitadas por re-armado |
| `detecciones_correctas`, `falsos_positivos`, `confusiones` | int | contra anotación de referencia |
| `latencias_frames` / `latencias_ms` | list[int] / list[float] | por decisión; inicio = visibilidad plena (Q2: completamente dentro de ROI y área ≥ mínima) |
| `paradas` | list[Parada] | `Parada = {inicio_t, t_configurado_s, fin_t, retardo_s}`; `retardo_s` = espera de SIGA después de T |
| `fps_promedio`, `latencia_media_ms`, `latencia_p95_ms` | float | |
| `transiciones` | list[TransicionEstado] | origen, destino, causa y momento; volcadas como eventos `TRANSICION` (FR-023) |

## Relaciones

```text
Fotograma ──▶ PipelineVision ──▶ ResultadoSegmentacion ──▶ [CandidatoSenal]
                                                   └──▶ [SenalConfirmada] + [EventoSenal]
                                                            │
                                                            ▼
                                            MaquinaEstados ──▶ EstadoRobot + DecisionMovimiento + [TransicionEstado]
                                                            │
                                                            ▼
                                                 MetricasCorrida ──▶ eventos.jsonl + metricas.json
```

- Una `Ocurrencia` agrupa las confirmaciones continuas de una señal entre re-armados (X fotogramas
  sin verla); las métricas la mapean 1:1 contra la anotación de referencia (Q3).
- `ParametrosConfiguracion` alimenta todas las etapas; ninguna etapa usa constantes locales no
  configurables.

## Máquina de estados — tabla de transiciones (FR-015–FR-022 + clarificaciones)

| Estado actual | Evento / condición | Nuevo estado | Efecto |
|---------------|--------------------|--------------|--------|
| EN_MARCHA | PARE nuevo confirmado | DETENIDO_MINIMO | emite `NO_AUTORIZADO`; inicia cronómetro T; `siga_armado=false` |
| EN_MARCHA | SIGA confirmado | EN_MARCHA | registra evento; nunca detiene (FR-019) |
| DETENIDO_MINIMO | SIGA confirmado (incluido co-visible al detenerse) | DETENIDO_MINIMO | `siga_armado=true` (Q-A) |
| DETENIDO_MINIMO | `t − t_inicio_parada ≥ T` y `siga_armado` | EN_MARCHA | emite `AUTORIZADO`; cierra la parada |
| DETENIDO_MINIMO | `t − t_inicio_parada ≥ T` y no `siga_armado` | DETENIDO_ESPERANDO_SIGA | sigue `NO_AUTORIZADO` |
| DETENIDO_ESPERANDO_SIGA | SIGA confirmado | EN_MARCHA | emite `AUTORIZADO`; cierra la parada |
| DETENIDO_* | PARE nuevo confirmado | sin cambio | registra evento; no reinicia T ni invalida SIGA (Q-D) |
| DETENIDO_* | pérdida temporal ≤ K fotogramas | sin cambio | cronómetro y `siga_armado` intactos (FR-022) |
| cualquiera | PARE sin verlo durante X fotogramas | — | `PARE_REARMADO`; la ocurrencia se cierra |

**Invariantes**

1. En `DETENIDO_*` la decisión es siempre `NO_AUTORIZADO`.
2. T nunca reanuda por sí solo: se exige `siga_armado=true` (FR-017).
3. El resultado depende solo de (estado, eventos, `t`): mismo guion ⇒ mismas transiciones
   (determinismo, Principio IV).
4. Si PARE y SIGA se confirman a la vez: PARE prevalece para la detención y el SIGA queda armado
   (FR-020 + Q-A).
