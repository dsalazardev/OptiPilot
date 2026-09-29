"""Transporte simulado en memoria, para pruebas sin hardware (T028, FR-033).

Cumple el ``Protocol Transporte`` y no abre ningún recurso externo: registra los
comandos recibidos y permite inyectar fallos. Es el doble que usan las pruebas de
control y de protocolo, de modo que toda la lógica de decisión y de desacople se
puede verificar en headless, sin robot (Principio V).

Por qué existe en ``src/`` y no en ``tests/``: el contrato lo lista como una
implementación de producción del ``Protocol`` (``transporte-bluetooth.md`` §6,
T16–T19). Además, el CLI lo usa como transporte por defecto cuando no hay robot,
así que no es código de prueba.
"""

from __future__ import annotations

from src.vision.modelos import ComandoMovimiento

__all__ = ["TransporteSimulado"]


class TransporteSimulado:
    """Transporte sin hardware que registra el historial de comandos.

    Invariantes del contrato (``transporte-bluetooth.md`` §6):

    - **T16**: misma interfaz que ``TransporteSPP``.
    - **T17**: cada comando aceptado queda en ``historial()``.
    - **T18**: ``fallar_con(n)`` hace que los siguientes ``n`` envíos devuelvan
      ``False`` sin registrar el comando, para probar la persistencia en cola y
      la reconexión.
    - **T19**: es el transporte por defecto de las pruebas.
    """

    def __init__(self) -> None:
        self._historial: list[ComandoMovimiento] = []
        self._fallos_restantes = 0
        self._error: str | None = None
        self._cerrado = False

    def enviar(self, comando: ComandoMovimiento) -> bool:
        """Registra el comando o simula un fallo. Nunca lanza."""
        if self._cerrado:
            self._error = "transporte simulado cerrado"
            return False
        if self._fallos_restantes > 0:
            self._fallos_restantes -= 1
            self._error = "fallo simulado de enlace"
            return False
        self._historial.append(comando)
        self._error = None
        return True

    def cerrar(self) -> None:
        """Cierra el doble. Idempotente: llamarlo dos veces no es error."""
        self._cerrado = True

    def conectado(self) -> bool:
        """Un transporte cerrado no está conectado; sin cerrar, siempre lo está."""
        return not self._cerrado

    def ultimo_error(self) -> str | None:
        """Último fallo registrado, o ``None`` si el último envío fue aceptado."""
        return self._error

    def historial(self) -> list[ComandoMovimiento]:
        """Copia de los comandos aceptados, en orden de envío (T17).

        Se devuelve una copia para que quien consulte el historial no pueda
        alterar el estado interno del doble.
        """
        return list(self._historial)

    def fallar_con(self, n: int) -> None:
        """Hace que los siguientes ``n`` envíos fallen (T18).

        Permite reproducir una desconexión y su reconexión sin mover un cable.
        """
        if n < 0:
            raise ValueError("el número de fallos simulados no puede ser negativo")
        self._fallos_restantes = n

    def reiniciar(self) -> None:
        """Devuelve el doble a su estado inicial (historial vacío, sin fallos).

        Útil entre corridas del CLI para que el historial no se mezcle.
        """
        self._historial.clear()
        self._fallos_restantes = 0
        self._error = None
        self._cerrado = False
