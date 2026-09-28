"""CLI de validación de OptiPilot: corre el pipeline sobre una fuente y deja evidencia.

Es el único punto del proyecto que abre archivos, escribe en disco e imprime.
``src/vision/`` permanece puro (contrato ``api-pipeline.md``: *«src/vision/ es
puro: no captura cámara, no abre archivos, no imprime; el I/O vive en
src/main.py, metricas.exportar() y visualizacion»*).

Uso::

    python -m src.main --fuente <ruta_video|directorio_imagenes|indice_camara>
                       [--config config/vision.json]
                       [--diagnostico]
                       [--salida salidas/<corrida>]
                       [--max-fotogramas N]
                       [--anotacion refs.json]

Códigos de salida: ``0`` corrida completada, ``1`` error de ejecución,
``2`` configuración o fuente invalida.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator, Sequence
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from src.vision.configuracion import (
    ConfiguracionInvalidaError,
    ParametrosConfiguracion,
    cargar_parametros,
)
from src.vision.maquina_estados import MaquinaEstados
from src.vision.metricas import MetricasCorrida
from src.vision.modelos import (
    ClaseSenal,
    EstadoRobot,
    MarcadorVisibilidadPlena,
    Parada,
)
from src.vision.pipeline import PipelineVision
from src.vision.visualizacion import anotar

CODIGO_OK = 0
CODIGO_ERROR_EJECUCION = 1
CODIGO_ENTRADA_INVALIDA = 2

_EXTENSIONES_IMAGEN = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"})


class FuenteInvalidaError(ValueError):
    """La fuente de fotogramas no existe, no se puede abrir o está vacía."""


# -- fuente de fotogramas --------------------------------------------------


def _es_indice_camara(fuente: str) -> bool:
    return fuente.isdigit()


def _abrir_video(ruta: Path) -> tuple[cv2.VideoCapture, float]:
    captura = cv2.VideoCapture(str(ruta))
    if not captura.isOpened():
        captura.release()
        raise FuenteInvalidaError(f"no se pudo abrir el video: {ruta}")
    fps = float(captura.get(cv2.CAP_PROP_FPS))
    if not np.isfinite(fps) or fps <= 0:
        fps = 0.0
    return captura, fps


def _iterar_fotogramas(
    fuente: str,
    fps_por_defecto: float,
    max_fotogramas: int | None,
) -> Iterator[tuple[int, float, np.ndarray]]:
    """Itera ``(indice, t_s, imagen)`` desde un video, un directorio o una cámara.

    ``t_s`` se deriva del índice y del fps para que la máquina de estados reciba
    tiempos reproducibles (el cronómetro T se calcula con ``t_s``, FR-017).
    """
    if _es_indice_camara(fuente):
        captura = cv2.VideoCapture(int(fuente))
        if not captura.isOpened():
            captura.release()
            raise FuenteInvalidaError(f"no se pudo abrir la cámara {fuente}")
        fps = float(captura.get(cv2.CAP_PROP_FPS))
        if not np.isfinite(fps) or fps <= 0:
            fps = fps_por_defecto
        try:
            yield from _iterar_captura(captura, fps, max_fotogramas)
        finally:
            captura.release()
        return

    ruta = Path(fuente)
    if ruta.is_dir():
        yield from _iterar_directorio(ruta, fps_por_defecto, max_fotogramas)
        return
    if not ruta.exists():
        raise FuenteInvalidaError(f"la fuente no existe: {fuente}")

    captura, fps = _abrir_video(ruta)
    if fps <= 0:
        fps = fps_por_defecto
    try:
        yield from _iterar_captura(captura, fps, max_fotogramas)
    finally:
        captura.release()


def _iterar_captura(
    captura: cv2.VideoCapture,
    fps: float,
    max_fotogramas: int | None,
) -> Iterator[tuple[int, float, np.ndarray]]:
    indice = 0
    while max_fotogramas is None or indice < max_fotogramas:
        exito, imagen = captura.read()
        if not exito or imagen is None:
            return
        yield indice, indice / fps, imagen
        indice += 1


def _iterar_directorio(
    directorio: Path,
    fps: float,
    max_fotogramas: int | None,
) -> Iterator[tuple[int, float, np.ndarray]]:
    rutas = sorted(
        ruta for ruta in directorio.iterdir() if ruta.suffix.lower() in _EXTENSIONES_IMAGEN
    )
    if not rutas:
        raise FuenteInvalidaError(f"el directorio no contiene imágenes: {directorio}")
    for indice, ruta in enumerate(rutas):
        if max_fotogramas is not None and indice >= max_fotogramas:
            return
        imagen = cv2.imread(str(ruta))
        if imagen is None:
            # Un archivo ilegible no aborta la corrida: es degradación controlada.
            print(f"[aviso] fotograma ilegible, se omite: {ruta}", file=sys.stderr)
            continue
        yield indice, indice / fps, imagen


# -- anotación de referencia (opcional) --------------------------------------


class Referencia:
    """Anotación de señales físicas por rango de fotogramas (Q3, FR-025).

    Formato JSON: una lista de ``{"clase": "PARE", "fotograma_inicio": int,
    "fotograma_fin": int}``. Sin este archivo el módulo solo aporta conteos y
    eventos, y las tasas de aceptación las calcula el flujo de análisis.
    """

    def __init__(self, tramos: Sequence[dict]) -> None:
        self._tramos = list(tramos)

    @classmethod
    def vacia(cls) -> "Referencia":
        return cls([])

    @classmethod
    def cargar(cls, ruta: Path) -> "Referencia":
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ConfiguracionInvalidaError("anotacion", str(error)) from error
        if not isinstance(datos, list):
            raise ConfiguracionInvalidaError(
                "anotacion", "se esperaba una lista de tramos"
            )
        return cls(datos)

    @property
    def tiene_tramos(self) -> bool:
        """Si hay anotación de referencia disponible para juzgar las detecciones."""
        return bool(self._tramos)

    def consultar(self, fotograma_idx: int) -> tuple[bool, ClaseSenal | None]:
        """Devuelve ``(anotada, clase_anotada)`` para ese fotograma."""
        for tramo in self._tramos:
            inicio = int(tramo.get("fotograma_inicio", 0))
            fin = int(tramo.get("fotograma_fin", inicio))
            if inicio <= fotograma_idx <= fin:
                return True, ClaseSenal(str(tramo["clase"]).upper())
        return False, None


# -- corrida ---------------------------------------------------------------


def _resolver_salida(salida: str | None) -> tuple[Path, str]:
    """Devuelve ``(directorio, corrida_id)``; sin ``--salida`` usa marca de tiempo."""
    if salida:
        directorio = Path(salida)
        return directorio, directorio.name or "corrida"
    corrida_id = "corrida_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("salidas") / corrida_id, corrida_id


def _resumen_consola(resumen: dict) -> str:
    lineas = [
        "=== Resumen de corrida ===",
        f"corrida_id          : {resumen['corrida_id']}",
        f"fuente              : {resumen['fuente']}",
        f"fotogramas          : {resumen['frames_procesados']}",
        f"ocurrencias PARE    : {resumen['ocurrencias_pare']}",
        f"ocurrencias SIGA    : {resumen['ocurrencias_siga']}",
        f"detecciones correctas: {resumen['detecciones_correctas']}",
        f"falsos positivos    : {resumen['falsos_positivos']}",
        f"confusiones         : {resumen['confusiones']}",
        f"paradas             : {len(resumen['paradas'])}",
    ]
    for indice, parada in enumerate(resumen["paradas"], start=1):
        lineas.append(
            f"  parada {indice}: inicio={parada['inicio_t']:.2f}s "
            f"T={parada['t_configurado_s']:.2f}s fin={parada['fin_t']:.2f}s "
            f"retardo={parada['retardo_s']:.2f}s"
        )
    latencias = resumen["latencias_frames"]
    lineas.append(
        f"latencia decision   : {latencias if latencias else 'sin datos'} (fotogramas)"
    )
    lineas.append(f"fps promedio        : {resumen['fps_promedio']:.2f}")
    lineas.append(
        f"latencia proc.      : media={resumen['latencia_media_ms']:.2f} ms "
        f"p95={resumen['latencia_p95_ms']:.2f} ms"
    )
    return "\n".join(lineas)


def _correr(
    params: ParametrosConfiguracion,
    fuente: str,
    diagnostico: bool,
    directorio: Path,
    corrida_id: str,
    max_fotogramas: int | None,
    referencia: Referencia,
) -> MetricasCorrida:
    """Recorre la fuente componiendo pipeline, máquina de estados y métricas."""
    pipeline = PipelineVision(params)
    maquina = MaquinaEstados(params, t_inicial=0.0)
    metricas = MetricasCorrida(corrida_id=corrida_id, fuente=fuente)

    frames = None
    if diagnostico:
        frames = directorio / "frames"
        frames.mkdir(parents=True, exist_ok=True)

    marcadores: dict[ClaseSenal, MarcadorVisibilidadPlena] = {}
    inicio_parada: float | None = None

    for indice, t_s, imagen in _iterar_fotogramas(fuente, params.fps_objetivo, max_fotogramas):
        resultado = pipeline.procesar(indice, t_s, imagen)

        for marcador in resultado.visibilidad_plena:
            marcadores.setdefault(marcador.clase, marcador)

        for evento in resultado.eventos:
            metricas.registrar_evento(evento)

        presentes = frozenset(senal.clase for senal in resultado.senales_confirmadas)
        estado = maquina.actualizar(presentes, resultado.eventos, t_s)

        for transicion in estado.transiciones_nuevas:
            metricas.registrar_transicion(transicion)

        for senal in resultado.senales_confirmadas:
            if referencia.tiene_tramos:
                anotada, clase_anotada = referencia.consultar(senal.fotograma_idx)
            else:
                # Sin referencia el módulo solo cuenta ocurrencias y no juzga acierto.
                anotada, clase_anotada = None, None
            metricas.registrar_senal(
                senal,
                anotada=anotada,
                clase_anotada=clase_anotada,
            )
            marcador = marcadores.get(senal.clase)
            if marcador is not None:
                metricas.registrar_latencia_desde_marcador(
                    marcador, senal.fotograma_idx, senal.t_s
                )

        metricas.registrar_fotograma(resultado.latencia_ms, t_s)

        if inicio_parada is None and estado.estado is not EstadoRobot.EN_MARCHA:
            inicio_parada = t_s
        if estado.estado is EstadoRobot.EN_MARCHA and inicio_parada is not None:
            metricas.registrar_parada(
                Parada.crear(
                    inicio_t=inicio_parada,
                    t_configurado_s=params.t_parada_s,
                    fin_t=t_s,
                )
            )
            inicio_parada = None

        if frames is not None:
            cv2.imwrite(str(frames / f"frame_{indice:06d}.png"), anotar(imagen, resultado, estado))

    return metricas


def _parsear_args(argv: Sequence[str] | None) -> argparse.Namespace:
    analizador = argparse.ArgumentParser(
        prog="python -m src.main",
        description="CLI de validación de OptiPilot (visión clásica, sin IA entrenada).",
    )
    analizador.add_argument(
        "--fuente",
        required=True,
        help="ruta de video, directorio de imágenes o índice de cámara",
    )
    analizador.add_argument(
        "--config",
        default="config/vision.json",
        help="ruta del JSON de configuración (por defecto: config/vision.json)",
    )
    analizador.add_argument(
        "--diagnostico",
        action="store_true",
        help="escribe fotogramas anotados por etapa (SC-012)",
    )
    analizador.add_argument(
        "--salida",
        default=None,
        help="directorio de salida; por defecto salidas/<corrida_id>",
    )
    analizador.add_argument(
        "--max-fotogramas",
        type=int,
        default=None,
        help="procesa como máximo N fotogramas",
    )
    analizador.add_argument(
        "--anotacion",
        default=None,
        help="JSON de referencia para confrontar detecciones (opcional, FR-025)",
    )
    return analizador.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada del CLI; devuelve el código de salida del contrato."""
    args = _parsear_args(argv)

    try:
        params = cargar_parametros(Path(args.config) if args.config else None)
    except ConfiguracionInvalidaError as error:
        print(f"[error] configuracion invalida: {error}", file=sys.stderr)
        return CODIGO_ENTRADA_INVALIDA

    referencia = Referencia.vacia()
    if args.anotacion:
        try:
            referencia = Referencia.cargar(Path(args.anotacion))
        except ConfiguracionInvalidaError as error:
            print(f"[error] {error}", file=sys.stderr)
            return CODIGO_ENTRADA_INVALIDA

    directorio, corrida_id = _resolver_salida(args.salida)

    try:
        metricas = _correr(
            params=params,
            fuente=args.fuente,
            diagnostico=args.diagnostico,
            directorio=directorio,
            corrida_id=corrida_id,
            max_fotogramas=args.max_fotogramas,
            referencia=referencia,
        )
    except FuenteInvalidaError as error:
        print(f"[error] fuente invalida: {error}", file=sys.stderr)
        return CODIGO_ENTRADA_INVALIDA
    except ConfiguracionInvalidaError as error:
        print(f"[error] configuracion invalida: {error}", file=sys.stderr)
        return CODIGO_ENTRADA_INVALIDA

    try:
        ruta_eventos, ruta_metricas = metricas.exportar(directorio)
    except OSError as error:
        print(f"[error] no se pudieron escribir los artefactos: {error}", file=sys.stderr)
        return CODIGO_ERROR_EJECUCION

    print(_resumen_consola(metricas.resumen()))
    print(f"eventos  : {ruta_eventos}")
    print(f"metricas  : {ruta_metricas}")
    return CODIGO_OK


if __name__ == "__main__":
    sys.exit(main())
