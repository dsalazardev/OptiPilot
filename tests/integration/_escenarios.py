"""Utilidades compartidas por los tests de integración (Fase 6).

Centraliza la construcción de fotogramas sintéticos y el bucle que encadena
``PipelineVision`` → ``MaquinaEstados``, de modo que cada test se concentre en
sus aserciones y no en el cableado. El bucle replica el de producción
(``src/main.py::_correr``) para que los tests midan el comportamiento real.

Posiciones de las señales: se usan dos centros separados para que un octágono no
tape al otro. En el centro de la ROI caben ambos (radio 45 px, ROI de señales de
512×264 px) y ese caso *co-visible* es uno de los escenarios de T025.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np

from src.vision.configuracion import ParametrosConfiguracion
from src.vision.maquina_estados import MaquinaEstados
from src.vision.modelos import EstadoRobot, PermisoMovimiento
from src.vision.pipeline import PipelineVision
from tests.fixtures.generador_sintetico import (
    color_por_clase,
    crear_fondo,
    dibujar_linea_vertical,
    dibujar_octagono,
)

#: Centros de cada clase, separados para permitir co-visibilidad.
POSICIONES_SENAL: dict[str, tuple[int, int]] = {
    "PARE": (200, 140),
    "SIGA": (440, 140),
}
RADIO_SENAL = 45.0
X_LINEA = 320
GROSOR_LINEA = 24
ALTO = 480
ANCHO = 640

__all__ = [
    "ANCHO",
    "ALTO",
    "GROSOR_LINEA",
    "POSICIONES_SENAL",
    "RADIO_SENAL",
    "TrazaEscenario",
    "X_LINEA",
    "correr_escenario",
    "fotograma_con",
    "tramos_a_clases",
]


def fotograma_con(
    clases: Iterable[str],
    x_linea: int = X_LINEA,
    radio: float = RADIO_SENAL,
    ruido_sigma: float = 0.0,
    semilla: int = 0,
) -> np.ndarray:
    """Fotograma con la línea guía y un octágono por cada clase indicada."""
    imagen = crear_fondo(ALTO, ANCHO)
    dibujar_linea_vertical(imagen, x_linea, GROSOR_LINEA)
    for clase in clases:
        dibujar_octagono(imagen, POSICIONES_SENAL[clase], radio, color_por_clase(clase))
    if ruido_sigma > 0.0:
        from tests.fixtures.generador_sintetico import aplicar_ruido

        return aplicar_ruido(imagen, ruido_sigma, semilla)
    return imagen


def tramos_a_clases(
    total: int,
    tramos: Sequence[tuple[int, int, str | Iterable[str]]],
) -> list[list[str]]:
    """Construye el guion de la corrida a partir de tramos ``(inicio, fin, clase)``.

    ``clase`` puede ser un string o un iterable de strings (para señales
    co-visibles). El intervalo es semiabierto: ``inicio <= i < fin``.
    """
    guion: list[list[str]] = [[] for _ in range(total)]
    for inicio, fin, clase in tramos:
        clases = [clase] if isinstance(clase, str) else list(clase)
        for indice in range(max(0, inicio), min(total, fin)):
            guion[indice] = list(clases)
    return guion


@dataclass
class TrazaEscenario:
    """Traza fotograma a fotograma de un escenario end-to-end."""

    estados: list[EstadoRobot] = field(default_factory=list)
    veredictos: list[PermisoMovimiento] = field(default_factory=list)
    causas: list[str] = field(default_factory=list)
    eventos: list[tuple[int, str, str | None]] = field(default_factory=list)
    transiciones: list[tuple[int, str, str, str]] = field(default_factory=list)
    confirmados_por_fotograma: list[tuple[str, ...]] = field(default_factory=list)

    def cambios_de_estado(self) -> list[tuple[int, str, str]]:
        """``(fotograma, estado, causa)`` en cada cambio, en orden."""
        salida: list[tuple[int, str, str]] = []
        for indice, estado in enumerate(self.estados):
            if indice == 0 or estado is not self.estados[indice - 1]:
                salida.append((indice, estado.value, self.causas[indice]))
        return salida

    def tipos_de_evento(self) -> list[str]:
        return [tipo for _i, tipo, _c in self.eventos]

    def fotogramas_de(self, tipo: str, clase: str | None = None) -> list[int]:
        return [
            indice
            for indice, t, c in self.eventos
            if t == tipo and (clase is None or c == clase)
        ]

    def indice_de_causa(self, causa: str) -> int:
        return self.causas.index(causa)


def correr_escenario(
    params: ParametrosConfiguracion,
    guion: Sequence[Sequence[str]],
) -> TrazaEscenario:
    """Ejecuta el guion encadenando pipeline y máquina de estados.

    No construye métricas: T025 verifica reglas de estado, que es lo que la
    máquina decide. El registro completo de métricas lo cubre T024.
    """
    pipeline = PipelineVision(params)
    maquina = MaquinaEstados(params, t_inicial=0.0)
    traza = TrazaEscenario()
    fps = params.fps_objetivo

    for indice, clases in enumerate(guion):
        t_s = indice / fps
        resultado = pipeline.procesar(indice, t_s, fotograma_con(clases))

        for evento in resultado.eventos:
            traza.eventos.append(
                (indice, evento.tipo.value, evento.clase.value if evento.clase else None)
            )

        presentes = frozenset(senal.clase for senal in resultado.senales_confirmadas)
        estado = maquina.actualizar(presentes, resultado.eventos, t_s)
        for transicion in estado.transiciones_nuevas:
            traza.transiciones.append(
                (
                    indice,
                    transicion.desde.value,
                    transicion.hacia.value,
                    transicion.causa.value,
                )
            )

        traza.estados.append(estado.estado)
        traza.veredictos.append(estado.decision.veredicto)
        traza.causas.append(estado.decision.causa)
        traza.confirmados_por_fotograma.append(
            tuple(sorted(senal.clase.value for senal in resultado.senales_confirmadas))
        )

    return traza
