"""Fixtures compartidas de la suite (T007)."""

from __future__ import annotations

import numpy as np
import pytest

from src.vision.configuracion import ParametrosConfiguracion


@pytest.fixture()
def parametros_por_defecto() -> ParametrosConfiguracion:
    """Configuración por defecto del contrato, ya validada."""
    return ParametrosConfiguracion.por_defecto()


@pytest.fixture()
def rng() -> np.random.Generator:
    """Generador aleatorio con semilla fija (pruebas deterministas)."""
    return np.random.default_rng(20260924)
