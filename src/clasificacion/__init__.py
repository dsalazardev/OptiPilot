"""Clasificación CNN de señales (frontend ONNX, sin TensorFlow en runtime)."""

from .base import ClasificadorSenales
from .onnx import ClasificadorONNX

__all__ = ["ClasificadorONNX", "ClasificadorSenales"]
