"""Contratos de datos compartidos del pipeline de visión (data-model.md).

Define los enums y dataclasses que intercambian las etapas: segmentación,
candidatos, detección confirmada, ocurrencias, eventos, máquina de estados y
métricas. Sin lógica de visión ni E/S: solo estructura y validaciones del
modelo (Constitución §II, §IV).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np

__all__ = [
    "CandidatoSenal",
    "CausaTransicion",
    "ClaseSenal",
    "DecisionMovimiento",
    "EstadoOcurrencia",
    "EstadoRobot",
    "EventoSenal",
    "MarcadorVisibilidadPlena",
    "Ocurrencia",
    "ResultadoProcesamiento",
    "ResultadoSegmentacion",
    "SenalConfirmada",
    "TipoEvento",
    "TransicionEstado",
]


class ClaseSenal(StrEnum):
    """Clases únicas de señal del reto."""

    PARE = "PARE"
    SIGA = "SIGA"


class EstadoRobot(StrEnum):
    """Estados observables de la máquina PARE/SIGA (FR-015)."""

    EN_MARCHA = "EN_MARCHA"
    DETENIDO_MINIMO = "DETENIDO_MINIMO"
    DETENIDO_ESPERANDO_SIGA = "DETENIDO_ESPERANDO_SIGA"


class DecisionMovimiento(StrEnum):
    """Decisión emitida a la capa de control."""

    AUTORIZADO = "AUTORIZADO"
    NO_AUTORIZADO = "NO_AUTORIZADO"


class CausaTransicion(StrEnum):
    """Causa registrada de una transición de estado (FR-023)."""

    INICIO = "INICIO"
    PARE_CONFIRMADO = "PARE_CONFIRMADO"
    T_CUMPLIDO = "T_CUMPLIDO"
    SIGA_CONFIRMADO = "SIGA_CONFIRMADO"
    REANUDACION = "REANUDACION"
    REARME = "REARME"


class TipoEvento(StrEnum):
    """Tipos de evento serializables en ``eventos.jsonl``."""

    PARE_CONFIRMADO = "PARE_CONFIRMADO"
    SIGA_CONFIRMADO = "SIGA_CONFIRMADO"
    SENAL_PERDIDA = "SENAL_PERDIDA"
    PARE_REARMADO = "PARE_REARMADO"
    FALSO_POSITIVO_SUPRIMIDO = "FALSO_POSITIVO_SUPRIMIDO"
    TRANSICION = "TRANSICION"


class EstadoOcurrencia(StrEnum):
    """Ciclo de vida de una ocurrencia (delimitada por re-armado)."""

    ACTIVA = "ACTIVA"
    CERRADA = "CERRADA"


def _exigir(condicion: bool, mensaje: str) -> None:
    if not condicion:
        raise ValueError(mensaje)


@dataclass(eq=False)
class ResultadoSegmentacion:
    """Máscaras binarias (0/1) a tamaño completo del fotograma por color objetivo."""

    mascara_linea: np.ndarray
    mascara_roja: np.ndarray
    mascara_verde: np.ndarray
    roi_linea: tuple[int, int, int, int]
    roi_senales: tuple[int, int, int, int]

    def __post_init__(self) -> None:
        for nombre in ("mascara_linea", "mascara_roja", "mascara_verde"):
            mascara = getattr(self, nombre)
            _exigir(isinstance(mascara, np.ndarray), f"'{nombre}' debe ser np.ndarray")
            _exigir(mascara.ndim == 2, f"'{nombre}' debe ser una máscara 2D")
        _exigir(
            self.mascara_linea.shape == self.mascara_roja.shape == self.mascara_verde.shape,
            "las máscaras deben tener la misma forma",
        )


@dataclass(frozen=True)
class CandidatoSenal:
    """Región validada (o descartada) antes de la confirmación temporal."""

    clase_estimada: ClaseSenal
    centro_px: tuple[int, int]
    area_px: int
    area_rel: float
    n_vertices: int
    caja_px: tuple[int, int, int, int]
    aspecto: float
    es_valido: bool
    motivo_invalidez: str | None = None

    def __post_init__(self) -> None:
        _exigir(self.area_px >= 0, "area_px debe ser >= 0")
        _exigir(self.area_rel >= 0, "area_rel debe ser >= 0")
        _exigir(self.n_vertices >= 3, "n_vertices debe ser >= 3")
        ancho, alto = self.caja_px[2], self.caja_px[3]
        _exigir(ancho > 0 and alto > 0, "la caja debe tener ancho y alto > 0")
        _exigir(self.aspecto > 0, "aspecto debe ser > 0")
        if self.es_valido:
            _exigir(
                self.motivo_invalidez is None,
                "un candidato válido no lleva motivo_invalidez",
            )
        else:
            _exigir(
                bool(self.motivo_invalidez),
                "un candidato inválido debe indicar motivo_invalidez",
            )


@dataclass(frozen=True)
class SenalConfirmada:
    """Octágono confirmado (flanco de subida) asociado a una ocurrencia."""

    clase: ClaseSenal
    centro_px: tuple[int, int]
    area_rel: float
    fotograma_idx: int
    t_s: float
    ocurrencia_id: int

    def __post_init__(self) -> None:
        _exigir(self.fotograma_idx >= 0, "fotograma_idx debe ser >= 0")
        _exigir(self.t_s >= 0, "t_s debe ser >= 0")
        _exigir(self.ocurrencia_id >= 0, "ocurrencia_id debe ser >= 0")
        _exigir(self.area_rel >= 0, "area_rel debe ser >= 0")


@dataclass
class Ocurrencia:
    """Aparición de una señal delimitada por el re-armado (FR-021, FR-025)."""

    id: int
    clase: ClaseSenal
    fotograma_inicio: int
    t_inicio: float
    fotograma_fin: int | None = None
    t_fin: float | None = None
    estado: EstadoOcurrencia = EstadoOcurrencia.ACTIVA
    anotada: bool = False
    detecciones: int = 0

    def __post_init__(self) -> None:
        _exigir(self.id >= 0, "id debe ser >= 0")
        _exigir(self.fotograma_inicio >= 0, "fotograma_inicio debe ser >= 0")
        _exigir(self.t_inicio >= 0, "t_inicio debe ser >= 0")
        _exigir(self.detecciones >= 0, "detecciones debe ser >= 0")
        if self.estado == EstadoOcurrencia.CERRADA:
            _exigir(
                self.fotograma_fin is not None and self.t_fin is not None,
                "una ocurrencia cerrada debe registrar su fin",
            )

    def cerrar(self, fotograma_idx: int, t_s: float) -> None:
        """Marca la ocurrencia como cerrada en el fotograma indicado."""
        _exigir(fotograma_idx >= self.fotograma_inicio, "el fin no puede ser anterior al inicio")
        _exigir(t_s >= self.t_inicio, "el tiempo de fin no puede ser anterior al inicio")
        self.fotograma_fin = fotograma_idx
        self.t_fin = t_s
        self.estado = EstadoOcurrencia.CERRADA


@dataclass(frozen=True)
class TransicionEstado:
    """Cambio de estado registrado (origen, destino, causa y momento — FR-023)."""

    desde: EstadoRobot
    hacia: EstadoRobot
    causa: CausaTransicion
    fotograma_idx: int
    t_s: float

    def __post_init__(self) -> None:
        _exigir(self.desde != self.hacia, "una transición debe cambiar de estado")
        _exigir(self.fotograma_idx >= 0, "fotograma_idx debe ser >= 0")
        _exigir(self.t_s >= 0, "t_s debe ser >= 0")


@dataclass(frozen=True)
class EventoSenal:
    """Evento serializable en ``eventos.jsonl`` (contrato de eventos/métricas)."""

    tipo: TipoEvento
    fotograma_idx: int
    t_s: float
    clase: ClaseSenal | None = None
    centro_px: tuple[int, int] | None = None
    ocurrencia_id: int | None = None
    origen: EstadoRobot | None = None
    destino: EstadoRobot | None = None
    causa: CausaTransicion | None = None

    def __post_init__(self) -> None:
        _exigir(self.fotograma_idx >= 0, "fotograma_idx debe ser >= 0")
        _exigir(self.t_s >= 0, "t_s debe ser >= 0")
        if self.tipo == TipoEvento.TRANSICION:
            _exigir(
                self.origen is not None and self.destino is not None and self.causa is not None,
                "un evento TRANSICION requiere origen, destino y causa",
            )
        else:
            _exigir(
                self.origen is None and self.destino is None and self.causa is None,
                "origen, destino y causa solo aplican a eventos TRANSICION",
            )

    @classmethod
    def de_transicion(cls, transicion: TransicionEstado) -> "EventoSenal":
        """Convierte una transición en su evento serializable ``TRANSICION``."""
        return cls(
            tipo=TipoEvento.TRANSICION,
            fotograma_idx=transicion.fotograma_idx,
            t_s=transicion.t_s,
            origen=transicion.desde,
            destino=transicion.hacia,
            causa=transicion.causa,
        )


@dataclass(frozen=True)
class MarcadorVisibilidadPlena:
    """Primer fotograma con la señal completamente dentro de la ROI y área ≥ mínima (SC-006)."""

    clase: ClaseSenal
    fotograma_idx: int
    t_s: float

    def __post_init__(self) -> None:
        _exigir(self.fotograma_idx >= 0, "fotograma_idx debe ser >= 0")
        _exigir(self.t_s >= 0, "t_s debe ser >= 0")


@dataclass
class ResultadoProcesamiento:
    """Salida del pipeline para un fotograma (data-model §12)."""

    segmentacion: ResultadoSegmentacion
    candidatos: list[CandidatoSenal]
    senales_confirmadas: list[SenalConfirmada]
    eventos: list[EventoSenal]
    latencia_ms: float
    visibilidad_plena: list[MarcadorVisibilidadPlena] = field(default_factory=list)

    def __post_init__(self) -> None:
        _exigir(self.latencia_ms >= 0, "latencia_ms debe ser >= 0")
