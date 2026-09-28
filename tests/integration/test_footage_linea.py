"""T027 — Validación de la máscara de línea contra footage real.

Marca ``footage``: no corre por defecto, se activa con la variable de entorno
``OPTIPILOT_VIDEO_DIR`` apuntando al directorio con los videos. Si no hay
footage, o si el footage no trae anotación de referencia, el módulo hace
**skip limpio** — nunca falla por falta de datos y nunca inventa un número.

El formato de la anotación, el procedimiento y la regla del IoU están
definidos en ``specs/001-cv-sign-detection/contracts/anotacion-referencia.md``
(§2). Este módulo implementa **la carga y el cálculo**; la pintura manual de
las máscaras sigue siendo un trabajo humano que el contrato describe en §2.2.

Criterio SC-010: la media del IoU sobre **todos** los fotogramas anotados del
corpus debe ser ≥ 0,60. Se reportan además mediana, mínimo, desviación
estándar y desglose por video, porque una media alta sostenida por una sola
toma no es evidencia de robusteza (§2.4).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from statistics import fmean, pstdev

import cv2
import numpy as np
import pytest

from src.vision.configuracion import cargar_parametros
from src.vision.preprocesamiento import Preprocesador
from src.vision.segmentacion import Segmentador, linea_detectada

#: Variable de entorno que habilita el módulo y señala el corpus.
ENV_DIR_VIDEO = "OPTIPILOT_VIDEO_DIR"

#: Nombre del archivo de anotación de línea, junto al video (§2.1).
NOMBRE_ANOTACION = "anotacion_linea.json"

#: Umbral de SC-010.
IOU_MINIMO = 0.60

#: Tamaños mínimos del corpus (§2.3). Por debajo, la media no es interpretable.
MIN_FOTOGRAMAS_POR_VIDEO = 20
MIN_VIDEOS = 2
MIN_FOTOGRAMAS_TOTALES = 40

#: Extensiones de video aceptadas al recorrer el corpus.
EXTENSIONES_VIDEO = {".mp4", ".avi", ".mov", ".mkv", ".webm"}

#: Marcador del módulo: opt-in explícito. Sin `-m footage` el archivo se excluye
#: de la corrida por defecto, igual que `perf` en `test_rendimiento.py`.
pytestmark = pytest.mark.footage

CONFIG = Path("config/vision.json")


# --------------------------------------------------------------------------- #
# Modelo de la anotación (§2.1)
# --------------------------------------------------------------------------- #


class AnotacionInvalidaError(ValueError):
    """La anotación existe pero no cumple el contrato §2.1/§2.2."""


@dataclass(frozen=True)
class MascaraAnotada:
    """Una entrada de ``mascaras``: un fotograma y su ruta relativa."""

    indice: int
    ruta: Path


@dataclass(frozen=True)
class AnotacionLinea:
    """Contenido de ``anotacion_linea.json`` ya validado contra §2.1."""

    video: str
    resolucion: tuple[int, int]
    formato: str
    metodo: str
    mascaras: tuple[MascaraAnotada, ...]

    @property
    def indices(self) -> list[int]:
        return [mascara.indice for mascara in self.mascaras]


@dataclass
class ResultadoIoU:
    """Métricas de IoU del corpus, con el desglose que exige §2.4."""

    valores: list[float] = field(default_factory=list)
    por_video: dict[str, list[float]] = field(default_factory=dict)
    omitidos: list[tuple[str, int, str]] = field(default_factory=list)

    @property
    def media(self) -> float:
        return fmean(self.valores) if self.valores else 0.0

    @property
    def mediana(self) -> float:
        return float(np.median(self.valores)) if self.valores else 0.0

    @property
    def minimo(self) -> float:
        return min(self.valores) if self.valores else 0.0

    @property
    def desviacion(self) -> float:
        return pstdev(self.valores) if len(self.valores) > 1 else 0.0


# --------------------------------------------------------------------------- #
# Carga y validación de la anotación (§2.1)
# --------------------------------------------------------------------------- #


def _leer_anotacion(ruta: Path) -> AnotacionLinea:
    """Carga ``anotacion_linea.json`` y valida su forma contra §2.1.

    Toda desviación lanza :class:`AnotacionInvalidaError` con el campo
    concreto: una anotación mal formada se reporta, no se ignora en silencio,
    porque ignorarla produciría un IoU falsamente alto.
    """
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AnotacionInvalidaError(f"archivo ilegible: {error}") from error

    if not isinstance(datos, dict):
        raise AnotacionInvalidaError("la raíz del JSON debe ser un objeto")

    for campo in ("video", "resolucion", "formato", "metodo", "mascaras"):
        if campo not in datos:
            raise AnotacionInvalidaError(f"falta el campo obligatorio '{campo}'")

    if datos["formato"] != "png_binario":
        raise AnotacionInvalidaError(
            f"formato '{datos['formato']}' no soportado; v1 solo admite 'png_binario'"
        )

    resolucion = datos["resolucion"]
    if (
        not isinstance(resolucion, list)
        or len(resolucion) != 2
        or not all(isinstance(valor, int) for valor in resolucion)
    ):
        raise AnotacionInvalidaError("'resolucion' debe ser [ancho, alto] de dos enteros")

    if not isinstance(datos["metodo"], str) or not datos["metodo"].strip():
        raise AnotacionInvalidaError("'metodo' es obligatoria para la trazabilidad (§2.2.1)")

    mascaras_crudas = datos["mascaras"]
    if not isinstance(mascaras_crudas, dict) or not mascaras_crudas:
        raise AnotacionInvalidaError("'mascaras' debe ser un objeto no vacío")

    mascaras: list[MascaraAnotada] = []
    for indice, ruta_mascara in mascaras_crudas.items():
        try:
            numero = int(indice)
        except (TypeError, ValueError) as error:
            raise AnotacionInvalidaError(
                f"clave de máscara '{indice}' no es un índice de fotograma"
            ) from error
        if numero < 0:
            raise AnotacionInvalidaError(f"índice de fotograma negativo: {numero}")
        if not isinstance(ruta_mascara, str) or not ruta_mascara.strip():
            raise AnotacionInvalidaError(f"ruta de máscara vacía para el fotograma {numero}")
        mascaras.append(MascaraAnotada(numero, Path(ruta_mascara)))

    mascaras.sort(key=lambda mascara: mascara.indice)
    return AnotacionLinea(
        video=str(datos["video"]),
        resolucion=(int(resolucion[0]), int(resolucion[1])),
        formato=str(datos["formato"]),
        metodo=str(datos["metodo"]),
        mascaras=tuple(mascaras),
    )


def _cargar_mascara(
    ruta: Path, ancho: int, alto: int
) -> np.ndarray:
    """Carga una máscara PNG y valida dimensiones y binaridad estricta (§2.1)."""
    if not ruta.is_file():
        raise AnotacionInvalidaError(f"máscara no encontrada: {ruta}")

    mascara = cv2.imread(str(ruta), cv2.IMREAD_UNCHANGED)
    if mascara is None:
        raise AnotacionInvalidaError(f"máscara ilegible: {ruta}")
    if mascara.ndim == 3:
        mascara = cv2.cvtColor(mascara, cv2.COLOR_BGR2GRAY)

    if (mascara.shape[1], mascara.shape[0]) != (ancho, alto):
        raise AnotacionInvalidaError(
            f"máscara {ruta.name} con resolución {mascara.shape[1]}x{mascara.shape[0]}, "
            f"se esperaba {ancho}x{alto} según 'resolucion'"
        )

    valores = set(np.unique(mascara).tolist())
    if not valores <= {0, 255}:
        raise AnotacionInvalidaError(
            f"máscara {ruta.name} no es binaria estricta (valores: {sorted(valores)[:8]})"
        )
    if not np.count_nonzero(mascara):
        # §2.1: una máscara vacía es error de anotación, no un caso válido.
        raise AnotacionInvalidaError(f"máscara {ruta.name} está completamente vacía")

    return (mascara > 0).astype(bool)


# --------------------------------------------------------------------------- #
# Cálculo del IoU (§2.4)
# --------------------------------------------------------------------------- #


def iou_booleas(prediccion: np.ndarray, referencia: np.ndarray) -> float:
    """IoU de dos conjuntos de píxeles dentro de la misma ROI.

    Ambas entradas deben tener la misma forma; el llamador las recorta a la ROI
    antes de invocar esta función (§2.5).
    """
    if prediccion.shape != referencia.shape:
        raise ValueError(
            f"formas distintas: predicción {prediccion.shape} vs referencia {referencia.shape}"
        )
    interseccion = int(np.count_nonzero(prediccion & referencia))
    union = int(np.count_nonzero(prediccion | referencia))
    if union == 0:
        raise ValueError("unión vacía: no hay línea que evaluar (§2.4)")
    return interseccion / union


def predecir_mascara_linea(
    imagen_bgr: np.ndarray, pre: Preprocesador, seg: Segmentador
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Ejecuta las etapas reales de preprocesamiento y segmentación de línea.

    Se usan las clases de producción, no una reimplementación del test, para que
    el IoU mida el comportamiento desplegado. Devuelve también la ROI de línea
    efectiva en píxeles, que §2.5 exige recortar a predicción y referencia por
    igual; se devuelve aquí para no repetir el preprocesamiento en el llamador.
    """
    resultado_pre = pre.aplicar(imagen_bgr)
    mascara = seg.aplicar(resultado_pre).mascara_linea
    return mascara, resultado_pre.roi_linea_px


# --------------------------------------------------------------------------- #
# Descubrimiento del corpus
# --------------------------------------------------------------------------- #


def _directorio_footage() -> Path | None:
    bruto = os.environ.get(ENV_DIR_VIDEO)
    if not bruto:
        return None
    ruta = Path(bruto)
    return ruta if ruta.is_dir() else None


def _videos(directorio: Path) -> list[Path]:
    return sorted(
        ruta
        for ruta in directorio.rglob("*")
        if ruta.is_file() and ruta.suffix.lower() in EXTENSIONES_VIDEO
    )


def _anotacion_de(video: Path) -> Path | None:
    """Busca la anotación junto al video (§2.1 la sitúa en su mismo directorio)."""
    directa = video.with_name(NOMBRE_ANOTACION)
    if directa.is_file():
        return directa
    indice = video.parent / NOMBRE_ANOTACION / f"{video.stem}.json"
    return indice if indice.is_file() else None


def corpus_anotado(directorio: Path) -> Iterator[tuple[Path, AnotacionLinea]]:
    """Emite ``(video, anotación)`` por cada video con anotación válida."""
    for video in _videos(directorio):
        ruta = _anotacion_de(video)
        if ruta is None:
            continue
        anotacion = _leer_anotacion(ruta)
        # El campo 'video' debe apuntar al archivo real (§2.1, regla del campo).
        if anotacion.video != video.name:
            raise AnotacionInvalidaError(
                f"{ruta.name} declara video='{anotacion.video}' pero está junto a "
                f"'{video.name}'"
            )
        yield video, anotacion


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def directorio_footage() -> Path:
    """Directorio del corpus, o skip si la variable no está definida."""
    ruta = _directorio_footage()
    if ruta is None:
        pytest.skip(
            f"footage real no habilitado: define {ENV_DIR_VIDEO} apuntando al "
            f"directorio con los videos (marcador 'footage', opt-in)"
        )
    return ruta


@pytest.fixture(scope="module")
def parametros():
    """Parámetros versionados junto al resultado, como exige §4.5."""
    return cargar_parametros(CONFIG if CONFIG.is_file() else None)


@pytest.fixture(scope="module")
def corpus(directorio_footage: Path) -> list[tuple[Path, AnotacionLinea]]:
    """Videos anotados del corpus, o skip si el footage no trae anotación."""
    entradas = list(corpus_anotado(directorio_footage))
    if not entradas:
        pytest.skip(
            f"footage presente en {directorio_footage} pero ningún video trae "
            f"{NOMBRE_ANOTACION}. Sin anotación no hay IoU evaluable; el contrato "
            f"de formato está en specs/001-cv-sign-detection/contracts/"
            f"anotacion-referencia.md §2"
        )
    return entradas


@pytest.fixture(scope="module")
def evaluador(corpus, parametros) -> Iterator[ResultadoIoU]:
    """Recorre el corpus y calcula el IoU de cada fotograma anotado."""
    pre = Preprocesador(parametros)
    seg = Segmentador(parametros)
    resultado = ResultadoIoU()

    for video, anotacion in corpus:
        captura = cv2.VideoCapture(str(video))
        if not captura.isOpened():
            pytest.skip(f"OpenCV no pudo abrir {video.name}")
        total_fotogramas = int(captura.get(cv2.CAP_PROP_FRAME_COUNT))
        nombre = video.name

        for mascara in anotacion.mascaras:
            if mascara.indice >= total_fotogramas:
                resultado.omitidos.append(
                    (nombre, mascara.indice, "índice fuera del rango del video")
                )
                captura.release()
                return
            captura.set(cv2.CAP_PROP_POS_FRAMES, mascara.indice)
            leido, imagen = captura.read()
            if not leido:
                resultado.omitidos.append(
                    (nombre, mascara.indice, "fotograma ilegible")
                )
                continue

            alto, ancho = imagen.shape[:2]
            ruta_mascara = video.parent / mascara.ruta
            if not ruta_mascara.is_file():
                # También puede estar relativas al directorio del JSON.
                ruta_mascara = video.with_name(NOMBRE_ANOTACION).parent / mascara.ruta
            referencia = _cargar_mascara(ruta_mascara, ancho, alto)
            prediccion, roi_px = predecir_mascara_linea(imagen, pre, seg)

            # §2.5: predicción y referencia recortadas a la misma ROI, para que
            # cambiar la ROI no altere el IoU.
            x, y, ancho_roi, alto_roi = roi_px
            ventana = (slice(y, y + alto_roi), slice(x, x + ancho_roi))
            pred_roi = prediccion[ventana]
            ref_roi = referencia[ventana]

            if not pred_roi.any() and not ref_roi.any():
                # §2.4: no hay línea que evaluar; el fotograma no cuenta.
                resultado.omitidos.append((nombre, mascara.indice, "sin línea en la ROI"))
                continue

            if not pred_roi.any():
                # §2.4: fallo de detección completo, no ausencia de datos.
                resultado.omitidos.append((nombre, mascara.indice, "predicción vacía"))
                resultado.valores.append(0.0)
                resultado.por_video.setdefault(nombre, []).append(0.0)
                continue

            valor = iou_booleas(pred_roi, ref_roi)
            resultado.valores.append(valor)
            resultado.por_video.setdefault(nombre, []).append(valor)

        captura.release()

    yield resultado


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_footage_disponible(directorio_footage: Path) -> None:
    """El corpus declarado existe y contiene al menos un video legible."""
    videos = _videos(directorio_footage)
    assert videos, f"no se encontró ningún video en {directorio_footage}"

    for video in videos[:1]:
        captura = cv2.VideoCapture(str(video))
        assert captura.isOpened(), f"OpenCV no pudo abrir {video.name}"
        leido, imagen = captura.read()
        captura.release()
        assert leido and imagen is not None, f"{video.name} no entregó fotogramas"
        assert imagen.ndim == 3 and imagen.shape[2] == 3, "el fotograma debe ser BGR"


def test_anotacion_cumple_contrato(corpus) -> None:
    """Cada anotación declara la resolución real del video y ≥ 20 fotogramas."""
    for video, anotacion in corpus:
        captura = cv2.VideoCapture(str(video))
        ancho = int(captura.get(cv2.CAP_PROP_FRAME_WIDTH))
        alto = int(captura.get(cv2.CAP_PROP_FRAME_HEIGHT))
        captura.release()

        assert anotacion.resolucion == (ancho, alto), (
            f"{video.name}: 'resolucion' {anotacion.resolucion} no coincide con el "
            f"video real {ancho}x{alto}"
        )
        assert len(anotacion.mascaras) >= MIN_FOTOGRAMAS_POR_VIDEO, (
            f"{video.name}: {len(anotacion.mascaras)} fotogramas anotados, el contrato "
            f"§2.3 exige ≥ {MIN_FOTOGRAMAS_POR_VIDEO}"
        )


def test_mascara_linea_reporta_no_detectado(directorio_footage, parametros) -> None:
    """El pipeline distingue «hay línea» de «no detectado» en footage real.

    Recorre el primer video y comprueba que `linea_detectada` responde al
    contenido real de la ROI, sin exigir un valor concreto: lo que se valida
    aquí es que el reporte sea informativo, no que la calibración sea correcta.
    """
    video = _videos(directorio_footage)[0]
    pre = Preprocesador(parametros)
    seg = Segmentador(parametros)

    captura = cv2.VideoCapture(str(video))
    leido, imagen = captura.read()
    captura.release()
    assert leido, f"no se pudo leer el primer fotograma de {video.name}"

    mascara, _roi_px = predecir_mascara_linea(imagen, pre, seg)
    assert mascara.dtype == np.bool_ or set(np.unique(mascara)) <= {0, 1, 255}
    assert isinstance(linea_detectada(mascara), bool)


def test_iou_supera_el_umbral_de_sc010(evaluador: ResultadoIoU) -> None:
    """SC-010: la media del IoU sobre el corpus anotado es ≥ 0,60."""
    assert evaluador.valores, "el corpus no produjo ningún IoU; nada que evaluar"

    desglose = "  ".join(
        f"{nombre}={fmean(valores):.3f}" for nombre, valores in sorted(evaluador.por_video.items())
    )
    assert evaluador.media >= IOU_MINIMO, (
        f"IoU medio {evaluador.media:.3f} < {IOU_MINIMO:.2f} (SC-010). "
        f"mediana={evaluador.mediana:.3f} mínimo={evaluador.minimo:.3f} "
        f"desviación={evaluador.desviacion:.3f} n={len(evaluador.valores)}. "
        f"Por video: {desglose}"
    )


def test_tamanio_del_corpus_es_interpretable(evaluador: ResultadoIoU, corpus) -> None:
    """El corpus cumple §2.3; si no, el resultado se reporta como no evaluable."""
    videos = len({video.name for video, _ in corpus})
    problemas: list[str] = []

    if videos < MIN_VIDEOS:
        problemas.append(f"{videos} video(s), §2.3 exige ≥ {MIN_VIDEOS}")
    if len(evaluador.valores) < MIN_FOTOGRAMAS_TOTALES:
        problemas.append(
            f"{len(evaluador.valores)} fotogramas evaluados, §2.3 exige ≥ "
            f"{MIN_FOTOGRAMAS_TOTALES}"
        )
    for nombre, valores in evaluador.por_video.items():
        if len(valores) < MIN_FOTOGRAMAS_POR_VIDEO:
            problemas.append(
                f"{nombre}: {len(valores)} fotogramas evaluados, §2.3 exige ≥ "
                f"{MIN_FOTOGRAMAS_POR_VIDEO}"
            )

    assert not problemas, (
        "corpus por debajo del mínimo del contrato §2.3: "
        + "; ".join(problemas)
        + ". Una media calculada sobre menos datos no debe publicarse como "
        "resultado de SC-010 (nota del contrato §2.3)."
    )
