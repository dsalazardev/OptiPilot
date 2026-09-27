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
    ClaseSenal,
    EventoSenal,
    MarcadorVisibilidadPlena,
    Parada,
    SenalConfirmada,
    TipoEvento,
    TransicionEstado,
)

__all__ = ["MetricasCorrida"]

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
