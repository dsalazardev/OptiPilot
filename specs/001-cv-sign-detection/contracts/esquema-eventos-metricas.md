# Contrato — Eventos y métricas por corrida

**Feature**: `specs/001-cv-sign-detection` | **Date**: 2026-09-24

Salidas de una corrida en `salidas/<corrida_id>/` (git-ignored):

```text
salidas/<corrida_id>/
├── eventos.jsonl     # un evento JSON por línea (UTF-8)
├── metricas.json     # resumen agregado de la corrida
└── frames/           # fotogramas anotados (modo diagnóstico) — o anotado.mp4
```

## `eventos.jsonl`

Una línea por evento, en orden temporal:

```jsonc
{"ts": 12.34, "frame": 370, "tipo": "PARE_CONFIRMADO", "clase": "PARE", "ocurrencia_id": 3, "centro": [318, 122]}
{"ts": 12.40, "frame": 372, "tipo": "TRANSICION", "clase": null, "ocurrencia_id": null, "centro": null, "origen": "EN_MARCHA", "destino": "DETENIDO_MINIMO", "causa": "PARE_CONFIRMADO"}
{"ts": 12.67, "frame": 380, "tipo": "SIGA_CONFIRMADO", "clase": "SIGA", "ocurrencia_id": 4, "centro": [402, 118]}
{"ts": 15.71, "frame": 471, "tipo": "PARE_REARMADO", "clase": "PARE", "ocurrencia_id": 3, "centro": null}
```

| Campo | Tipo | Notas |
|-------|------|-------|
| `ts` | float | segundos desde el inicio de la corrida |
| `frame` | int | índice de fotograma |
| `tipo` | enum | `PARE_CONFIRMADO`, `SIGA_CONFIRMADO`, `SENAL_PERDIDA`, `PARE_REARMADO`, `FALSO_POSITIVO_SUPRIMIDO`, `TRANSICION` |
| `clase` | "PARE" \| "SIGA" \| null | según el tipo |
| `ocurrencia_id` | int \| null | identifica la ocurrencia (delimitada por re-armado) |
| `centro` | [x, y] \| null | píxeles |
| `origen`, `destino` | EstadoRobot \| null | presentes solo en `TRANSICION` |
| `causa` | CausaTransicion \| null | presente solo en `TRANSICION` |

## `metricas.json`

```jsonc
{
  "corrida_id": "demo_01",
  "fuente": "videos/pista_practica.mp4",
  "frames_procesados": 1180,
  "ocurrencias_pare": 2,
  "ocurrencias_siga": 2,
  "detecciones_correctas": 4,
  "falsos_positivos": 0,
  "confusiones": 0,
  "latencias_frames": [6, 5, 7, 6],
  "latencias_ms": [201.0, 168.4, 233.1, 199.5],
  "paradas": [
    { "inicio_t": 12.40, "t_configurado_s": 3.0, "fin_t": 16.05, "retardo_s": 0.65 }
  ],
  "fps_promedio": 29.8,
  "latencia_media_ms": 24.6,
  "latencia_p95_ms": 31.2
}
```

| Campo | Unidad | Definición |
|-------|--------|------------|
| `ocurrencias_pare` / `ocurrencias_siga` | count | ocurrencias registradas por el módulo (delimitadas por re-armado) |
| `detecciones_correctas` / `falsos_positivos` / `confusiones` | count | contra la anotación de referencia de señales físicas (Q3); `confusiones` = PARE↔SIGA |
| `latencias_frames` | frames | desde el primer fotograma con la señal **completamente dentro de la ROI y área ≥ mínima** hasta la decisión emitida (Q2, SC-006) |
| `latencias_ms` | ms | la misma latencia en tiempo (según `ts` de fotogramas) |
| `paradas[].retardo_s` | s | tiempo adicional esperando SIGA después de cumplirse T (SC-008) |
| `latencia_media_ms`, `latencia_p95_ms` | ms | latencia de **procesamiento** por fotograma (SC-007) |

## Reglas

1. Los archivos se escriben al cerrar la corrida (o incrementalmente para `eventos.jsonl`). Cada
   transición de estado (FR-023) se vuelca como evento `TRANSICION` con origen, destino, causa y
   momento.
2. `metricas.json` nunca omite claves: contadores en 0 y listas vacías cuando no aplica.
3. Las tasas de aceptación (SC-001/002/003) se calculan contra la anotación de referencia; el
   módulo solo aporta los conteos y eventos.
4. Los fotogramas anotados se generan solo con `--diagnostico` (SC-012) y no afectan la decisión.
5. Sin datos personales ni secretos; los artefactos se excluyen del control de versiones.
