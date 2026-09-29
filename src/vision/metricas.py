"""Registro y exportación de métricas y evidencia por corrida (FR-025, SC-012).

Agrega lo que el pipeline y la máquina de estados ya emitieron —fotogramas,
eventos, señales confirmadas, paradas y transiciones— y lo vuelca en los dos
artefactos del contrato ``contracts/esquema-eventos-metricas.md``:
``eventos.jsonl`` (una línea JSON por evento, en orden temporal) y
``metricas.json`` (resumen agregado que nunca omite claves).

Este módulo **no decide** la aceptación de una detección: solo aporta los
conteos. Las tasas de SC-001/002/003 se calculan en el flujo de análisis contra
la anotación de referencia (contrato de eventos/métricas, Regla 3).

Es el único punto del pipeline que escribe en disco, y lo hace de forma
explícita: ``exportar(directorio)`` (Constitución §II, §V).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from .modelos import (
    CausaComando,
    ClaseSenal,
    ComandoMovimiento,
    DecisionCompuesta,
    EventoSenal,
    MarcadorVisibilidadPlena,
    Parada,
    SenalConfirmada,
    TipoEvento,
    TransicionEstado,
)

__all__ = ["MetricasControl", "MetricasCorrida"]

_CLAVES_RESUMEN = (
    "corrida_id",
    "fuente",
    "frames_procesados",
    "ocurrencias_pare",
    "ocurrencias_siga",
    "detecciones_correctas",
    "falsos_positivos",
    "confusiones",
    "latencias_frames",
    "latencias_ms",
    "paradas",
    "fps_promedio",
    "latencia_media_ms",
    "latencia_p95_ms",
)


def _percentil(valores: list[float], percentil: float) -> float:
    """Percentil por interpolación lineal (mismo criterio que ``numpy.percentile``).

    Se implementa aquí para que el módulo no dependa de numpy y el resultado sea
    determinista y verificable en las pruebas.
    """
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    if len(ordenados) == 1:
        return float(ordenados[0])
    posicion = (len(ordenados) - 1) * (percentil / 100.0)
    inferior = math.floor(posicion)
    superior = math.ceil(posicion)
    if inferior == superior:
        return float(ordenados[inferior])
    fraccion = posicion - inferior
    return float(ordenados[inferior] * (1.0 - fraccion) + ordenados[superior] * fraccion)


def _linea_evento(evento: EventoSenal) -> dict:
    """Serializa un evento con las claves del contrato de ``eventos.jsonl``.

    ``ts``, ``frame``, ``tipo``, ``clase``, ``ocurrencia_id`` y ``centro`` están
    siempre; ``origen``, ``destino`` y ``causa`` solo en eventos ``TRANSICION``
    (y ``EventoSenal`` los rechaza en cualquier otro tipo).
    """
    linea: dict = {
        "ts": evento.t_s,
        "frame": evento.fotograma_idx,
        "tipo": str(evento.tipo),
        "clase": str(evento.clase) if evento.clase is not None else None,
        "ocurrencia_id": evento.ocurrencia_id,
        "centro": list(evento.centro_px) if evento.centro_px is not None else None,
    }
    if evento.tipo is TipoEvento.TRANSICION:
        linea["origen"] = str(evento.origen)
        linea["destino"] = str(evento.destino)
        linea["causa"] = str(evento.causa)
    return linea


class MetricasCorrida:
    """Acumula la evidencia de una corrida y la exporta (contrato de métricas)."""

    def __init__(self, corrida_id: str, fuente: str) -> None:
        self._corrida_id = corrida_id
        self._fuente = fuente
        self._latencias_procesamiento: list[float] = []
        self._eventos: list[EventoSenal] = []
        self._senales: list[tuple[ClaseSenal, int]] = []
        self._paradas: list[Parada] = []
        self._latencias_frames: list[int] = []
        self._latencias_ms: list[float] = []
        self._detecciones_correctas = 0
        self._falsos_positivos = 0
        self._confusiones = 0
        self._t_ultimo: float | None = None

    # -- registro -----------------------------------------------------------

    def registrar_fotograma(self, latencia_ms: float, t_s: float | None = None) -> None:
        """Suma la latencia de **procesamiento** del fotograma (SC-007).

        ``t_s`` es opcional para no romper la firma del contrato; cuando se
        informa, permite calcular ``fps_promedio`` a partir del avance del
        vídeo en vez de la latencia del procesador.
        """
        if latencia_ms < 0:
            raise ValueError("latencia_ms debe ser >= 0")
        self._latencias_procesamiento.append(float(latencia_ms))
        if t_s is not None:
            if t_s < 0:
                raise ValueError("t_s debe ser >= 0")
            if self._t_ultimo is None or t_s > self._t_ultimo:
                self._t_ultimo = float(t_s)

    def registrar_evento(self, evento: EventoSenal) -> None:
        """Añade un evento al registro que se vuelcará en ``eventos.jsonl``."""
        self._eventos.append(evento)

    def registrar_transicion(self, transicion: TransicionEstado) -> None:
        """Vuelca una transición de estado como evento ``TRANSICION`` (FR-023)."""
        self._eventos.append(EventoSenal.de_transicion(transicion))

    def registrar_senal(
        self,
        senal: SenalConfirmada,
        anotada: bool | None = None,
        clase_anotada: ClaseSenal | None = None,
    ) -> None:
        """Registra una señal confirmada y, si hay referencia, la confronta (Q3).

        ``ocurrencias_*`` cuenta ocurrencias delimitadas por re-armado, así que
        se deduplica por ``(clase, ocurrencia_id)`` y **no** depende de que
        exista anotación.

        ``anotada`` admite tres estados: ``None`` significa *sin anotación de
        referencia* y entonces solo se cuenta la ocurrencia, sin juzgar acierto
        ni error — es lo que ocurre cuando el CLI corre sin referencia, y evita
        que toda detección correcta se contabilice como falso positivo. Con
        ``True``/``False`` se separa detecciones correctas de falsos positivos;
        si además se informa ``clase_anotada`` y difiere de la clase detectada,
        se cuenta una confusión PARE↔SIGA.
        """
        par = (senal.clase, senal.ocurrencia_id)
        if par not in self._senales:
            self._senales.append(par)
        if anotada is None:
            return
        if clase_anotada is not None and clase_anotada is not senal.clase:
            self._confusiones += 1
        elif anotada:
            self._detecciones_correctas += 1
        else:
            self._falsos_positivos += 1

    def registrar_parada(self, parada: Parada) -> None:
        """Registra una detención completa con su retardo de reanudación (SC-008)."""
        self._paradas.append(parada)

    def registrar_decision_latencia(self, frames: int, ms: float) -> None:
        """Latencia de decisión por ocurrencia: de visibilidad plena a la decisión."""
        if frames < 0:
            raise ValueError("frames debe ser >= 0")
        if ms < 0:
            raise ValueError("ms debe ser >= 0")
        self._latencias_frames.append(int(frames))
        self._latencias_ms.append(float(ms))

    def registrar_latencia_desde_marcador(
        self,
        marcador: MarcadorVisibilidadPlena,
        fotograma_idx: int,
        t_s: float,
    ) -> None:
        """Calcula la latencia de decisión desde el marcador de visibilidad plena.

        Es el cómputo que exige T020: el origen de la latencia es el primer
        fotograma con la señal completamente dentro de la ROI y área ≥ mínima
        (Q2, SC-006), no el primer fotograma en que se ve algo.
        """
        if fotograma_idx < marcador.fotograma_idx:
            raise ValueError("la decisión no puede preceder a la visibilidad plena")
        if t_s < marcador.t_s:
            raise ValueError("la decisión no puede preceder a la visibilidad plena")
        self.registrar_decision_latencia(
            frames=fotograma_idx - marcador.fotograma_idx,
            ms=(t_s - marcador.t_s) * 1000.0,
        )

    # -- salida -------------------------------------------------------------

    def resumen(self) -> dict:
        """Resumen agregado de la corrida con **todas** las claves del contrato.

        Ante ausencia de datos los contadores quedan en 0 y las listas vacías;
        ninguna clave se omite (Regla 2 del contrato de eventos/métricas).
        """
        ocurrencias_pare = sum(1 for clase, _ in self._senales if clase is ClaseSenal.PARE)
        ocurrencias_siga = sum(1 for clase, _ in self._senales if clase is ClaseSenal.SIGA)
        duracion_s = self._t_ultimo or 0.0
        fps_promedio = (len(self._latencias_procesamiento) / duracion_s) if duracion_s > 0 else 0.0
        return {
            "corrida_id": self._corrida_id,
            "fuente": self._fuente,
            "frames_procesados": len(self._latencias_procesamiento),
            "ocurrencias_pare": ocurrencias_pare,
            "ocurrencias_siga": ocurrencias_siga,
            "detecciones_correctas": self._detecciones_correctas,
            "falsos_positivos": self._falsos_positivos,
            "confusiones": self._confusiones,
            "latencias_frames": list(self._latencias_frames),
            "latencias_ms": list(self._latencias_ms),
            "paradas": [
                {
                    "inicio_t": parada.inicio_t,
                    "t_configurado_s": parada.t_configurado_s,
                    "fin_t": parada.fin_t,
                    "retardo_s": parada.retardo_s,
                }
                for parada in self._paradas
            ],
            "fps_promedio": fps_promedio,
            "latencia_media_ms": (
                sum(self._latencias_procesamiento) / len(self._latencias_procesamiento)
                if self._latencias_procesamiento
                else 0.0
            ),
            "latencia_p95_ms": _percentil(self._latencias_procesamiento, 95.0),
        }

    def exportar(self, directorio: Path) -> tuple[Path, Path]:
        """Escribe ``eventos.jsonl`` y ``metricas.json``; devuelve sus rutas."""
        destino = Path(directorio)
        destino.mkdir(parents=True, exist_ok=True)

        ruta_eventos = destino / "eventos.jsonl"
        with ruta_eventos.open("w", encoding="utf-8") as archivo:
            for evento in self._eventos_ordenados():
                archivo.write(json.dumps(_linea_evento(evento), ensure_ascii=False) + "\n")

        ruta_metricas = destino / "metricas.json"
        with ruta_metricas.open("w", encoding="utf-8") as archivo:
            json.dump(self.resumen(), archivo, ensure_ascii=False, indent=2)
            archivo.write("\n")

        return ruta_eventos, ruta_metricas

    def _eventos_ordenados(self) -> list[EventoSenal]:
        """Eventos en orden temporal; a igualdad de tiempo, orden de inserción."""
        return sorted(self._eventos, key=lambda evento: (evento.t_s, evento.fotograma_idx))


# ---------------------------------------------------------------------------
# Control de trayectoria (specs/002 — T032)
# ---------------------------------------------------------------------------

#: Comandos laterales: los que expresan «la línea está de ese lado».
_LATERALES = frozenset({ComandoMovimiento.IZQUIERDA, ComandoMovimiento.DERECHA})


def _es_transicion_lateral(anterior: ComandoMovimiento, actual: ComandoMovimiento) -> bool:
    """True si el comando pasa entre ``AVANZAR`` y un lateral (en cualquier sentido).

    Es la definición de *corrección* que usa SC-001: una corrección empieza
    cuando se abandona el avance recto y termina cuando se vuelve a él.
    """
    return (anterior is ComandoMovimiento.AVANZAR and actual in _LATERALES) or (
        actual is ComandoMovimiento.AVANZAR and anterior in _LATERALES
    )


class MetricasControl:
    """Acumula la evidencia del control de trayectoria por corrida (T032).

    Consume la ``DecisionCompuesta`` de cada fotograma y deriva las métricas que
    la rúbrica necesita para el análisis de resultados (criterio 11):

    - ``correcciones``: transiciones ``AVANZAR ↔`` lateral, proxy de SC-001.
    - ``fotogramas_por_comando``: reparto del tiempo entre los cuatro comandos.
    - ``perdidas_linea``: cuántas veces se dejó de ver la línea (``pos.valida``).
    - ``recuperaciones_ok`` / ``recuperaciones_fallidas``: se retomó la línea
      dentro de la ventana de gracia, o se agotó (FR-020).
    - ``velocidad_error_px``: cambio de ``x_px`` entre fotogramas válidos.
    - ``latencia_decision_ms``: tiempo de estimar + decidir + componer.

    **No modifica ``MetricasCorrida``** (FR-026): son dos responsabilidades
    distintas —detección de señales frente a control— y mezclarlas habría
    cambiado el resumen de 001, del que dependen sus pruebas.
    """

    def __init__(self) -> None:
        self._correcciones = 0
        self._por_comando: dict[ComandoMovimiento, int] = {c: 0 for c in ComandoMovimiento}
        self._perdidas_linea = 0
        self._recuperaciones_ok = 0
        self._recuperaciones_fallidas = 0
        self._velocidades_error_px: list[float] = []
        self._latencias_decision_ms: list[float] = []
        self._comando_anterior: ComandoMovimiento | None = None
        self._valida_anterior: bool | None = None
        self._x_anterior: float | None = None
        self._en_perdida = False

    def registrar(self, decision: DecisionCompuesta, latencia_decision_ms: float = 0.0) -> None:
        """Registra la decisión de un fotograma y actualiza los contadores.

        ``latencia_decision_ms`` es opcional: cuando no se mide, no se añade
        muestra y la lista de latencias queda vacía (igual que en el contrato).
        """
        comando = decision.comando
        self._por_comando[comando] += 1

        if self._comando_anterior is not None and _es_transicion_lateral(
            self._comando_anterior, comando
        ):
            self._correcciones += 1
        self._comando_anterior = comando

        posicion = decision.posicion
        if posicion.valida:
            self._registrar_fotograma_valido(posicion, decision)
        else:
            self._registrar_fotograma_invalido(decision)

        self._valida_anterior = posicion.valida
        if latencia_decision_ms > 0:
            self._latencias_decision_ms.append(float(latencia_decision_ms))

    def _registrar_fotograma_valido(self, posicion, decision: DecisionCompuesta) -> None:
        if self._en_perdida:
            if decision.causa in (CausaComando.RECUPERACION, CausaComando.SEGUIMIENTO):
                self._recuperaciones_ok += 1
            self._en_perdida = False
        if self._x_anterior is not None and posicion.x_px is not None:
            self._velocidades_error_px.append(abs(posicion.x_px - self._x_anterior))
        self._x_anterior = posicion.x_px

    def _registrar_fotograma_invalido(self, decision: DecisionCompuesta) -> None:
        if self._valida_anterior is not False:
            self._perdidas_linea += 1
        self._en_perdida = True
        if decision.causa is CausaComando.GRACIA_AGOTADA:
            self._recuperaciones_fallidas += 1
            self._en_perdida = False
        self._x_anterior = None

    def resumen(self) -> dict:
        """Resumen con todas las claves, aunque no haya datos (Regla 2)."""
        return {
            "correcciones": self._correcciones,
            "fotogramas_por_comando": {str(clave): valor for clave, valor in self._por_comando.items()},
            "perdidas_linea": self._perdidas_linea,
            "recuperaciones_ok": self._recuperaciones_ok,
            "recuperaciones_fallidas": self._recuperaciones_fallidas,
            "velocidad_error_px_media": (
                sum(self._velocidades_error_px) / len(self._velocidades_error_px)
                if self._velocidades_error_px
                else 0.0
            ),
            "velocidad_error_px_p95": _percentil(self._velocidades_error_px, 95.0),
            "velocidad_error_px_max": max(self._velocidades_error_px, default=0.0),
            "velocidades_error_px": list(self._velocidades_error_px),
            "latencia_decision_ms_media": (
                sum(self._latencias_decision_ms) / len(self._latencias_decision_ms)
                if self._latencias_decision_ms
                else 0.0
            ),
            "latencia_decision_ms_p95": _percentil(self._latencias_decision_ms, 95.0),
            "latencias_decision_ms": list(self._latencias_decision_ms),
        }
