"""Tests de la cola de desacople y del transporte simulado (T027, T031).

Qué se prueba y por qué
-----------------------
``ColaTransporte`` existe para que el bucle de visión **nunca** espere a la
radio. La propiedad que lo garantiza no es "el código se ve bien", sino que el
bucle solo llame a ``encolar`` (O(1), sin E/S) y jamás a ``drenar`` (que sí hace
la escritura bloqueante). Este archivo fija esa frontera de tres formas:

1. comportamiento de la cola (dedup, FIFO, reintento, ``ultimo_error``);
2. comportamiento del ``TransporteSimulado`` (historial, inyección de fallos);
3. una comprobación **estática** (AST) de que ningún módulo de ``src/vision/``
   referencia la cola ni ``drenar`` — la pureza del paquete de visión.

Ninguna prueba toca hardware: el transporte es el doble en memoria.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from src.transporte.base import Transporte
from src.transporte.cola import ColaTransporte
from src.transporte.simulado import TransporteSimulado
from src.vision.modelos import ComandoMovimiento

AVANZAR = ComandoMovimiento.AVANZAR
IZQUIERDA = ComandoMovimiento.IZQUIERDA
DERECHA = ComandoMovimiento.DERECHA
DETENER = ComandoMovimiento.DETENER


class TransporteQueRevienta:
    """Doble hostil: lanza en ``enviar`` para probar que la cola no propaga.

    Un ``transportes.enviar`` real puede fallar de formas que el contrato no
    enumera; la cola debe absorberlas todas (FR-034, Q22).
    """

    def __init__(self) -> None:
        self.llamadas = 0

    def enviar(self, comando: ComandoMovimiento) -> bool:
        self.llamadas += 1
        raise RuntimeError("el enlace explotó")

    def cerrar(self) -> None: ...

    def conectado(self) -> bool:
        return True

    def ultimo_error(self) -> str | None:
        return None


class TransporteIntermitente:
    """Acepta todo salvo la llamada ``falla_en`` (1-indexada).

    ``TransporteSimulado.fallar_con`` falla desde el siguiente envío, así que no
    sirve para reproducir "algunos ya salieron y luego se cayó el enlace". Este
    doble sí, y es el escenario que prueba que un fallo tardío no pierde lo ya
    transmitido.
    """

    def __init__(self, falla_en: int) -> None:
        self.falla_en = falla_en
        self.llamadas = 0
        self._historial: list[ComandoMovimiento] = []

    def enviar(self, comando: ComandoMovimiento) -> bool:
        self.llamadas += 1
        if self.llamadas == self.falla_en:
            return False
        self._historial.append(comando)
        return True

    def cerrar(self) -> None: ...

    def conectado(self) -> bool:
        return True

    def ultimo_error(self) -> str | None:
        return None

    def historial(self) -> list[ComandoMovimiento]:
        return list(self._historial)


# ---------------------------------------------------------------------------
# TransporteSimulado (T028)
# ---------------------------------------------------------------------------


def test_el_simulado_cumple_el_protocolo() -> None:
    assert isinstance(TransporteSimulado(), Transporte)


def test_el_simulado_registra_el_historial_en_orden() -> None:
    transporte = TransporteSimulado()
    for comando in (AVANZAR, IZQUIERDA, DETENER):
        assert transporte.enviar(comando) is True
    assert transporte.historial() == [AVANZAR, IZQUIERDA, DETENER]


def test_el_historial_es_una_copia_y_no_expone_el_estado() -> None:
    transporte = TransporteSimulado()
    transporte.enviar(AVANZAR)
    copia = transporte.historial()
    copia.append(DETENER)
    assert transporte.historial() == [AVANZAR]


def test_fallar_con_inyecta_exactamente_n_fallos() -> None:
    transporte = TransporteSimulado()
    transporte.fallar_con(2)
    assert transporte.enviar(AVANZAR) is False
    assert transporte.enviar(AVANZAR) is False
    assert transporte.enviar(AVANZAR) is True
    assert transporte.historial() == [AVANZAR]
    assert transporte.ultimo_error() is None  # el éxito limpia el error


def test_fallar_con_rechaza_negativos() -> None:
    with pytest.raises(ValueError):
        TransporteSimulado().fallar_con(-1)


def test_cerrar_es_idempotente_y_bloquea_envios() -> None:
    transporte = TransporteSimulado()
    transporte.enviar(AVANZAR)
    transporte.cerrar()
    transporte.cerrar()
    assert transporte.conectado() is False
    assert transporte.enviar(DETENER) is False
    assert transporte.historial() == [AVANZAR]


def test_reiniciar_devuelve_el_doble_a_su_estado_inicial() -> None:
    transporte = TransporteSimulado()
    transporte.enviar(AVANZAR)
    transporte.fallar_con(1)
    transporte.cerrar()
    transporte.reiniciar()
    assert transporte.historial() == []
    assert transporte.conectado() is True
    assert transporte.ultimo_error() is None
    assert transporte.enviar(DERECHA) is True


# ---------------------------------------------------------------------------
# ColaTransporte: deduplicación (FR-032)
# ---------------------------------------------------------------------------


def test_el_primer_comando_siempre_se_encola() -> None:
    assert ColaTransporte().encolar(AVANZAR) is True


def test_un_comando_identico_ya_enviado_se_descarta() -> None:
    cola = ColaTransporte()
    transporte = TransporteSimulado()
    cola.encolar(AVANZAR)
    cola.drenar(transporte)
    assert cola.encolar(AVANZAR) is False  # idéntico al último enviado, sin pendientes
    assert cola.pendientes() == 0


def test_un_comando_distinto_no_se_descarta() -> None:
    cola = ColaTransporte()
    transporte = TransporteSimulado()
    cola.encolar(AVANZAR)
    cola.drenar(transporte)
    assert cola.encolar(DERECHA) is True


def test_no_se_deduplica_si_hay_pendientes() -> None:
    """La deduplicación es solo contra lo ya enviado, nunca dentro del backlog.

    Si hubiera pendientes, descartar el comando alteraría el orden de los giros.
    """
    cola = ColaTransporte()
    assert cola.encolar(AVANZAR) is True
    assert cola.encolar(AVANZAR) is True  # hay uno pendiente: no se descarta
    assert cola.pendientes() == 2


# ---------------------------------------------------------------------------
# ColaTransporte: drenaje FIFO y reintentos (T12, T13)
# ---------------------------------------------------------------------------


def test_drenar_transmite_en_orden_fifo() -> None:
    cola = ColaTransporte()
    transporte = TransporteSimulado()
    for comando in (AVANZAR, IZQUIERDA, DETENER):
        cola.encolar(comando)
    assert cola.drenar(transporte) == 3
    assert transporte.historial() == [AVANZAR, IZQUIERDA, DETENER]


def test_drenar_devuelve_cuantos_transmitio_y_vacia_la_cola() -> None:
    cola = ColaTransporte()
    cola.encolar(AVANZAR)
    cola.encolar(DERECHA)
    assert cola.drenar(TransporteSimulado()) == 2
    assert cola.pendientes() == 0
    assert cola.drenar(TransporteSimulado()) == 0


def test_un_fallo_deja_el_comando_pendiente_y_registra_el_error() -> None:
    cola = ColaTransporte()
    transporte = TransporteSimulado()
    transporte.fallar_con(1)
    cola.encolar(AVANZAR)

    assert cola.drenar(transporte) == 0
    assert cola.pendientes() == 1  # el comando sigue ahí
    assert cola.ultimo_error() is not None
    assert transporte.historial() == []


def test_la_reconexion_reanuda_sin_duplicar() -> None:
    """Tras un fallo, el reintento envía el comando una sola vez, en su lugar."""
    cola = ColaTransporte()
    transporte = TransporteSimulado()
    transporte.fallar_con(1)
    cola.encolar(AVANZAR)
    cola.encolar(DERECHA)

    cola.drenar(transporte)  # falla el primero; el segundo ni se intenta
    assert transporte.historial() == []
    assert cola.pendientes() == 2

    assert cola.drenar(transporte) == 2  # ahora sí, en orden y sin duplicar
    assert transporte.historial() == [AVANZAR, DERECHA]
    assert cola.ultimo_error() is None


def test_un_fallo_parcial_no_pierde_los_ya_transmitidos() -> None:
    cola = ColaTransporte()
    for comando in (AVANZAR, IZQUIERDA, DETENER):
        cola.encolar(comando)
    transporte = TransporteIntermitente(falla_en=2)

    # El primer comando se transmite; el segundo falla y corta el drenaje.
    assert cola.drenar(transporte) == 1
    assert transporte.historial() == [AVANZAR]
    assert cola.pendientes() == 2
    assert cola.ultimo_enviado() is AVANZAR

    # La llamada siguiente ya no falla: el reintento completa sin duplicar.
    assert cola.drenar(transporte) == 2
    assert transporte.historial() == [AVANZAR, IZQUIERDA, DETENER]
    assert cola.pendientes() == 0


def test_pendientes_refleja_el_backlog() -> None:
    cola = ColaTransporte()
    assert cola.pendientes() == 0
    cola.encolar(AVANZAR)
    cola.encolar(DERECHA)
    assert cola.pendientes() == 2
    cola.drenar(TransporteSimulado())
    assert cola.pendientes() == 0


def test_ultimo_enviado_empieza_en_none_y_se_actualiza() -> None:
    cola = ColaTransporte()
    assert cola.ultimo_enviado() is None
    cola.encolar(IZQUIERDA)
    cola.drenar(TransporteSimulado())
    assert cola.ultimo_enviado() is IZQUIERDA


def test_vaciar_descarta_lo_pendiente_pero_conserva_la_deduplicacion() -> None:
    cola = ColaTransporte()
    transporte = TransporteSimulado()
    cola.encolar(AVANZAR)
    cola.drenar(transporte)
    cola.encolar(DERECHA)
    cola.vaciar()
    assert cola.pendientes() == 0
    assert cola.encolar(AVANZAR) is False  # el último enviado sigue siendo AVANZAR


# ---------------------------------------------------------------------------
# Robustez: la cola nunca propaga y nunca bloquea por E/S (FR-034, Q22)
# ---------------------------------------------------------------------------


def test_drenar_nunca_lanza_aunque_el_transporte_explote() -> None:
    cola = ColaTransporte()
    cola.encolar(AVANZAR)
    explosivo = TransporteQueRevienta()
    assert cola.drenar(explosivo) == 0
    assert explosivo.llamadas == 1
    assert cola.pendientes() == 1
    assert "RuntimeError" in (cola.ultimo_error() or "")


def test_encolar_no_hace_ninguna_llamada_al_transporte() -> None:
    """``encolar`` es O(1) y puro: no debe hablar con el transporte ni una vez."""
    explosivo = TransporteQueRevienta()
    cola = ColaTransporte()
    for comando in (AVANZAR, IZQUIERDA, DERECHA, DETENER):
        cola.encolar(comando)
    cola.pendientes()
    assert explosivo.llamadas == 0


# ---------------------------------------------------------------------------
# T031: el bucle de visión no drena (SC-005, T14)
# ---------------------------------------------------------------------------


def test_ningun_modulo_de_vision_referencia_la_cola_ni_el_drenaje() -> None:
    """Invariante de arquitectura: ``src/vision/`` es puro y no conoce el transporte.

    La escritura bloqueante ocurre en ``drenar``. Si un módulo de visión lo
    llamara —o importara ``ColaTransporte``— el enlace podría bloquear el bucle
    de detección. Se comprueba sobre el **AST**, no con un grep, para no dar
    falsos positivos con menciones en docstrings.

    La otra mitad del invariante —que ``main.py`` sí encola en el bucle y drena
    fuera de él— se verifica en este mismo archivo tras el cableado (T035).
    """
    raiz = pathlib.Path(__file__).resolve().parents[2] / "src" / "vision"
    infracciones: list[str] = []
    for ruta in sorted(raiz.rglob("*.py")):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ImportFrom) and nodo.module and "transporte" in nodo.module:
                infracciones.append(f"{ruta.name}: importa {nodo.module}")
            elif isinstance(nodo, ast.Import):
                if any("transporte" in alias.name for alias in nodo.names):
                    infracciones.append(f"{ruta.name}: importa transporte")
            elif isinstance(nodo, ast.Attribute) and nodo.attr == "drenar":
                infracciones.append(f"{ruta.name}:{nodo.lineno}: llama a drenar")
    assert not infracciones, f"src/vision/ no puede conocer el transporte: {infracciones}"


def _llamadas_por_funcion(ruta: pathlib.Path) -> dict[str, set[str]]:
    """Nombres de método invocados dentro de cada función de un archivo."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    por_funcion: dict[str, set[str]] = {}
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nombres = {
                sub.func.attr
                for sub in ast.walk(nodo)
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
            }
            por_funcion[nodo.name] = nombres
    return por_funcion


def test_el_bucle_de_vision_encola_y_nunca_drena() -> None:
    """SC-005 / T14: ``main.py`` encola en el bucle y drena solo en el hilo.

    Es la otra mitad del invariante que no se puede comprobar desde
    ``src/vision/``: el punto de composición (``main.py``) debe llamar a
    ``encolar`` en ``_correr`` —el camino por fotograma— y dejar ``drenar``
    encerrado en ``_BombeoTransporte``, que corre aparte.
    """
    ruta = pathlib.Path(__file__).resolve().parents[2] / "src" / "main.py"
    llamadas = _llamadas_por_funcion(ruta)

    assert "encolar" in llamadas["_correr"], "el bucle debe encolar el comando final"
    assert "drenar" not in llamadas["_correr"], "el bucle de visión NUNCA debe drenar"
    assert "drenar" in llamadas.get("_bucle", set()), "el drenaje vive en su propio hilo"
    assert "encolar" not in llamadas.get("_bucle", set())
