# Phase 1 - Data Model: Cálculo de Posición de Línea y Control de Trayectoria

**Feature**: `specs/002-control-trayectoria` | **Date**: 2026-09-28 | **Spec**: [spec.md](./spec.md)

Convenciones (heredadas de `001` y de la Constitución §II–§IV): entidades en español;
`dataclass` frozen donde no haya estado mutable; **sin I/O dentro de las entidades**; coordenadas en
píxeles del fotograma; fracciones normalizadas en [0, 1] cuando se comparan entre resoluciones
distintas; tiempos en segundos; conteos en **fotogramas** (no segundos) para todo lo que dependa de
la cadencia de la cámara; sin fuentes de azar (determinismo, Principio IV). Los esquemas de
serialización se detallan en `contracts/`.

---

## Entidades

### 1. ParametrosControl (frozen, serializable a JSON) — parámetros nuevos de 002

Se integra como **extensión** de `ParametrosConfiguracion` de 001: mismo archivo `config/vision.json`,
mismo mecanismo de carga y validación (`cargar_parametros` mezcla defaults + archivo y valida con
`ConfiguracionInvalidaError(campo, motivo)`). No se crea un archivo de configuración paralelo
(FR-038).

| Campo | Tipo | Default | Validación | Trazabilidad |
|-------|------|---------|------------|--------------|
| `x_objetivo` | float | 0.5 (provisional) | `0.0 <= x <= 1.0` | FR-004, FR-005 (Decisión 3) |
| `frac_anticipacion` | float | 0.40 | `0.0 <= f < 1.0` | FR-001 (banda de lectura) |
| `frac_pico` | float | 0.50 | `0.0 < f <= 1.0` | FR-004 (soporte del centroide) |
| `umbral_confianza` | float | 0.35 | `0.0 <= c <= 1.0` | FR-006, FR-007 |
| `zona_muerta` | float | 0.10 | `0.0 <= z < 0.5` | FR-012, FR-013 |
| `histeresis` | float | 0.03 | `0.0 <= h`; `z - h >= 0` | FR-012 |
| `n_gracia_busqueda` | int | 5 | `>= 0` | FR-019 (Decisión 4) |
| `puerto_serial` | str \| None | `None` | `None` o no vacío | FR-028 |
| `baudrate` | int | 9600 | `>= 1200` | FR-028 |
| `timeout_serial_s` | float | 0.20 | `> 0` | FR-031 |

**Restricciones cruzadas** (fallan la carga, no el runtime):

Reglas resumidas aquí; la lista normativa completa es V1–V6 en
`contracts/esquema-configuracion.md` §4.

| Regla | Motivo |
|-------|--------|
| `zona_muerta + histeresis <= 0.5` (V1) | Con zona muerta ≥ 0.5 el robot quedaría ciego a media pista (edge case, spec) |
| `zona_muerta - histeresis >= 0.0` (V2) | Si no, el umbral de retorno sería negativo y la histéresis no tendría sentido |
| `frac_anticipacion < 1.0` (V3) | Deja una banda de lectura de altura `(1 - frac_anticipacion) * alto_roi > 0` dentro de la ROI; con 1.0 la banda se vaciaría |
| `frac_pico > 0.0` (V4) | Con 0 el soporte sería toda la ROI y el centroide caería en el centro global, no en el de la línea |
| `baudrate >= 1200` (V5) | Por debajo, la trama de 4 bytes no es fiable con un ATmega a 16 MHz |
| `timeout_serial_s > 0.0` (V6) | Con 0 el puerto quedaría en modo bloqueante infinito |
| `n_gracia_busqueda >= 0` | 0 significa `DETENER` inmediato (configuración válida, aunque no recomendada) |

**No se toca en esta spec** (decisión del equipo): `t_parada_s`, `n_confirmacion`, `k_tolerancia`,
`x_rearme`, rangos HSV, `kernel_morfologico_px`, `area_minima_rel`, `presupuesto_latencia_frames`,
`fps_objetivo`, `vertices_objetivo`, `tolerancia_vertices`, `aspecto_min`, `aspecto_max`. Todos
pertenecen a 001 y permanecen intactos.

### 2. PosicionLinea (frozen) — US1, FR-001–FR-010

Resultado del cálculo de posición para un fotograma.

| Campo | Tipo | Validación | Descripción |
|-------|------|------------|-------------|
| `x_px` | float \| None | `0 <= x <= ancho` | Centro del pico de la proyección de columnas. `None` si no hay pico. |
| `x_norm` | float \| None | `0.0 <= x <= 1.0` | `x_px / ancho`. `None` si no válido. |
| `error_norm` | float \| None | sin rango fijo | `x_norm - x_objetivo`; signo = lado de la línea respecto al objetivo |
| `ancho_banda_px` | float | `>= 0` | Longitud del soporte del pico (columnas con masa ≥ `frac_pico` del máximo) |
| `confianza` | float | `0.0 <= c <= 1.0` | Dominancia del pico; penaliza ambigüedad y proximidad al borde |
| `valida` | bool | — | `True` solo si hay pico dominante, confianza ≥ umbral y no está en el borde |
| `ultimo_lado` | Lado \| None | — | Lado memorizado en el fotograma (copia de `LadoConocido.lado`) |

**Invariante**: `valida == False` ⟹ `x_px is None and x_norm is None and error_norm is None and
confianza == 0.0`. Esto hace imposible que el control consuma una posición inventada.

**No contiene**: `x_objetivo` (vive en la configuración), ni el índice de fotograma (lo lleva el
cargador de métricas), ni la máscara (es grande y ya la tiene `ResultadoSegmentacion`).

### 3. LadoConocido (frozen) — US3, FR-018

Memoria del último lado en que se detectó la línea.

| Campo | Tipo | Validación | Descripción |
|-------|------|------------|-------------|
| `lado` | Lado | — | `IZQUIERDA` \| `DERECHA` |
| `fotograma` | int | `>= 0` | Índice del fotograma en que se detectó por última vez |
| `fotogramas_perdidos` | int | `>= 0` | Contador incremental de fotogramas con `valida = False` desde entonces |

**Invariante**: mientras el robot esté en búsqueda, `fotogramas_perdidos <= n_gracia_busqueda`
(es decir, N fotogramas de gracia: el contador empieza en 1 al primer fotograma inválido). Al superar
ese valor —fotograma N+1 inválido—, el control emite `DETENER` y la memoria queda congelada (se
conserva para diagnóstico).

**Ciclo de vida**: se crea en el primer fotograma con `valida = True`; se actualiza en cada fotograma
válido (reinicia `fotogramas_perdidos` a 0); **se vacía al arrancar el proceso** (FR-023). Nunca
sobrevive entre corridas.

### 4. Lado (StrEnum) — dominio

`IZQUIERDA` | `DERECHA`. Se usa en `LadoConocido` y en la métrica de correcciones. Se evita un `int`
o un `bool` porque el dominio es explícito y debe poder imprimirse en la evidencia visual (póster).

### 5. ComandoMovimiento (StrEnum) — US2/US3, FR-011

**Los cuatro valores que fijó el profesor.** Este es el vocabulario de la API de control, no un
detalle de implementación.

| Valor | Significado | Cuándo se emite |
|-------|-------------|-----------------|
| `AVANZAR` | Avanza recto; la línea está dentro de la zona muerta | Posición válida y `|error_norm| < zona_muerta` |
| `IZQUIERDA` | Corrige hacia la izquierda | `error_norm < -(zona_muerta)` con línea válida, o búsqueda por memoria hacia la izquierda |
| `DERECHA` | Corrige hacia la derecha | `error_norm > +zona_muerta` con línea válida, o búsqueda por memoria hacia la derecha |
| `DETENER` | Parada segura | Pérdida de línea sin memoria, gracia agotada, veto por FSM, o error interno |

**Invariante de seguridad**: `DETENER` es el valor por defecto ante cualquier condición no
reconhecida (FR-025). El control nunca devuelve `None` ni lanza excepción al consumidor.

**Distinción importante**: `IZQUIERDA`/`DERECHA` significan **«la línea está de ese lado»**, no
«gira a la izquierda/derecha». Que el giro físico corresponda depende del montaje (riesgo abierto
documentado en `spec.md` Supuestos y `research.md`).

### 6. CausaComando (StrEnum) — FR-027, auditabilidad

Por qué se emitió el comando final. Existe para que la precedencia sea demostrable en la defensa oral.

| Valor | Origen |
|-------|--------|
| `SEGUIMIENTO` | Control: línea dentro de zona muerta → `AVANZAR` |
| `CORRECCION_DERECHA` / `CORRECCION_IZQUIERDA` | Control: error fuera de zona muerta |
| `RECUPERACION` | Control: memoria del último lado durante la ventana de gracia |
| `PERDIDA_SIN_MEMORIA` | Control: línea perdida sin lado conocido |
| `GRACIA_AGOTADA` | Control: pérdida que excede `n_gracia_busqueda` |
| `VETO_FSM` | Compositor: `DecisionMovimiento.veredicto == NO_AUTORIZADO` |
| `FALLO_SEGURO` | Compositor: excepción o estado inconsistente |

### 7. DecisionCompuesta (frozen) — compositor, FR-024–FR-027

Comando final + su causa. Es lo que consume el transporte.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `comando` | ComandoMovimiento | Orden final de alto nivel |
| `causa` | CausaComando | Razón de la decisión (auditable) |
| `posicion` | PosicionLinea | Posición del fotograma (evidencia) |
| `permitido` | PermisoMovimiento | Copia del veredicto de la FSM, sin modificarlo |

**Invariante de precedencia**: `causa == VETO_FSM` ⟹ `comando == DETENER`. Es el contrato que
garantiza que PARE siempre gana (SC-007).

### 8. Transporte (Protocol, sin I/O en la definición) — US4, FR-030

Contrato mínimo. La **definición** no hace I/O; las implementaciones sí.

| Miembro | Firma | Contrato |
|---------|--------|----------|
| `enviar` | `(comando: ComandoMovimiento) -> bool` | Encola/serializa el comando. Devuelve `True` si se aceptó. Nunca lanza por desconexión. |
| `cerrar` | `() -> None` | Libera el recurso. Idempotente. |
| `conectado` | `() -> bool` | Estado de conexión, consultable sin excepción. |
| `ultimo_error` | `() -> str \| None` | Último fallo registrado, para métricas. |

**Implementaciones**:

| Clase | Módulo | Rol |
|-------|--------|-----|
| `TransporteSimulado` | `src/transporte/simulado.py` | Registra comandos en memoria. **Usado por todas las pruebas** (FR-033). |
| `TransporteSPP` | `src/transporte/spp.py` | SPP/RFCOMM con `pyserial` sobre COM. Único punto del proyecto que importa `serial`. |

**Por qué un Protocol y no una clase base**: permite que las pruebas inyecten el simulado sin
herencia, y que `src/vision/` no dependa de nada de `pyserial`. `src/transporte/` es el **único**
paquete que importa el driver real.

### 9. ColaTransporte (stateful) — FR-031, FR-032

Desacopla decisión y transmisión. **Es stateful**: a diferencia de las demás entidades, tiene
estado mutable intencionado (el último comando enviado) porque representa un proceso.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `_ultimo_enviado` | ComandoMovimiento \| None | Último comando realmente transmitido (para deduplicar) |
| `_pendientes` | list[ComandoMovimiento] | Comandos encolados pendientes de drenaje |

| Método | Comportamiento |
|--------|----------------|
| `encolar(comando)` | Si `comando == _ultimo_enviado` y la cola está vacía, **descarta** (deduplicación FR-032). Si no, encola. |
| `drenar(transporte)` | Envía lo pendiente al transporte; un fallo deja el comando pendiente y registra `ultimo_error` (FR-034). |
| `pendientes()` | Número de comandos aún no transmitidos (métrica de salud del enlace). |

**Invariante**: el bucle de visión **nunca** llama a `drenar` en su camino crítico; `drenar` se
invoca desde el hilo/iteración de transporte, de modo que la latencia de radio no suma al tiempo de
procesamiento (SC-005).

### 10. MetricasControl (stateful) — FR-017, FR-036

Acumula por corrida. Extiende el patrón de `MetricasCorrida` de 001 sin modificarlo.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `correcciones` | int | Transiciones `AVANZAR ↔ {IZQUIERDA, DERECHA}` (proxy del criterio «Corrección de trayectoria») |
| `fotogramas_avanzar` / `_izquierda` / `_derecha` / `_detener` | int | Tiempo en cada comando |
| `perdidas_linea` | int | Eventos de pérdida (transición válida → inválida) |
| `recuperaciones_ok` | int | Pérdidas resueltas antes de agotar la gracia |
| `recuperaciones_fallidas` | int | Pérdidas que agotaron la gracia → `DETENER` |
| `velocidad_error_px` | list[float] | `x_px[i] - x_px[i-1]` por fotograma; su desviación estándar discrimina cámara en mano (15–20 px) de desarrilamiento (~52 px) |
| `latencia_decision_ms` | list[float] | Tiempo entre `PosicionLinea` válida y emisión del comando |

**Métrica derivada clave**: `correcciones` es el indicador directo de SC-001. La rúbrica califica
«No cumple» con más de 3 correcciones incorrectas; este contador hace ese umbral observable.

### 11. EventoControl (frozen) — para `visualizacion.py`

Un comando con su contexto, para la evidencia visual por etapa (FR-037, SC-009).

| Campo | Tipo |
|-------|------|
| `decision` | DecisionCompuesta |
| `lateral` | LadoConocido \| None |
| `fotograma` | int |

`visualizacion.py` dibuja sobre la máscara de línea: la posición estimada, la vertical del
`x_objetivo`, las bandas de zona muerta e histéresis, y el comando emitido con su causa. Es la
evidencia del póster para los criterios 10 y 11.

---

## Relaciones

```text
ResultadoSegmentacion (001)
    └─ mascara_linea
          └─> EstimadorLinea.aplicar()
                 └─> PosicionLinea  ──┐
                                       │
MaquinaEstados (001)                   │
    └─ DecisionMovimiento ─────────────┤
          (veredicto)                 │
                                       ▼
                            Compositor.arbitrar()
                                       │
                    ┌──────────────────┴──────────────────┐
                    ▼                                     ▼
        (veto NO_AUTORIZADO)              ControlTrayectoria.decidir()
                    │                                     │
                    │                            LadoConocido (memoria)
                    │                                     │
                    └────────────> DecisionCompuesta <────┘
                                          │
                                          ▼
                                 ColaTransporte.encolar()
                                          │
                          ┌───────────────┴───────────────┐
                          ▼                               ▼
                            TransporteSimulado        TransporteSPP (pyserial)
                          (pruebas)                   (hardware, fuera de visión/)
                                          │
                                          ▼
                                  MetricasControl
```

**Invariante de dependencia**: las flechas apuntan en un solo sentido. `src/vision/` no importa
`src/transporte/`; el CLI (`src/main.py`) es quien inyecta un transporte en la cola. Esto mantiene
`src/vision/` puro (patrón heredado de 001) y hace que las pruebas de control no necesiten hardware.

## Serialización

`ParametrosControl` se serializa dentro de `config/vision.json` (mismo archivo de 001, bloque de
control). `DecisionCompuesta` y `EventoControl` se vuelcan a las métricas de corrida con el formato
de `contracts/esquema-configuracion.md` y `contracts/api-control.md`. `PosicionLinea` **no** se
serializa por fotograma en el JSON de métricas (sería gigantic): se registra en la evidencia visual
y sus agregados (confianza media, velocidad de error) sí van a métricas.

## Fuera de este modelo

- **Telemetría del robot**: no hay lectura de sensores ni confirmaciones (unidireccional, US4).
- **Firmware del receptor**: la decodificación de tramas vive en el microcontrolador, fuera del
  repositorio.
- **Trayectoria o cartografía**: el robot no mapea la pista; sólo corrige cuadro a cuadro.
- **PID o control de velocidad**: imposible con la API de 4 comandos discretos (`research.md`
  Decisión 2).
- **`t_parada_s` y la semántica de la FSM**: intactos (decisión del equipo).
