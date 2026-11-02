"""Adaptador ONNX del clasificador de señales (specs/004).

Es la única frontera de E/S del modelo en el runtime: `src/vision/` no importa
ONNX ni TensorFlow. El modelo se carga una vez y se reutiliza en cada recorte.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from src.vision.modelos import ClaseSenal, ClaseSenalExtra, PrediccionSenal

__all__ = ["ClasificadorONNX"]

_FABRICA_SESION = Callable[[str], Any]

_MAPA_SENAL: dict[str, ClaseSenal] = {
    "PARE": ClaseSenal.PARE,
    "SIGA": ClaseSenal.SIGA,
}
_MAPA_EXTRA: dict[str, ClaseSenalExtra] = {
    "ZONA ESCOLAR": ClaseSenalExtra.ZONA_ESCOLAR,
    "VELOCIDAD 60": ClaseSenalExtra.VELOCIDAD_60,
}


def _sha256(ruta: Path) -> str:
    digest = hashlib.sha256()
    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def _crear_sesion(ruta: str) -> Any:
    import onnxruntime as ort

    opciones = ort.SessionOptions()
    # El valor automático (0) usa demasiados hilos para MobileNet y añade
    # sobrecarga: medido en el portátil de desarrollo, 35.8 ms de media frente a
    # 7.4 ms con 4 hilos. Cuatro hilos mantienen la inferencia bajo el
    # presupuesto de 15 ms sin acaparar la CPU del bucle de visión.
    opciones.intra_op_num_threads = min(4, os.cpu_count() or 1)
    opciones.inter_op_num_threads = 1
    return ort.InferenceSession(
        ruta, sess_options=opciones, providers=["CPUExecutionProvider"]
    )


def _desconocida() -> PrediccionSenal:
    return PrediccionSenal(
        clase="DESCONOCIDA",
        confianza=0.0,
        probabilidades={},
    )


class ClasificadorONNX:
    """Carga un MobileNet exportado a ONNX y clasifica recortes BGR."""

    def __init__(
        self,
        ruta_modelo: str | Path,
        ruta_metadatos: str | Path,
        fabrica_sesion: _FABRICA_SESION | None = None,
    ) -> None:
        self._ruta_modelo = Path(ruta_modelo)
        self._ruta_metadatos = Path(ruta_metadatos)
        if not self._ruta_modelo.is_file():
            raise FileNotFoundError(f"No se encontró el modelo ONNX: {self._ruta_modelo}")
        if not self._ruta_metadatos.is_file():
            raise FileNotFoundError(
                f"No se encontró la metadata del modelo: {self._ruta_metadatos}"
            )

        self._metadatos = self._cargar_metadatos(self._ruta_metadatos)
        self._tamano = self._leer_tamano(self._metadatos)
        self._clases = self._leer_clases(self._metadatos)
        self._verificar_hash(self._ruta_modelo, self._metadatos)
        self._sesion = (fabrica_sesion or _crear_sesion)(str(self._ruta_modelo))
        self._entrada = self._sesion.get_inputs()[0].name
        self._cerrado = False

    @staticmethod
    def _cargar_metadatos(ruta: Path) -> dict[str, Any]:
        with ruta.open(encoding="utf-8") as archivo:
            datos = json.load(archivo)
        if not isinstance(datos, dict):
            raise ValueError("la metadata del modelo debe ser un objeto JSON")
        if datos.get("preproceso") != "mobilenet_tf":
            raise ValueError("preproceso no soportado: se esperaba 'mobilenet_tf'")
        if datos.get("canal") != "RGB":
            raise ValueError("canal no soportado: se esperaba 'RGB'")
        return datos

    @staticmethod
    def _leer_tamano(metadatos: dict[str, Any]) -> tuple[int, int]:
        tamano = metadatos.get("tamano_entrada")
        if not isinstance(tamano, list) or len(tamano) != 2:
            raise ValueError("tamano_entrada debe ser [alto, ancho]")
        alto, ancho = int(tamano[0]), int(tamano[1])
        if alto <= 0 or ancho <= 0:
            raise ValueError("tamano_entrada debe ser positivo")
        return alto, ancho

    @staticmethod
    def _leer_clases(metadatos: dict[str, Any]) -> dict[int, str]:
        bruto = metadatos.get("clases")
        if not isinstance(bruto, dict) or not bruto:
            raise ValueError("la metadata no contiene el mapa de clases")
        clases: dict[int, str] = {}
        for indice, nombre in bruto.items():
            try:
                clave = int(indice)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"índice de clase inválido: {indice!r}") from exc
            if not isinstance(nombre, str) or not nombre:
                raise ValueError(f"nombre de clase inválido para el índice {clave}")
            clases[clave] = nombre
        return clases

    @staticmethod
    def _verificar_hash(ruta: Path, metadatos: dict[str, Any]) -> None:
        esperado = metadatos.get("sha256")
        if not isinstance(esperado, str) or not esperado:
            return
        if _sha256(ruta) != esperado:
            raise ValueError("el SHA-256 del modelo ONNX no coincide con la metadata")

    def clasificar(self, imagen_bgr: np.ndarray) -> PrediccionSenal:
        """Clasifica un recorte BGR. Una imagen inválida devuelve ``DESCONOCIDA``."""
        if self._cerrado or self._sesion is None:
            return _desconocida()
        if (
            imagen_bgr is None
            or imagen_bgr.ndim != 3
            or imagen_bgr.shape[2] != 3
            or imagen_bgr.size == 0
        ):
            return _desconocida()
        try:
            lote = self._preprocesar(imagen_bgr)
            salida = self._sesion.run(None, {self._entrada: lote})[0]
            probabilidades = np.asarray(salida, dtype=np.float32)
            if probabilidades.ndim != 2 or probabilidades.shape[0] != 1:
                return _desconocida()
            vector = probabilidades[0]
            if vector.size != len(self._clases):
                return _desconocida()
            vector = self._como_probabilidades(vector)
            if vector is None:
                return _desconocida()
            indice = int(np.argmax(vector))
            etiqueta = self._clases.get(indice)
            if etiqueta is None:
                return _desconocida()
            return self._prediccion(etiqueta, float(vector[indice]), vector)
        except Exception:
            return _desconocida()

    def cerrar(self) -> None:
        """Libera la sesión ONNX. Idempotente."""
        self._sesion = None
        self._cerrado = True

    def _preprocesar(self, imagen_bgr: np.ndarray) -> np.ndarray:
        rgb = cv2.cvtColor(imagen_bgr, cv2.COLOR_BGR2RGB)
        alto, ancho = self._tamano
        redimensionada = cv2.resize(rgb, (ancho, alto), interpolation=cv2.INTER_AREA)
        arreglo = redimensionada.astype(np.float32) / 127.5 - 1.0
        return np.expand_dims(arreglo, axis=0)

    @staticmethod
    def _como_probabilidades(vector: np.ndarray) -> np.ndarray | None:
        if not np.all(np.isfinite(vector)):
            return None
        if np.all(vector >= 0.0) and np.all(vector <= 1.0):
            total = float(np.sum(vector))
            if abs(total - 1.0) <= 1e-3:
                return vector
        desplazado = vector - float(np.max(vector))
        exponencial = np.exp(desplazado)
        total = float(np.sum(exponencial))
        if total <= 0.0 or not np.isfinite(total):
            return None
        return exponencial / total

    def _prediccion(
        self,
        etiqueta: str,
        confianza: float,
        vector: np.ndarray,
    ) -> PrediccionSenal:
        probabilidades = {
            self._clases[indice]: float(valor)
            for indice, valor in enumerate(vector)
            if indice in self._clases
        }
        return PrediccionSenal(
            clase=etiqueta,
            confianza=confianza,
            probabilidades=probabilidades,
            clase_senal=_MAPA_SENAL.get(etiqueta),
            clase_extra=_MAPA_EXTRA.get(etiqueta),
        )
