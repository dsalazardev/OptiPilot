# Contrato: Cadencia de marcha

**Feature**: `004-clasificador-senales-cnn` | **Date**: 2026-11-02

## 1. Tabla de cadencia

| Señal | Comando | Intervalo | Comportamiento |
|---|---|---|---|
| PARE | `x` | 3.0 s | Detiene y reanuda al cumplirse `t_parada_s` |
| SIGA | `w` | 1.0 s | Marcha normal |
| ZONA ESCOLAR | `w` | 2.0 s | Marcha lenta |
| VELOCIDAD 60 | `w` | 0.5 s | Marcha rápida |

La cadencia se mide con `t_s`:
- fuente en vivo: `time.perf_counter()`;
- video/directorio: `indice / fps` (determinista para tests).

## 2. Reglas

1. **PARE manda.** Mientras la FSM emite `NO_AUTORIZADO` (`VETO_FSM`), se envía `DETENER` (`x`) de inmediato y no se envía ningún `w`.
2. **Reanudación.** Al cumplirse `t_parada_s`, la FSM autoriza y el modo vuelve a `SIGA` (1.0 s). El primer `w` se envía de inmediato.
3. **Modo persistente.** `SIGA`, `ZONA_ESCOLAR` y `VELOCIDAD_60` persisten hasta que otra clase se confirme. No expiran al desaparecer el cartel.
4. **Primer `w` inmediato.** Si el último comando fue `IZQUIERDA`, `DERECHA` o `DETENER`, el primer `AVANZAR` se envía sin esperar el intervalo.
5. **Correcciones.** `IZQUIERDA` y `DERECHA` conservan la cadencia de `fotogramas_por_orden` (6 frames por defecto). No usan el intervalo de la señal.
6. **Deduplicación.** La cola sigue deduplicando comandos idénticos consecutivos; la cadencia no envía comandos que la cola descartaría.
7. **Prioridad.** `DETENER` > corrección > `AVANZAR`. La cadencia nunca retrasa una parada: con el clasificador activo, cualquier `DETENER` (FSM, pérdida de línea o fallo seguro) se envía en el fotograma en que se decide. Con el clasificador apagado se conserva el comportamiento actual del bucle.
8. **Sin hardware.** La lógica se prueba con `t_s` inyectado y un transporte simulado.
9. **Solo con clasificador activo.** `CadenciaMarcha` se usa únicamente con `--clasificador onnx`. Con `--clasificador off`, el bucle conserva la cadencia actual de `fotogramas_por_orden` para todas las órdenes y el comportamiento es idéntico al de antes de esta feature.

## 3. Ejemplos

### SIGA (1.0 s)

```text
t=0.00  AVANZAR  → w
t=0.20  AVANZAR  → (nada)
t=0.50  IZQUIERDA → a
t=0.60  AVANZAR  → w (primero tras corrección)
t=1.60  AVANZAR  → w
```

### PARE

```text
t=2.00  PARE confirmado → x
t=2.10  FSM NO_AUTORIZADO → x
...
t=5.00  FSM AUTORIZADO (T cumplido) → w (modo SIGA)
```

### ZONA ESCOLAR

```text
t=0.00  AVANZAR → w
t=0.50  AVANZAR → (nada)
t=2.00  AVANZAR → w
```

## 4. Estado

`CadenciaMarcha` mantiene:
- `_ultimo_avance_t: float | None`
- `_ultima_orden: ComandoMovimiento | None`

`debe_enviar(comando, modo, t_s)` devuelve `True`/`False` y actualiza el estado solo cuando el comando se transmite. `reiniciar()` limpia ambos campos al inicio de una corrida.

## 5. Supuesto de hardware

El contrato asume que el firmware del mBot trata cada `w` como un paso de avance y que la separación entre `w` modula la velocidad. Si el firmware mantiene movimiento continuo, el intervalo no cambiará la velocidad; el comportamiento debe validarse en pista y registrarse en AGENTS.md §27.
