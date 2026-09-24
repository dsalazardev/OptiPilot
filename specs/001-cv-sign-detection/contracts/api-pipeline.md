# Contrato — API pública del módulo de visión (Python)

**Feature**: `specs/001-cv-sign-detection` | **Date**: 2026-09-24

Fachada estable del pipeline. Los nombres son contractuales; los cuerpos de función son
implementación (ver `tasks.md`). `src/vision/` es puro: no captura cámara, no abre archivos, no
imprime; el I/O vive en `src/main.py`, `metricas.exportar()` y `visualizacion` (guardado explícito).

## Configuración (`src.vision.configuracion`)

```python
class ConfiguracionInvalidaError(ValueError): ...

def cargar_parametros(ruta: Path | None = None) -> ParametrosConfiguracion:
    """Defaults embebidos + JSON opcional; valida y falla con campo y motivo."""

ParametrosConfiguracion.por_defecto() -> ParametrosConfiguracion
```

- `ParametrosConfiguracion` es inmutable (frozen) y serializable a JSON.
- Todos los parámetros de FR-024 provienen de aquí; ninguna etapa usa constantes no configurables.

## Pipeline por fotograma (`src.vision.pipeline`)

```python
class PipelineVision:
    def __init__(self, params: ParametrosConfiguracion) -> None: ...
    def procesar(self, indice: int, t_s: float, imagen_bgr: np.ndarray) -> ResultadoProcesamiento: ...
```

- `ResultadoProcesamiento`: `segmentacion`, `candidatos`, `senales_confirmadas`, `eventos`,
  `latencia_ms` y el marcador de **visibilidad plena** por señal (primer fotograma completamente
  dentro de la ROI y área ≥ mínima; base de SC-006) (ver `data-model.md` §12).
- Determinista y sin estado oculto más allá del necesario para confirmación temporal (N/K/X);
  procesar la misma secuencia produce siempre el mismo resultado.
- Un fotograma vacío o ilegible devuelve un resultado con máscaras vacías y sin excepción (FR-014).

## Máquina de estados (`src.vision.maquina_estados`)

```python
class MaquinaEstados:
    def __init__(self, params: ParametrosConfiguracion, t_inicial: float) -> None: ...
    def actualizar(
        self,
        presentes: frozenset[ClaseSenal],
        eventos: Sequence[EventoSenal],
        t_s: float,
    ) -> ResultadoEstado: ...

    @property
    def estado(self) -> EstadoRobot: ...
    @property
    def decision(self) -> DecisionMovimiento: ...
```

- `ResultadoEstado`: `estado`, `decision`, `transiciones_nuevas: list[TransicionEstado]`.
- `presentes` = clases en estado confirmado en el fotograma (incluye señales co-visibles ya
  confirmadas al detenerse: Q-A).
- El cronómetro T se calcula con `t_s` (inyectable ⇒ pruebas deterministas de US2).
- SALIDA del módulo hacia la capa de control: `DecisionMovimiento` (`AUTORIZADO` /
  `NO_AUTORIZADO`). No hay control de motores en este módulo.

## Métricas (`src.vision.metricas`)

```python
class MetricasCorrida:
    def __init__(self, corrida_id: str, fuente: str) -> None: ...
    def registrar_fotograma(self, latencia_ms: float) -> None: ...
    def registrar_evento(self, evento: EventoSenal) -> None: ...
    def registrar_transicion(self, transicion: TransicionEstado) -> None: ...
    def registrar_senal(self, senal: SenalConfirmada, anotada: bool) -> None: ...
    def registrar_parada(self, parada: Parada) -> None: ...
    def registrar_decision_latencia(self, frames: int, ms: float) -> None:
        """Latencia por ocurrencia: del marcador de visibilidad plena (Q2) a la decisión."""
    def resumen(self) -> dict: ...
    def exportar(self, directorio: Path) -> tuple[Path, Path]:
        """Escribe eventos.jsonl y metricas.json; devuelve sus rutas."""
```

- Esquemas exactos en `contracts/esquema-eventos-metricas.md`.
- Las transiciones de estado se registran con `registrar_transicion` y se vuelcan como eventos
  `TRANSICION` (origen, destino, causa y momento) en `eventos.jsonl` (FR-023).
- No decide la aceptación: solo registra; la comparación contra la anotación de referencia la hace
  el flujo de análisis (FR-025, Q3).

## Visualización (`src.vision.visualizacion`)

```python
def anotar(imagen_bgr: np.ndarray, resultado: ResultadoProcesamiento,
           estado: ResultadoEstado | None = None) -> np.ndarray:
    """Devuelve una copia anotada (máscaras, contornos, clase, estado y decisión). No guarda."""
```

## CLI de validación (`src.main`)

```text
python -m src.main --fuente <ruta_video|directorio_imagenes|indice_camara>
                   [--config config/vision.json]
                   [--diagnostico]          # activa anotación por etapa
                   [--salida salidas/<corrida>]
                   [--max-fotogramas N]
```

- Salida en consola: resumen de la corrida (fotogramas, ocurrencias, paradas, latencias).
- `--diagnostico` escribe fotogramas anotados y `eventos.jsonl`/`metricas.json` en `--salida`.
- **Códigos de salida**: `0` corrida completada; `1` error de ejecución; `2` configuración o fuente
  inválida.
- Headless por defecto (sin ventanas); funciona en CI local y en la máquina del robot.

## Garantías de contrato

1. **Determinismo**: mismas entradas + misma configuración ⇒ mismas salidas (Principio IV).
2. **Cumplimiento Reto 1**: toda la lógica de segmentación/detección es propia, sobre primitivas
   autorizadas de OpenCV; ningún submódulo que detecte automáticamente (DNN, ArUco, QR, etc.).
3. **Sin secretos ni red**: el módulo no usa red, credenciales ni servicios externos.
4. **Errores explícitos**: configuración inválida ⇒ `ConfiguracionInvalidaError`; fuente ilegible ⇒
   error del CLI con código 2; fotograma vacío ⇒ degradación controlada (FR-014).
