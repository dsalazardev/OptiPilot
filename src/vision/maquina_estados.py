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
    TipoEvento,
    TransicionEstado,
)

__all__ = ["MaquinaEstados", "ResultadoEstado"]


def _exigir(condicion: bool, mensaje: str) -> None:
    if not condicion:
        raise ValueError(mensaje)


@dataclass(frozen=True)
class ResultadoEstado:
    """Salida de ``MaquinaEstados.actualizar`` (contrato api-pipeline §Fase 4)."""

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
    - Tras ``x_rearme`` fotogramas sin PARE visible, la señal PARE se **rearma**
      (FR-023) y queda registrada la transición con causa ``REARME``.
    """

    def __init__(self, params: ParametrosConfiguracion, t_inicial: float) -> None:
        _exigir(params.t_parada_s >= 0, "t_parada_s debe ser >= 0")
        _exigir(params.k_tolerancia >= 0, "k_tolerancia debe ser >= 0")
        _exigir(params.x_rearme >= 0, "x_rearme debe ser >= 0")
        _exigir(t_inicial >= 0, "t_inicial debe ser >= 0")
        self._params = params
        self._t_inicial = t_inicial
        self._estado: EstadoRobot = EstadoRobot.EN_MARCHA
        self._decision: DecisionMovimiento = DecisionMovimiento.AUTORIZADO
        self._t_inicio_parada: float | None = None
        self._siga_armado: bool = False
        self._pare_visible: bool = False
        self._fotogramas_sin_pare: int = 0
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
        self._fotogramas_sin_pare = (
            0 if ClaseSenal.PARE in presentes else self._fotogramas_sin_pare + 1
        )

        transiciones: list[TransicionEstado] = []
        decision: DecisionMovimiento

        if pare_confirmado_nuevo:
            self._pare_visible = True

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
                decision = DecisionMovimiento.NO_AUTORIZADO
            else:
                decision = DecisionMovimiento.AUTORIZADO

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
                    decision = DecisionMovimiento.AUTORIZADO
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
                    decision = DecisionMovimiento.NO_AUTORIZADO
            else:
                decision = DecisionMovimiento.NO_AUTORIZADO

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
                decision = DecisionMovimiento.AUTORIZADO
            else:
                decision = DecisionMovimiento.NO_AUTORIZADO

        if self._fotogramas_sin_pare >= self._params.x_rearme and self._pare_visible:
            self._rearmar_pare(transiciones, t_s)

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

    def _rearmar_pare(self, transiciones: list[TransicionEstado], t_s: float) -> None:
        self._pare_visible = False
        self._fotogramas_sin_pare = 0
        self._registrar_transicion(
            transiciones,
            self._estado,
            self._estado,
            CausaTransicion.REARME,
            t_s,
        )
