"""Contratos de datos compartidos del pipeline de visión (data-model.md).

Define los enums y dataclasses que intercambian las etapas: segmentación,
candidatos, detección confirmada, ocurrencias, eventos, máquina de estados y
métricas. Sin lógica de visión ni E/S: solo estructura y validaciones del
modelo (Constitución §II, §IV).

El bloque de control de trayectoria (Objetivos 3 y 4 del Reto 1) se añadió en
``specs/002`` y vive en el mismo módulo para que el compositor pueda consumir
``DecisionMovimiento`` junto a ``DecisionCompuesta`` sin introducir un ciclo de
importación entre ``vision`` y ``transporte`` (§II: el pipeline justifica la
estructura). Ninguna de las entidades preexistentes se modificó: el contrato
de 001 del que dependen sus 167 pruebas queda intacto (FR-026).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np

__all__ = [
    "CandidatoSenal",
    "CausaComando",
    "CausaTransicion",
    "ClaseSenal",
    "ComandoMovimiento",
    "DecisionCompuesta",
    "DecisionControl",
    "DecisionMovimiento",
    "EstadoOcurrencia",
    "EstadoRobot",
    "EventoSenal",
    "Lado",
    "LadoConocido",
    "MarcadorVisibilidadPlena",
    "Ocurrencia",
    "Parada",
    "PermisoMovimiento",
    "PosicionLinea",
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


class PermisoMovimiento(StrEnum):
    """Veredicto binario de la decisión de movimiento (FR-015)."""

    AUTORIZADO = "AUTORIZADO"
    NO_AUTORIZADO = "NO_AUTORIZADO"


@dataclass(frozen=True)
class DecisionMovimiento:
    """Decisión emitida a la capa de control: veredicto + causa (data-model §8).

    ``data-model.md`` §8 exige acompañar el veredicto de una ``causa: str`` que
    explique por qué se autoriza o no el movimiento (p. ej. ``PARE_CONFIRMADO``,
    ``T_CUMPLIDO_CON_SIGA``, ``SIGA_CONFIRMADO``, ``INICIO``). Al ser la causa
    distinta en cada emisión, la decisión es un value object frozen y no un enum
    simple: el veredicto sigue siendo un ``StrEnum`` (``PermisoMovimiento``) para
    poder compararse con ``is`` y serializarse sin ambigüedad.
    """

    veredicto: PermisoMovimiento
    causa: str

    @property
    def autorizada(self) -> bool:
        return self.veredicto is PermisoMovimiento.AUTORIZADO

    def __str__(self) -> str:
        return f"{self.veredicto}:{self.causa}"


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


@dataclass(frozen=True)
class Parada:
    """Detención por PARE y su reanudación (data-model §13, SC-008/FR-025).

    ``retardo_s`` es el tiempo adicional que el robot esperaba un SIGA una vez
    cumplidos los ``t_configurado_s`` minutos (contrato de eventos/métricas,
    §``paradas[].retardo_s``). Se calcula con :meth:`crear` para no dejar la
    resta a mano del consumidor.
    """

    inicio_t: float
    t_configurado_s: float
    fin_t: float
    retardo_s: float

    def __post_init__(self) -> None:
        _exigir(self.inicio_t >= 0, "inicio_t debe ser >= 0")
        _exigir(self.t_configurado_s >= 0, "t_configurado_s debe ser >= 0")
        _exigir(self.fin_t >= self.inicio_t, "fin_t no puede ser anterior a inicio_t")
        _exigir(self.retardo_s >= 0, "retardo_s debe ser >= 0")

    @classmethod
    def crear(cls, inicio_t: float, t_configurado_s: float, fin_t: float) -> "Parada":
        """Construye la parada derivando el retardo respecto al fin de T."""
        return cls(
            inicio_t=inicio_t,
            t_configurado_s=t_configurado_s,
            fin_t=fin_t,
            retardo_s=max(0.0, fin_t - (inicio_t + t_configurado_s)),
        )


@dataclass
class ResultadoProcesamiento:
    """Salida del pipeline para un fotograma (data-model §12).

    Desde la feature 002 transporta además la **posición lateral** estimada y la
    **propuesta del control** (``estimador → control``). El compositor no puede
    ejecutarse aquí porque necesita el veredicto de la FSM, que se actualiza
    después; el pipeline lo aplica en :meth:`PipelineVision.componer`. Los dos
    campos nuevos son opcionales para no romper a los consumidores de 001.
    """

    segmentacion: ResultadoSegmentacion
    candidatos: list[CandidatoSenal]
    senales_confirmadas: list[SenalConfirmada]
    eventos: list[EventoSenal]
    latencia_ms: float
    visibilidad_plena: list[MarcadorVisibilidadPlena] = field(default_factory=list)
    posicion: "PosicionLinea | None" = None
    decision_control: "DecisionControl | None" = None

    def __post_init__(self) -> None:
        _exigir(self.latencia_ms >= 0, "latencia_ms debe ser >= 0")


# ---------------------------------------------------------------------------
# Control de trayectoria (specs/002 — Objetivos 3 y 4 del Reto 1)
# ---------------------------------------------------------------------------


class Lado(StrEnum):
    """Lado en que se encontró la línea respecto al objetivo (data-model §4).

    Se evita ``int`` o ``bool`` porque el dominio es explícito y el valor tiene
    que poder imprimirse tal cual en la evidencia visual del póster.
    """

    IZQUIERDA = "IZQUIERDA"
    DERECHA = "DERECHA"


class ComandoMovimiento(StrEnum):
    """Vocabulario de la API de control: los cuatro valores fijados (data-model §5).

    ``IZQUIERDA`` y ``DERECHA`` significan **«la línea está de ese lado»**, no
    «gira a la izquierda/derecha»: la equivalencia con el giro físico depende
    del montaje de cámara y motores, y es un riesgo abierto declarado en la
    spec, no un detalle de implementación.

    ``DETENER`` es el valor por defecto ante cualquier condición no reconocida
    (FR-025): el control nunca devuelve ``None`` ni propaga excepción.
    """

    AVANZAR = "AVANZAR"
    IZQUIERDA = "IZQUIERDA"
    DERECHA = "DERECHA"
    DETENER = "DETENER"


class CausaComando(StrEnum):
    """Por qué se emitió el comando final (data-model §6, FR-027).

    Existe para que la precedencia sea demostrable en la defensa oral: cada
    comando emitido lleva su motivo, y ``VETO_FSM`` prueba que un PARE ganó
    siempre (SC-007).
    """

    SEGUIMIENTO = "SEGUIMIENTO"
    CORRECCION_DERECHA = "CORRECCION_DERECHA"
    CORRECCION_IZQUIERDA = "CORRECCION_IZQUIERDA"
    RECUPERACION = "RECUPERACION"
    PERDIDA_SIN_MEMORIA = "PERDIDA_SIN_MEMORIA"
    GRACIA_AGOTADA = "GRACIA_AGOTADA"
    VETO_FSM = "VETO_FSM"
    FALLO_SEGURO = "FALLO_SEGURO"


@dataclass(frozen=True)
class PosicionLinea:
    """Posición lateral estimada de la línea en un fotograma (data-model §2).

    Invariante central (FR-006): ``valida is False`` implica que **no** hay
    posición. ``x_px``, ``x_norm`` y ``error_norm`` quedan a ``None`` y la
    confianza a ``0.0``, de modo que es imposible que el control consuma una
    posición inventada. El error se calcula contra el ``x_objetivo``
    configurado, no contra el centro geométrico del fotograma (FR-004).
    """

    x_px: float | None
    x_norm: float | None
    error_norm: float | None
    ancho_banda_px: float
    confianza: float
    valida: bool
    ultimo_lado: Lado | None = None

    def __post_init__(self) -> None:
        _exigir(self.ancho_banda_px >= 0, "ancho_banda_px debe ser >= 0")
        _exigir(0.0 <= self.confianza <= 1.0, "confianza debe estar en [0, 1]")
        if self.valida:
            for nombre in ("x_px", "x_norm", "error_norm"):
                _exigir(
                    getattr(self, nombre) is not None,
                    f"una posición válida exige {nombre}",
                )
            _exigir(0.0 <= self.x_norm <= 1.0, "x_norm debe estar en [0, 1]")
            _exigir(self.x_px >= 0, "x_px debe ser >= 0")
        else:
            for nombre in ("x_px", "x_norm", "error_norm"):
                _exigir(
                    getattr(self, nombre) is None,
                    f"una posición inválida no puede traer {nombre}",
                )
            _exigir(self.confianza == 0.0, "una posición inválida exige confianza == 0.0")


@dataclass(frozen=True)
class LadoConocido:
    """Memoria del último lado en que se detectó la línea (data-model §3, FR-018).

    ``fotogramas_perdidos`` arranca en 1 al primer fotograma inválido y se
    reinicia a 0 en cada fotograma válido. Mientras sea ``<= n_gracia_busqueda``
    el robot sigue buscando hacia ``lado``; al superarlo (fotograma N+1) el
    control emite ``DETENER`` y congela la memoria para diagnóstico (FR-020).

    Es frozen a propósito: el estado del control avanza creando instancias
    nuevas, lo que hace que cada paso sea comparable y auditable.
    """

    lado: Lado
    fotograma: int
    fotogramas_perdidos: int

    def __post_init__(self) -> None:
        _exigir(self.fotograma >= 0, "fotograma debe ser >= 0")
        _exigir(self.fotogramas_perdidos >= 0, "fotogramas_perdidos debe ser >= 0")


@dataclass(frozen=True)
class DecisionControl:
    """Propuesta del control de trayectoria, antes del arbitraje de la FSM."""

    comando: ComandoMovimiento
    causa: CausaComando
    lateral: LadoConocido | None = None


@dataclass(frozen=True)
class DecisionCompuesta:
    """Comando final tras aplicar la precedencia de seguridad (data-model §7).

    Invariante (FR-024, SC-007): ``causa is CausaComando.VETO_FSM`` implica
    ``comando is ComandoMovimiento.DETENER``. El veto de la FSM PARE/SIGA se aplica
    aquí y no antes: es el árbitro que garantiza que un PARE confirmado en un
    fotograma no sea pisado por una corrección de dirección.
    """

    comando: ComandoMovimiento
    causa: CausaComando
    posicion: PosicionLinea
    permitido: PermisoMovimiento

    def __post_init__(self) -> None:
        if self.causa is CausaComando.VETO_FSM:
            _exigir(
                self.comando is ComandoMovimiento.DETENER,
                "el veto de la FSM solo puede producir DETENER",
            )
