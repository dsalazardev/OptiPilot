"""Ley de control de trayectoria: de la posición al comando (Objetivo 4 del Reto 1).

**Técnicas autorizadas y únicamente ellas** (Reto 1, §«Se permite el uso de»):
comparación de umbral con histéresis —es decir, lógica booleana— y conteo de
fotogramas. No hay álgebra de control, ni PID, ni filtros, ni aprendizaje
(FR-011, FR-015, Principio I de la Constitución).

**Por qué zona muerta e histéresis y no un simple ``if |e| > 0``.** El error de
posición medido en los 9 vídeos reales oscila fotograma a fotograma; con la
misma línea leída, una comparación sin histéresis cambiaría de comando decenas
de veces por segundo y el robot oscilaría sobre la línea en vez de recorrerla.
La zona muerta da margen a los mandos correctivos y la histéresis impide que ese
margen se convierta en chatter (FR-013, FR-014).

**Frontera de responsabilidad.** Este módulo decide *hacia dónde está la línea*
y devuelve un comando. No sabe hacia dónde gira el robot: esa equivalencia
depende del montaje y es un riesgo abierto de la spec. Y no arbitra con la FSM:
si la FSM veta, el compositor lo impusará después (FR-024, SC-007).
"""

from __future__ import annotations

import math

from src.vision.configuracion import ParametrosConfiguracion
from src.vision.modelos import (
    CausaComando,
    ComandoMovimiento,
    DecisionControl,
    Lado,
    LadoConocido,
    PosicionLinea,
)

__all__ = ["ControlTrayectoria"]


class ControlTrayectoria:
    """Convierte la posición lateral estimada en un comando de movimiento.

    Es **stateful**: mantiene dos datos —el último lado en que se vio la línea
    y el último comando de seguimiento— que son los que hacen posible la
    histéresis y la recuperación. El estado avanza creando instancias nuevas de
    ``LadoConocido`` (frozen), nunca mutando las viejas, para que cada paso sea
    comparable y auditable (FR-018).
    """

    def __init__(self, params: ParametrosConfiguracion) -> None:
        self._params = params
        self._lateral: LadoConocido | None = None
        self._seguimiento: tuple[ComandoMovimiento, CausaComando] | None = None
        self._fotograma = 0

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def decidir(self, pos: PosicionLinea) -> DecisionControl:
        """Decide el comando de este fotograma. Nunca lanza ni devuelve ``None``.

        Ésta es la frontera con el consumidor: cualquier estado inesperado, tipo
        equivocado o excepción interna se convierte en ``DETENER`` con causa
        ``FALLO_SEGURO`` (FR-025, Q8/Q9). ``DETENER`` es el valor por defecto
        ante cualquier condición no reconocida.
        """
        try:
            if pos.valida:
                return self._con_linea(pos)
            return self._sin_linea()
        except Exception:
            # Deliberadamente amplio: el requisito es que el consumidor nunca
            # reciba una excepción, así que cualquier fallo interno se traduce.
            return self._fallo_seguro()

    def reiniciar(self) -> None:
        """Vacía la memoria para que no sobreviva entre corridas (FR-023, Q13)."""
        self._lateral = None
        self._seguimiento = None
        self._fotograma = 0

    # ------------------------------------------------------------------
    # Fotograma con línea visible
    # ------------------------------------------------------------------

    def _con_linea(self, pos: PosicionLinea) -> DecisionControl:
        """Línea válida: actualiza la memoria y elige el comando (Q10)."""
        error = self._exigir_error(pos)
        if error > 0:
            lado = Lado.DERECHA
        elif error < 0:
            lado = Lado.IZQUIERDA
        else:
            # `error == 0` no aporta información de lado, así que se conserva el
            # anterior. Sin memoria previa tampoco se inventa uno: un lado
            # fabricado mandaría a buscar en una dirección sin fundamento.
            lado = self._lateral.lado if self._lateral is not None else None

        # Q10: con línea visible el contador de pérdidas vuelve a cero.
        self._lateral = (
            LadoConocido(lado=lado, fotograma=self._fotograma, fotogramas_perdidos=0)
            if lado is not None
            else None
        )
        comando, causa = self._seguimiento_para(error)
        self._seguimiento = (comando, causa)
        self._fotograma += 1
        return DecisionControl(comando=comando, causa=causa, lateral=self._lateral)

    def _seguimiento_para(self, error: float) -> tuple[ComandoMovimiento, CausaComando]:
        """Aplica los dos umbrales de la histéresis (Q12, T021).

        Umbral de salida a corrección: ``|e| >= z + h``.
        Umbral de retorno a avanzar:   ``|e| <= z - h``.
        En la banda intermedia se mantiene el comando de seguimiento anterior.
        """
        zona = self._params.zona_muerta
        hist = self._params.histeresis
        magnitud = abs(error)

        if magnitud >= zona + hist:
            if error > 0:
                return ComandoMovimiento.DERECHA, CausaComando.CORRECCION_DERECHA
            return ComandoMovimiento.IZQUIERDA, CausaComando.CORRECCION_IZQUIERDA
        if magnitud <= zona - hist:
            return ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO
        # Banda de histéresis: se mantiene el último comando de seguimiento. Sin
        # historial, avanzar es la salida segura: no se inventa una corrección.
        if self._seguimiento is None:
            return ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO
        return self._seguimiento

    # ------------------------------------------------------------------
    # Fotograma sin línea
    # ------------------------------------------------------------------

    def _sin_linea(self) -> DecisionControl:
        """Pérdida de línea: buscar hacia el lado memorizado, o parar si no hay."""
        # La histéresis se olvida al perder la línea: durante la búsqueda la
        # pose del robot cambia sin ninguna medición válida, así que el comando
        # anterior describe una geometría que ya no existe. Al reaparecer la
        # línea, un error en la banda vuelve a empezar desde AVANZAR (T020).
        self._seguimiento = None
        self._fotograma += 1

        if self._lateral is None:
            return DecisionControl(
                comando=ComandoMovimiento.DETENER,
                causa=CausaComando.PERDIDA_SIN_MEMORIA,
                lateral=None,
            )

        limite = self._params.n_gracia_busqueda
        if self._lateral.fotogramas_perdidos > limite:
            # La gracia ya se agotó en un fotograma anterior: la memoria queda
            # congelada en el valor con el que se falló (FR-020).
            return DecisionControl(
                comando=ComandoMovimiento.DETENER,
                causa=CausaComando.GRACIA_AGOTADA,
                lateral=self._lateral,
            )

        self._lateral = LadoConocido(
            lado=self._lateral.lado,
            fotograma=self._lateral.fotograma,
            fotogramas_perdidos=self._lateral.fotogramas_perdidos + 1,
        )
        if self._lateral.fotogramas_perdidos > limite:
            # Fotograma N+1: se congela el contador en N+1, que es el número
            # real de fotogramas perdidos. Congelarlo en N dejaría el diagnóstico
            # indistinguible de una pérdida de 1 o de 50 fotogramas.
            return DecisionControl(
                comando=ComandoMovimiento.DETENER,
                causa=CausaComando.GRACIA_AGOTADA,
                lateral=self._lateral,
            )

        comando = (
            ComandoMovimiento.DERECHA
            if self._lateral.lado is Lado.DERECHA
            else ComandoMovimiento.IZQUIERDA
        )
        return DecisionControl(
            comando=comando,
            causa=CausaComando.RECUPERACION,
            lateral=self._lateral,
        )

    # ------------------------------------------------------------------
    # Fallo seguro
    # ------------------------------------------------------------------

    def _exigir_error(self, pos: PosicionLinea) -> float:
        """Extrae el error validándolo: un estado inconsistente da ``FALLO_SEGURO``."""
        error = pos.error_norm
        if error is None or isinstance(error, bool) or not isinstance(error, (int, float)):
            raise ValueError("posición válida sin error_norm utilizable")
        valor = float(error)
        if not math.isfinite(valor):
            raise ValueError("error_norm no finito")
        return valor

    def _fallo_seguro(self) -> DecisionControl:
        """Salida por defecto ante cualquier condición no reconocida (FR-025)."""
        return DecisionControl(
            comando=ComandoMovimiento.DETENER,
            causa=CausaComando.FALLO_SEGURO,
            lateral=self._lateral,
        )
