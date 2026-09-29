"""Tests del transporte hacia el mBot (US4).

El protocolo son **letras ASCII sueltas** por un socket RFCOMM, no tramas: el
profesor lo confirmó el 2026-09-28 y estos tests fijan el contrato byte a byte
para que nadie reintroduzca la trama de 4 bytes con checksum que tenía el spec
anterior.

Ninguna prueba toca la red ni requiere hardware: el socket se inyecta con un
doble, de modo que la suite sigue siendo headless aunque la máquina no tenga
proveedor de Bluetooth.
"""

from __future__ import annotations

import ast
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.transporte.base import Transporte
from src.transporte.spp import CANAL_RFCOMM, MAPA_COMANDOS, TransporteSPP, serializar
from src.vision.modelos import ComandoMovimiento

MAC = "00:1B:10:21:2C:1B"


class SocketFalso:
    """Doble de ``socket.socket`` que registra lo que se le envía."""

    def __init__(self, fallo_al_conectar: bool = False, fallo_al_enviar: bool = False) -> None:
        self.fallo_al_conectar = fallo_al_conectar
        self.fallo_al_enviar = fallo_al_enviar
        self.enviados: list[bytes] = []
        self.direccion: tuple[str, int] | None = None
        self.timeout: float | None = None
        self.cercado = 0
        self.settimeout_calls = 0

    def settimeout(self, valor: float) -> None:
        self.timeout = valor
        self.settimeout_calls += 1

    def connect(self, direccion: tuple[str, int]) -> None:
        if self.fallo_al_conectar:
            raise OSError(10061, "connection refused")
        self.direccion = direccion

    def sendall(self, datos: bytes) -> None:
        if self.fallo_al_enviar:
            raise OSError(107, "transport endpoint is not connected")
        self.enviados.append(datos)

    def close(self) -> None:
        self.cercado += 1


def _transporte(
    socket_falso: SocketFalso, timeout_s: float = 0.20, mac: str = MAC
) -> TransporteSPP:
    return TransporteSPP(
        mac=mac,
        timeout_s=timeout_s,
        fabrica=lambda *args: socket_falso,  # type: ignore[arg-type,return-value]
    )


# ---------------------------------------------------------------------------
# El protocolo: un byte ASCII por comando
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "comando,byte_esperado",
    [
        (ComandoMovimiento.AVANZAR, b"w"),
        (ComandoMovimiento.IZQUIERDA, b"a"),
        (ComandoMovimiento.DERECHA, b"d"),
        (ComandoMovimiento.DETENER, b"x"),
    ],
)
def test_cada_comando_viaja_como_un_unico_caracter_ascii(comando: ComandoMovimiento, byte_esperado: bytes) -> None:
    """El mapeo del profesor, byte a byte. Sin trama, sin delimitador."""
    assert serializar(comando) == byte_esperado
    assert len(serializar(comando)) == 1


def test_los_cuatro_comandos_estan_cubiertos_y_son_distintos() -> None:
    assert set(MAPA_COMANDOS) == set(ComandoMovimiento)
    assert len(set(MAPA_COMANDOS.values())) == 4


def test_el_protocolo_envia_exactamente_un_byte_por_comando() -> None:
    falso = SocketFalso()
    transporte = _transporte(falso)
    for comando in ComandoMovimiento:
        assert transporte.enviar(comando) is True
    assert falso.enviados == [b"w", b"a", b"d", b"x"]
    assert all(len(dato) == 1 for dato in falso.enviados)


def test_detener_usa_x_y_no_w() -> None:
    """Regresión: ``DETENER`` es una orden de parada, no un avance."""
    assert serializar(ComandoMovimiento.DETENER) == b"x"
    assert serializar(ComandoMovimiento.DETENER) != serializar(ComandoMovimiento.AVANZAR)


# ---------------------------------------------------------------------------
# Conexión RFCOMM
# ---------------------------------------------------------------------------


def test_conecta_a_la_mac_configurada_por_el_canal_rfcomm_estandar() -> None:
    falso = SocketFalso()
    transporte = _transporte(falso)
    transporte.enviar(ComandoMovimiento.AVANZAR)
    assert falso.direccion == (MAC, CANAL_RFCOMM)
    assert CANAL_RFCOMM == 1  # puerto estándar del perfil SPP


def test_la_mac_es_configurable() -> None:
    """Dos MAC distintas deben producir dos destinos distintos."""
    destinos = []
    for mac in (MAC, "AA:BB:CC:DD:EE:FF"):
        falso = SocketFalso()
        _transporte(falso, mac=mac).enviar(ComandoMovimiento.AVANZAR)
        destinos.append(falso.direccion)
    assert destinos == [(MAC, CANAL_RFCOMM), ("AA:BB:CC:DD:EE:FF", CANAL_RFCOMM)]
    assert destinos[0][0] != destinos[1][0]


def test_el_constructor_no_abre_el_socket() -> None:
    """La conexión es perezosa: construir el transporte no debe tocar la radio.

    Si se abriera en ``__init__``, el CLI no podría arrancar sin robot, que es
    justo lo que lo hace utilizable como herramienta de validación headless.
    """
    creada: list[str] = []

    def fabrica_fallida(*args: object) -> SocketFalso:
        creada.append("creada")
        return SocketFalso()

    transporte = TransporteSPP(mac=MAC, fabrica=fabrica_fallida)  # type: ignore[arg-type]
    assert creada == []  # construir no abrió nada
    assert transporte.conectado() is False
    assert creada == []  # ni siquiera preguntar por el estado
    transporte.enviar(ComandoMovimiento.AVANZAR)  # ahora sí
    assert creada == ["creada"]


def test_usa_la_familia_y_el_protocolo_de_bluetooth_classic() -> None:
    """``AF_BLUETOOTH`` + ``SOCK_STREAM`` + ``BTPROTO_RFCOMM``, como pide el profesor."""
    capturado: list[tuple] = []

    def fabrica(*args: object) -> SocketFalso:
        capturado.append(args)
        return SocketFalso()

    TransporteSPP(mac=MAC, fabrica=fabrica).enviar(ComandoMovimiento.AVANZAR)  # type: ignore[arg-type]
    familia, tipo, protocolo = capturado[0]
    assert familia == socket.AF_BLUETOOTH
    assert tipo == socket.SOCK_STREAM
    assert protocolo == socket.BTPROTO_RFCOMM


def test_acota_el_timeout_del_socket() -> None:
    """Un ``sendall`` bloqueado no puede congelar el proceso (FR-031)."""
    falso = SocketFalso()
    _transporte(falso, timeout_s=0.2).enviar(ComandoMovimiento.AVANZAR)
    assert falso.timeout == 0.2
    assert falso.settimeout_calls == 1


def test_reutiliza_la_conexion_para_no_reabrir_en_cada_comando() -> None:
    """Conectar por fotograma agotaría el enlace; se abre una vez y se reutiliza."""
    falso = SocketFalso()
    transporte = _transporte(falso)
    for _ in range(10):
        transporte.enviar(ComandoMovimiento.AVANZAR)
    assert falso.settimeout_calls == 1
    assert len(falso.enviados) == 10


# ---------------------------------------------------------------------------
# Fallo seguro: nunca lanzar (FR-034)
# ---------------------------------------------------------------------------


def test_una_mac_inalcanzable_no_lanza_y_devuelve_false() -> None:
    transporte = _transporte(SocketFalso(fallo_al_conectar=True))
    assert transporte.enviar(ComandoMovimiento.AVANZAR) is False
    assert transporte.ultimo_error() is not None
    assert "refused" in transporte.ultimo_error()  # type: ignore[operator]


def test_un_fallo_de_envio_no_lanza_y_registra_el_error() -> None:
    transporte = _transporte(SocketFalso(fallo_al_enviar=True))
    assert transporte.enviar(ComandoMovimiento.AVANZAR) is False
    assert transporte.ultimo_error() is not None
    assert transporte.conectado() is False


def test_un_envio_exitoso_limpia_el_error_anterior() -> None:
    """Tras reconectar, el error viejo no debe quedarse dando diagnósticos falsos."""
    falso = SocketFalso(fallo_al_conectar=True)
    transporte = _transporte(falso)
    assert transporte.enviar(ComandoMovimiento.AVANZAR) is False
    falso.fallo_al_conectar = False
    assert transporte.enviar(ComandoMovimiento.AVANZAR) is True
    assert transporte.ultimo_error() is None


def test_ningun_modulo_del_proyecto_importa_serial() -> None:
    """El enlace es RFCOMM puro: nadie importa ``serial`` ni ``pyserial``.

    Se comprueba sobre el **árbol sintáctico** de todo ``src/``, no con un grep:
    un ``grep`` daría falso positivo con cualquier docstring que mencione
    ``pyserial`` para explicar que ya no se usa (que es justo lo que hace
    ``spp.py``). ``ast`` sólo ve lo que realmente se importa.
    """
    raiz = Path(__file__).resolve().parents[2] / "src"
    importados: set[str] = set()
    for ruta in sorted(raiz.rglob("*.py")):
        for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Import):
                importados.update(alias.name.split(".")[0] for alias in nodo.names)
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                importados.add(nodo.module.split(".")[0])
    assert "serial" not in importados, f"importación prohibida: {importados}"
    # Lo que sí se usa para el enlace, de la biblioteca estándar.
    assert "socket" in importados


def test_sin_proveedor_de_bluetooth_degrada_en_lugar_de_reventar() -> None:
    """``AF_BLUETOOTH`` puede no existir; eso es "no conectado", no una excepción."""
    import src.transporte.spp as modulo

    original = modulo.socket
    try:
        # Un `socket` sin `AF_BLUETOOTH`, como en un SO sin el proveedor.
        modulo.socket = SimpleNamespace(SOCK_STREAM=socket.SOCK_STREAM)  # type: ignore[assignment]
        transporte = TransporteSPP(mac=MAC)
        assert transporte.enviar(ComandoMovimiento.AVANZAR) is False
        assert "AF_BLUETOOTH" in transporte.ultimo_error()  # type: ignore[operator]
        assert transporte.conectado() is False
    finally:
        modulo.socket = original  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Interfaz
# ---------------------------------------------------------------------------


def test_cerrar_es_idempotente() -> None:
    falso = SocketFalso()
    transporte = _transporte(falso)
    transporte.enviar(ComandoMovimiento.AVANZAR)
    transporte.cerrar()
    transporte.cerrar()
    transporte.cerrar()
    assert falso.cercado == 1


def test_consultar_el_estado_nunca_lanza() -> None:
    """``conectado`` y ``ultimo_error`` son seguros incluso sin haber enviado nada."""
    transporte = TransporteSPP(mac=MAC, fabrica=lambda *a: SocketFalso())  # type: ignore[arg-type]
    assert transporte.conectado() is False
    assert transporte.ultimo_error() is None
    assert transporte.conectado() is False


def test_cumple_el_protocolo_transporte() -> None:
    """El doble de pruebas satisface ``Transporte``: la abstracción no es decorativa."""
    transporte = _transporte(SocketFalso())
    assert isinstance(transporte, Transporte)
    assert TransporteSPP(mac=MAC, fabrica=lambda *a: SocketFalso()).__class__ is TransporteSPP  # type: ignore[arg-type]
