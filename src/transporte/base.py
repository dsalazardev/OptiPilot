"""Contrato del transporte hacia el robot (data-model §8, FR-030).

Deliberadamente un ``Protocol`` y no una clase base: las pruebas inyectan
``TransporteSimulado`` sin herencia, y ``src/vision/`` no depende de nada de
``pyserial`` ni de ningún driver. ``src/transporte/spp.py`` es el único módulo
del proyecto que importa ``serial``.

**La definición no hace E/S.** ``enviar`` es la frontera: su implementación sí
escribe en un puerto, el ``Protocol`` solo fija la firma y el contrato de
fallo. Ninguna excepción debe cruzar esa frontera — una desconexión se
reporta con ``False`` y ``ultimo_error``, nunca propagándose (FR-034).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.vision.modelos import ComandoMovimiento

__all__ = ["Transporte"]


@runtime_checkable
class Transporte(Protocol):
    """Medio físico de envío de comandos al robot."""

    def enviar(self, comando: ComandoMovimiento) -> bool:
        """Envía un comando. Devuelve ``True`` si se aceptó.

        No debe lanzar por desconexión ni por un puerto ausente: el fallo se
        registra en ``ultimo_error`` y se devuelve ``False``.
        """
        ...

    def cerrar(self) -> None:
        """Libera el recurso. Idempotente: llamarlo dos veces no es error."""
        ...

    def conectado(self) -> bool:
        """Estado de conexión, consultable sin excepción (data-model §8).

        Es un **método**, no una propiedad: así lo fija el contrato en
        data-model §8 (``() -> bool``), de modo que la forma de la llamada queda
        fijada antes de escribir las implementaciones. Todos los llamadores
        usan ``t.conectado()``.
        """
        ...

    def ultimo_error(self) -> str | None:
        """Último fallo registrado, o ``None`` si no hubo ninguno."""
        ...
