"""Contrato del clasificador de señales (specs/004)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

from src.vision.modelos import PrediccionSenal

__all__ = ["ClasificadorSenales"]


@runtime_checkable
class ClasificadorSenales(Protocol):
    """Clasifica un recorte BGR y devuelve una predicción de señal."""

    def clasificar(self, imagen_bgr: np.ndarray) -> PrediccionSenal:
        """Devuelve la predicción para ``imagen_bgr``; nunca lanza por una imagen inválida."""
        ...

    def cerrar(self) -> None:
        """Libera la sesión. Idempotente."""
        ...
