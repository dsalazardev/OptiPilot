"""Canal real hacia el mBot: Bluetooth Classic (SPP) sobre sockets RFCOMM.

**Protocolo confirmado por el profesor (2026-09-28)**: cada comando viaja como
**un único carácter ASCII** por un socket RFCOMM. No hay trama, ni cabecera, ni
checksum, ni longitud fija.

- ``AVANZAR`` → ``b"w"`` (0x77), seguir recto
- ``IZQUIERDA`` → ``b"a"`` (0x61), la línea está a la izquierda
- ``DERECHA`` → ``b"d"`` (0x64), la línea está a la derecha
- ``DETENER`` → ``b"x"`` (0x78), parada

**Supuesto declarado**: se envía exactamente un byte, sin salto de línea ni
delimitador, porque así funciona un receptor que lee ``recv(1)`` por comando. El
código de ejemplo ``Robot.py`` del profesor **no está en este repositorio**, así
que no se pudo verificar contra él. Si su receptor esperase un terminador de
línea, el cambio es una línea aquí (``SUFIJO``) y nada más.

**Por qué sockets y no un puerto COM.** El enlace es RFCOMM puro: el módulo
Bluetooth del mBot publica un servicio de puerto serie y la PC se conecta a él
como socket. ``pyserial`` queda sin uso y se retiró de las dependencias.

**Por qué la fábrica de sockets es inyectable.** La suite debe correr sin
hardware y sin un proveedor de Bluetooth en el SO (``AF_BLUETOOTH`` no existe en
toda plataforma). Inyectando la fábrica, los tests ejercitan la ruta completa de
envío y de fallo contra un doble, sin tocar la red.
"""

from __future__ import annotations

import socket
from collections.abc import Callable

from src.vision.modelos import ComandoMovimiento

__all__ = ["MAPA_COMANDOS", "SUFIJO", "TransporteSPP", "serializar"]

#: Carácter ASCII que espera el mBot para cada comando (contrato §1).
MAPA_COMANDOS: dict[ComandoMovimiento, bytes] = {
    ComandoMovimiento.AVANZAR: b"w",
    ComandoMovimiento.IZQUIERDA: b"a",
    ComandoMovimiento.DERECHA: b"d",
    ComandoMovimiento.DETENER: b"x",
}

#: Delimitador añadido al comando. Vacío: el receptor lee un byte por comando.
SUFIJO = b""

#: Canal RFCOMM estándar del perfil Serial Port Profile.
CANAL_RFCOMM = 1

#: Fábrica de sockets: se inyecta en los tests para no necesitar hardware.
#: Recibe ``(familia, tipo, protocolo)``, la misma firma que ``socket.socket``.
FabricaSocket = Callable[[int, int, int], socket.socket]


def serializar(comando: ComandoMovimiento) -> bytes:
    """Convierte un comando en el byte que espera el mBot.

    Es una función pura y total: si algún día apareciera un valor de
    ``ComandoMovimiento`` sin mapeo, se lanza aquí, en el borde del sistema, y no
    dentro del bucle de visión.
    """
    try:
        return MAPA_COMANDOS[comando]
    except KeyError as exc:  # pragma: no cover - imposible con el enum cerrado
        raise ValueError(f"comando sin carácter ASCII definido: {comando!r}") from exc


class TransporteSPP:
    """Envía comandos al mBot por Bluetooth Classic SPP (RFCOMM).

    Cumple el ``Protocol`` ``Transporte``: **nunca** lanza por desconexión ni por
    una MAC inalcanzable. Todo fallo se registra en ``ultimo_error`` y se
    devuelve ``False``, para que una desconexión del robot no pueda tumbar el
    bucle de visión (FR-034).
    """

    def __init__(
        self,
        mac: str,
        timeout_s: float = 0.20,
        fabrica: FabricaSocket | None = None,
    ) -> None:
        self._mac = mac
        self._timeout_s = timeout_s
        # Se resuelve perezosamente en `_conectar`: atar la fábrica en el
        # constructor acoplaba el objeto al módulo `socket` desde el arranque, y
        # en una plataforma sin `AF_BLUETOOTH` eso ya fallaba demasiado pronto.
        self._fabrica = fabrica
        self._socket: socket.socket | None = None
        self._error: str | None = None

    # ------------------------------------------------------------------
    # Interfaz Transporte
    # ------------------------------------------------------------------

    def enviar(self, comando: ComandoMovimiento) -> bool:
        """Envía un comando. ``True`` si el mBot lo recibió.

        Reconecta best-effort: si no hay conexión, intenta abrirla una vez. Un
        fallo de envío **no** propaga la excepción.
        """
        try:
            if self._socket is None and not self._conectar():
                return False
            assert self._socket is not None
            self._socket.sendall(serializar(comando) + SUFIJO)
            self._error = None
            return True
        except (OSError, ValueError) as exc:
            # Un error de codificación (comando sin mapeo) no es un problema de
            # la conexión, pero se registra igual para que sea diagnosticable.
            self._cerrar_socket()
            self._error = f"{type(exc).__name__}: {exc}"
            return False

    def cerrar(self) -> None:
        """Libera el socket. Idempotente: llamarlo dos veces no es error."""
        self._cerrar_socket()

    def conectado(self) -> bool:
        """Estado de conexión, consultable sin excepción."""
        return self._socket is not None

    def ultimo_error(self) -> str | None:
        """Último fallo registrado, o ``None`` si no hubo ninguno."""
        return self._error

    # ------------------------------------------------------------------
    # Interno
    # ------------------------------------------------------------------

    def _conectar(self) -> bool:
        """Abre el socket RFCOMM. Devuelve ``False`` si no se pudo."""
        try:
            # `AF_BLUETOOTH` no existe en todas las plataformas: se consulta
            # con getattr para degradar a "no conectado" en vez de reventar con
            # AttributeError al importar el módulo.
            familia = getattr(socket, "AF_BLUETOOTH", None)
            protocolo = getattr(socket, "BTPROTO_RFCOMM", None)
            if familia is None or protocolo is None:
                self._error = (
                    "AF_BLUETOOTH no está disponible en esta plataforma; "
                    "se necesita un proveedor de Bluetooth del sistema"
                )
                return False
            sock = (self._fabrica or socket.socket)(familia, socket.SOCK_STREAM, protocolo)
            sock.settimeout(self._timeout_s)
            sock.connect((self._mac, CANAL_RFCOMM))
        except OSError as exc:
            self._error = f"{type(exc).__name__}: {exc}"
            return False
        self._socket = sock
        self._error = None
        return True

    def _cerrar_socket(self) -> None:
        """Cierra el socket sin propagar nada."""
        sock, self._socket = self._socket, None
        if sock is None:
            return
        try:
            sock.close()
        except OSError:
            pass
