"""Confirmación temporal de señales PARE/SIGA y ciclo de ocurrencias (T012).

Esta etapa NO usa OpenCV: trabaja sobre los ``CandidatoSenal`` ya validados.
Es lógica propia del equipo (Constitución §I): ninguna biblioteca delega la
decisión. La técnica aplicada es el **filtrado temporal / consenso por ventana**
de fotogramas: un candidato válido repetido a lo largo del tiempo se confirma
(FR-011), las pérdidas breves (≤ ``k_tolerancia``) no revocan lo confirmado y
una ocurrencia se re-arma tras ``x_rearme`` fotogramas sin ver la señal
(FR-021). Las decisiones son puramente deterministas (mismas entradas ⇒ mismas
salidas, Principio IV).

Contratos consumidos (data-model §5/§6/§10):
- ``SenalConfirmada``: solo en flanco de subida (una por confirmación), ligada a
  su ``Ocurrencia``;
- ``Ocurrencia``: delimitada por el re-armado; ``detecciones`` = fotogramas
  confirmados acumulados;
- ``EventoSenal``: ``PARE_CONFIRMADO``/``SIGA_CONFIRMADO`` (flanco de subida),
  ``SENAL_PERDIDA`` (confirmación revocada) y ``PARE_REARMADO`` (ocurrencia
  PARE cerrada).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .configuracion import ParametrosConfiguracion
from .modelos import (
    CandidatoSenal,
    ClaseSenal,
    EventoSenal,
    Ocurrencia,
    SenalConfirmada,
    TipoEvento,
)

__all__ = [
    "Detector",
    "ResultadoDeteccion",
]


@dataclass
class _RastreoSenal:
    """Estado temporal de una clase: acumulación, confirmación y ocurrencia."""

    confirmada: bool = False
    conteo: int = 0
    sin_ver: int = 0
    ocurrencia_id: int | None = None


@dataclass(frozen=True)
class ResultadoDeteccion:
    """Salida del detector para un fotograma (tubería interna del pipeline)."""

    senales_confirmadas: tuple[SenalConfirmada, ...] = ()
    eventos: tuple[EventoSenal, ...] = ()
    presentes: frozenset[ClaseSenal] = frozenset()
    clases_rearmadas: frozenset[ClaseSenal] = frozenset()


def _candidato_de_clase(
    candidatos: Sequence[CandidatoSenal], clase: ClaseSenal
) -> CandidatoSenal | None:
    """Primer candidato válido de la clase indicada."""
    for c in candidatos:
        if c.es_valido and c.clase_estimada == clase:
            return c
    return None


class Detector:
    """Confirmación temporal N/K/X y ciclo de vida de ocurrencias (T012)."""

    def __init__(self, params: ParametrosConfiguracion) -> None:
        self._params = params
        self._rastreo: dict[ClaseSenal, _RastreoSenal] = {
            ClaseSenal.PARE: _RastreoSenal(),
            ClaseSenal.SIGA: _RastreoSenal(),
        }
        self._ocurrencias: list[Ocurrencia] = []
        self._proximo_id = 0

    @property
    def ocurrencias(self) -> list[Ocurrencia]:
        """Ocurrencias registradas (activas y cerradas), en orden de creación."""
        return list(self._ocurrencias)

    def actualizar(
        self,
        candidatos: Sequence[CandidatoSenal],
        indice: int,
        t_s: float,
    ) -> ResultadoDeteccion:
        """Procesa un fotograma: confirma, revoca, re-arma y emite eventos."""
        confirmadas: list[SenalConfirmada] = []
        eventos: list[EventoSenal] = []
        presentes: set[ClaseSenal] = set()
        rearmadas: set[ClaseSenal] = set()

        for clase in (ClaseSenal.PARE, ClaseSenal.SIGA):
            rastro = self._rastreo[clase]
            candidato = _candidato_de_clase(candidatos, clase)

            if candidato is not None:
                rastro.sin_ver = 0
                if not rastro.confirmada:
                    rastro.conteo += 1
                    if rastro.conteo >= self._params.n_confirmacion:
                        # Flanco de subida: confirma la señal (FR-011).
                        rastro.confirmada = True
                        confirmadas.append(
                            self._confirmar(clase, candidato, rastro, indice, t_s)
                        )
                        eventos.append(
                            EventoSenal(
                                tipo=(
                                    TipoEvento.PARE_CONFIRMADO
                                    if clase is ClaseSenal.PARE
                                    else TipoEvento.SIGA_CONFIRMADO
                                ),
                                fotograma_idx=indice,
                                t_s=t_s,
                                clase=clase,
                                centro_px=candidato.centro_px,
                                ocurrencia_id=rastro.ocurrencia_id,
                            )
                        )
                # Fotograma confirmado adicional de la ocurrencia actual.
                if rastro.confirmada:
                    self._registrar_deteccion(rastro.ocurrencia_id)
            else:
                rastro.sin_ver += 1
                if rastro.confirmada and rastro.sin_ver > self._params.k_tolerancia:
                    # Pérdida que excede K: se revoca la confirmación.
                    rastro.confirmada = False
                    rastro.conteo = 0
                    eventos.append(
                        EventoSenal(
                            tipo=TipoEvento.SENAL_PERDIDA,
                            fotograma_idx=indice,
                            t_s=t_s,
                            clase=clase,
                            ocurrencia_id=rastro.ocurrencia_id,
                        )
                    )
                elif not rastro.confirmada and rastro.sin_ver > self._params.k_tolerancia:
                    # Sin confirmar aún: un hueco > K cancela lo acumulado.
                    rastro.conteo = 0
                if rastro.ocurrencia_id is not None and rastro.sin_ver >= self._params.x_rearme:
                    # Re-armado: cerrar la ocurrencia y permitir una nueva (FR-021).
                    self._cerrar_ocurrencia(rastro.ocurrencia_id, indice, t_s)
                    if clase is ClaseSenal.PARE:
                        eventos.append(
                            EventoSenal(
                                tipo=TipoEvento.PARE_REARMADO,
                                fotograma_idx=indice,
                                t_s=t_s,
                                clase=clase,
                                ocurrencia_id=rastro.ocurrencia_id,
                            )
                        )
                    rastro.ocurrencia_id = None
                    rearmadas.add(clase)

            if rastro.confirmada:
                presentes.add(clase)

        return ResultadoDeteccion(
            senales_confirmadas=tuple(confirmadas),
            eventos=tuple(eventos),
            presentes=frozenset(presentes),
            clases_rearmadas=frozenset(rearmadas),
        )

    def _confirmar(
        self,
        clase: ClaseSenal,
        candidato: CandidatoSenal,
        rastro: _RastreoSenal,
        indice: int,
        t_s: float,
    ) -> SenalConfirmada:
        """Crea (si falta) la ocurrencia y devuelve la señal confirmada."""
        if rastro.ocurrencia_id is None:
            rastro.ocurrencia_id = self._proximo_id
            self._proximo_id += 1
            self._ocurrencias.append(
                Ocurrencia(
                    id=rastro.ocurrencia_id,
                    clase=clase,
                    fotograma_inicio=indice,
                    t_inicio=t_s,
                )
            )
        return SenalConfirmada(
            clase=clase,
            centro_px=candidato.centro_px,
            area_rel=candidato.area_rel,
            fotograma_idx=indice,
            t_s=t_s,
            ocurrencia_id=rastro.ocurrencia_id,
        )

    def _registrar_deteccion(self, ocurrencia_id: int | None) -> None:
        """Incrementa el contador de fotogramas confirmados de la ocurrencia."""
        if ocurrencia_id is not None:
            self._ocurrencias[ocurrencia_id].detecciones += 1

    def _cerrar_ocurrencia(self, ocurrencia_id: int, indice: int, t_s: float) -> None:
        """Marca la ocurrencia como cerrada en el fotograma del re-armado."""
        self._ocurrencias[ocurrencia_id].cerrar(indice, t_s)