"""Máquina de estados determinista PARE/SIGA (US2, Reto 1).

Implementa el cronómetro de parada mínima T (``t_parada_s``), el armado del
SIGA, el latcheo/rearme del PARE y la tolerancia a pérdidas momentáneas K
(``k_tolerancia``) según la tabla de transiciones y las clarificaciones de
``data-model.md`` (FR-015, FR-016, FR-017, FR-018, FR-019, FR-020, FR-021,
FR-022, FR-023, FR-024 y FR-025). Es determinista: ``actualizar`` depende solo
de (``presentes``, ``eventos``, ``t_s``); la misma secuencia produce siempre el
mismo ``ResultadoEstado`` (Constitución §IV, principio de determinismo total).

Técnicas usadas (todas clásicas y permitidas, sin DL): solo lógica de estados
y cronómetro sobre las confirmaciones ya emitidas por la etapa de detección
(FR-015..FR-025). Este módulo no realiza visión: consume ``presentes`` (señales
confirmadas en el fotograma) y ``eventos`` (confirmaciones y pérdidas
latcheadas) y emite la decisión de movimiento y las transiciones nuevas
(FR-023). La tolerancia K se aplica aguas arriba, en ``deteccion.py`` (T012);
como aquí solo se actúa sobre confirmaciones de flanco de subida, una pérdida
momentánea ≤ K no altera ni el estado ni el cronómetro (FR-018/FR-022).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from src.vision.configuracion import ParametrosConfiguracion
from src.vision.modelos import (
    CausaTransicion,
    ClaseSenal,
    DecisionMovimiento,
    EstadoRobot,
    EventoSenal,
    PermisoMovimiento,
    TipoEvento,
    TransicionEstado,
)

__all__ = ["MaquinaEstados", "ResultadoEstado"]

CAUSA_INICIO = "INICIO"
CAUSA_PARE_DETENIDO = "PARE_DETENIDO"
CAUSA_T_MINIMO_EN_CURSO = "T_MINIMO_EN_CURSO"
CAUSA_T_CUMPLIDO_SIN_SIGA = "T_CUMPLIDO_SIN_SIGA"
CAUSA_ESPERANDO_SIGA = "ESPERANDO_SIGA"
CAUSA_T_CUMPLIDO_CON_SIGA = "T_CUMPLIDO_CON_SIGA"
CAUSA_SIGA_EN_MARCHA = "SIGA_EN_MARCHA"


def _no_autorizado(causa: str) -> DecisionMovimiento:
    return DecisionMovimiento(veredicto=PermisoMovimiento.NO_AUTORIZADO, causa=causa)


def _autorizado(causa: str) -> DecisionMovimiento:
    return DecisionMovimiento(veredicto=PermisoMovimiento.AUTORIZADO, causa=causa)


def _exigir(condicion: bool, mensaje: str) -> None:
    if not condicion:
        raise ValueError(mensaje)


@dataclass(frozen=True)
class ResultadoEstado:
    """Salida de ``MaquinaEstados.actualizar`` (contrato api-pipeline §Fase 4).

    Lleva exactamente los tres campos que documenta el contrato
    (``estado``, ``decision``, ``transiciones_nuevas``). La FSM no emite eventos
    propios: el rearme de la señal PARE es responsabilidad de la etapa de
    detección, que es la única que observa la visibilidad real, y llega ya
    filtrado por el pipeline en ``resultado.eventos``.
    """

    estado: EstadoRobot
    decision: DecisionMovimiento
    transiciones_nuevas: list[TransicionEstado] = field(default_factory=list)


class MaquinaEstados:
    """Máquina de estados finita (FSM) determinista para la detención/reanudación.

    Estados (``EstadoRobot``): ``EN_MARCHA``, ``DETENIDO_MINIMO`` y
    ``DETENIDO_ESPERANDO_SIGA`` (FR-015/FR-017). El cronómetro T es el mínimo
    de detención (``t_parada_s``): no reanuda por sí solo (FR-017) y exige un
    SIGA confirmado (armado) para cerrar la parada (FR-016/FR-017).

    Reglas (tabla data-model + FR-018..FR-025):
    - Un PARE nuevo confirmado detiene (FR-015) e inicia T.
    - El SIGA confirmado durante la detención (incluido el co-visible al
      detenerse, Q-A) queda **armado**; al cumplirse T reanuda (FR-016/FR-017).
    - Un PARE nuevo durante la detención **no** reinicia T ni invalida el SIGA
      armado (Q-C, FR-020/FR-021).
    - Al cumplirse T sin SIGA armado el robot queda en ``DETENIDO_ESPERANDO_SIGA``
      y reanuda solo ante un SIGA confirmado (FR-017).
    - Una pérdida momentánea ≤ K no afecta el estado ni el cronómetro, porque la
      máquina solo reacciona a confirmaciones de flanco de subida (FR-018/FR-022).

    El *latch* del PARE (cuenta de ``x_rearme`` fotogramas sin ver la señal y
    emisión de ``PARE_REARMADO``, FR-023) es de una sola propiedad: lo lleva la
    etapa de detección (``deteccion.py``), la única que observa la visibilidad
    real. La FSM no lo duplica porque solo recibe confirmaciones de flanco de
    subida: con su propio contador mediría "fotogramas sin confirmación" en
    vez de "fotogramas sin señal", se rearmaría con el octágono todavía a la
    vista y además duplicaría el evento ``PARE_REARMADO`` en ``eventos.jsonl``.
    """

    def __init__(self, params: ParametrosConfiguracion, t_inicial: float) -> None:
        _exigir(params.t_parada_s >= 0, "t_parada_s debe ser >= 0")
        _exigir(params.k_tolerancia >= 0, "k_tolerancia debe ser >= 0")
        _exigir(t_inicial >= 0, "t_inicial debe ser >= 0")
        self._params = params
        self._t_inicial = t_inicial
        self._estado: EstadoRobot = EstadoRobot.EN_MARCHA
        self._decision: DecisionMovimiento = DecisionMovimiento(
            veredicto=PermisoMovimiento.AUTORIZADO,
            causa=CAUSA_INICIO,
        )
        self._t_inicio_parada: float | None = None
        self._siga_armado: bool = False
        self._fotograma: int = 0

    @property
    def estado(self) -> EstadoRobot:
        return self._estado

    @property
    def decision(self) -> DecisionMovimiento:
        """Última decisión de movimiento emitida (contrato api-pipeline)."""
        return self._decision

    def actualizar(
        self,
        presentes: frozenset[ClaseSenal],
        eventos: Sequence[EventoSenal],
        t_s: float,
    ) -> ResultadoEstado:
        """Avanza la FSM un fotograma con las señales confirmadas y sus eventos.

        ``presentes`` agrupa las señales confirmadas en el instante (incluidas
        las co-visibles, Q-A). ``eventos`` transporta las confirmaciones de
        PARE/SIGA y las pérdidas ya latcheadas por la etapa de detección.
        Devuelve la decisión de movimiento y las transiciones nuevas (FR-023).
        """
        _exigir(t_s >= self._t_inicial, "t_s no debe retroceder respecto a t_inicial")

        pare_confirmado_nuevo = self._confirmado(eventos, ClaseSenal.PARE)
        siga_confirmado_nuevo = self._confirmado(eventos, ClaseSenal.SIGA)

        transiciones: list[TransicionEstado] = []
        decision: DecisionMovimiento

        if self._estado is EstadoRobot.EN_MARCHA:
            if pare_confirmado_nuevo:
                self._registrar_transicion(
                    transiciones,
                    EstadoRobot.EN_MARCHA,
                    EstadoRobot.DETENIDO_MINIMO,
                    CausaTransicion.PARE_CONFIRMADO,
                    t_s,
                )
                self._estado = EstadoRobot.DETENIDO_MINIMO
                self._t_inicio_parada = t_s
                if ClaseSenal.SIGA in presentes:
                    self._siga_armado = True
                decision = _no_autorizado(CAUSA_PARE_DETENIDO)
            else:
                decision = _autorizado(CAUSA_INICIO)

        elif self._estado is EstadoRobot.DETENIDO_MINIMO:
            if ClaseSenal.SIGA in presentes or siga_confirmado_nuevo:
                self._siga_armado = True
            _exigir(
                self._t_inicio_parada is not None,
                "DETENIDO_MINIMO exige cronómetro iniciado",
            )
            t_transcurrido = t_s - self._t_inicio_parada
            if t_transcurrido >= self._params.t_parada_s:
                if self._siga_armado:
                    self._registrar_transicion(
                        transiciones,
                        EstadoRobot.DETENIDO_MINIMO,
                        EstadoRobot.EN_MARCHA,
                        CausaTransicion.T_CUMPLIDO,
                        t_s,
                    )
                    self._estado = EstadoRobot.EN_MARCHA
                    self._t_inicio_parada = None
                    self._siga_armado = False
                    decision = _autorizado(CAUSA_T_CUMPLIDO_CON_SIGA)
                else:
                    self._registrar_transicion(
                        transiciones,
                        EstadoRobot.DETENIDO_MINIMO,
                        EstadoRobot.DETENIDO_ESPERANDO_SIGA,
                        CausaTransicion.T_CUMPLIDO,
                        t_s,
                    )
                    self._estado = EstadoRobot.DETENIDO_ESPERANDO_SIGA
                    self._t_inicio_parada = None
                    decision = _no_autorizado(CAUSA_T_CUMPLIDO_SIN_SIGA)
            else:
                decision = _no_autorizado(CAUSA_T_MINIMO_EN_CURSO)

        else:
            if siga_confirmado_nuevo:
                self._registrar_transicion(
                    transiciones,
                    EstadoRobot.DETENIDO_ESPERANDO_SIGA,
                    EstadoRobot.EN_MARCHA,
                    CausaTransicion.SIGA_CONFIRMADO,
                    t_s,
                )
                self._estado = EstadoRobot.EN_MARCHA
                self._t_inicio_parada = None
                self._siga_armado = False
                decision = _autorizado(CausaTransicion.SIGA_CONFIRMADO.value)
            else:
                decision = _no_autorizado(CAUSA_ESPERANDO_SIGA)

        self._decision = decision
        self._fotograma += 1

        return ResultadoEstado(
            estado=self._estado,
            decision=decision,
            transiciones_nuevas=transiciones,
        )

    @staticmethod
    def _confirmado(eventos: Sequence[EventoSenal], clase: ClaseSenal) -> bool:
        """¿Hay confirmación de flanco de subida para ``clase`` en este fotograma?"""
        tipo = (
            TipoEvento.PARE_CONFIRMADO
            if clase is ClaseSenal.PARE
            else TipoEvento.SIGA_CONFIRMADO
        )
        return any(e.tipo is tipo and e.clase is clase for e in eventos)

    def _registrar_transicion(
        self,
        transiciones: list[TransicionEstado],
        desde: EstadoRobot,
        hacia: EstadoRobot,
        causa: CausaTransicion,
        t_s: float,
    ) -> None:
        transiciones.append(
            TransicionEstado(
                desde=desde,
                hacia=hacia,
                causa=causa,
                fotograma_idx=self._fotograma,
                t_s=t_s,
            )
        )

