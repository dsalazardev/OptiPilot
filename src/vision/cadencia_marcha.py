"""Cadencia de envío de ``w`` según el modo de marcha (specs/004).

La lógica es pura y recibe ``t_s`` desde el bucle: en vivo es reloj de pared y
en video es ``indice / fps``. No abre hilos ni escribe en la cola; solo decide
si el comando de este fotograma debe transmitirse.
"""

from __future__ import annotations

from src.vision.configuracion import ParametrosConfiguracion
from src.vision.modelos import ComandoMovimiento, ModoMarcha

__all__ = ["CadenciaMarcha"]


class CadenciaMarcha:
    """Decide cuándo un ``AVANZAR`` puede salir hacia el robot."""

    def __init__(self, params: ParametrosConfiguracion) -> None:
        self._params = params
        self._ultimo_avance_t: float | None = None
        self._ultima_orden: ComandoMovimiento | None = None

    def intervalo_para(self, modo: ModoMarcha) -> float:
        """Segundos mínimos entre dos ``w`` consecutivos para ``modo``."""
        if modo is ModoMarcha.ZONA_ESCOLAR:
            return self._params.intervalo_zona_escolar_s
        if modo is ModoMarcha.VELOCIDAD_60:
            return self._params.intervalo_velocidad_60_s
        return self._params.intervalo_siga_s

    def debe_enviar(
        self,
        comando: ComandoMovimiento,
        modo: ModoMarcha,
        t_s: float,
    ) -> bool:
        """True si ``comando`` debe transmitirse en ``t_s``."""
        if comando is ComandoMovimiento.DETENER:
            self._ultimo_avance_t = None
            self._ultima_orden = comando
            return True

        if comando in (ComandoMovimiento.IZQUIERDA, ComandoMovimiento.DERECHA):
            self._ultima_orden = comando
            return True

        if comando is not ComandoMovimiento.AVANZAR:
            return False

        intervalo = self.intervalo_para(modo)
        if (
            self._ultima_orden is not ComandoMovimiento.AVANZAR
            or self._ultimo_avance_t is None
            or t_s - self._ultimo_avance_t >= intervalo
        ):
            self._ultima_orden = comando
            self._ultimo_avance_t = t_s
            return True
        return False

    def reiniciar(self) -> None:
        """Olvida el historial entre corridas."""
        self._ultimo_avance_t = None
        self._ultima_orden = None
