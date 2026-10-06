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

#: Cada cuántos turnos, una vez agotada la gracia, el robot reintenta la
#: búsqueda en vez de quedarse detenido en firme: uno de cada cuatro turnos
#: asoma hacia el lado memorizado, suficiente para reubicarse sin barrer en
#: redondo.
_REINTENTOS_BUSQUEDA = 4

#: Turnos de avance forzado tras salir de un STOP. La señal está **sobre la
#: pista**: al reanudar, el robot debe seguir recto y dejar que la línea
#: reaparezca por debajo del octágono, no girar buscándola. Sin esto, la parada
#: dejaba el control en estado de recuperación y el robot salía girando. Cuatro
#: turnos (≈1.6 s a la cadencia de 12 fotogramas) cubren el paso por encima de
#: la señal.
_TURNOS_TRAS_STOP = 4


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
        #: Fotogramas transcurridos desde que se agotó la gracia de búsqueda. Se
        #: lleva aparte de ``fotogramas_perdidos`` para no romper el congelado de
        #: la memoria (FR-020) que documenta el diagnóstico.
        self._reintento = 0
        #: Fotogramas de avance forzado que quedan al salir de un STOP.
        self._tras_stop = 0
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
        self._reintento = 0
        self._tras_stop = 0
        self._fotograma = 0

    def sostener(self) -> None:
        """Congela el seguimiento mientras la FSM veta el movimiento (PARE).

        **Por qué hace falta.** Mientras el robot está parado sobre el STOP la
        señal tapa la línea. Si el control siguiera contando fotogramas sin verla,
        al reanudar estaría en plena búsqueda y saldría **girando** hacia un lado
        en vez de continuar recto: es el fallo de "después del PARE intenta
        reubicarse". Aquí se descarta esa cuenta y se deja armado un tramo corto
        de avance para después de la parada.

        La señal SIGA no pasa por aquí: no veta el movimiento, así que el robot
        simplemente sigue su trayectoria sin detenerse.
        """
        self._seguimiento = None
        self._reintento = 0
        self._tras_stop = _TURNOS_TRAS_STOP * max(1, self._params.fotogramas_por_orden)
        if self._lateral is not None:
            self._lateral = LadoConocido(
                lado=self._lateral.lado,
                fotograma=self._lateral.fotograma,
                fotogramas_perdidos=0,
            )

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

        # Q10: con línea visible el contador de pérdidas vuelve a cero, y con él
        # el reintento de búsqueda: ya no hace falta. También se desarma el avance
        # posterior al STOP: la línea ya está a la vista.
        self._reintento = 0
        self._tras_stop = 0
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
            lado = Lado.DERECHA if error > 0 else Lado.IZQUIERDA
            comando = self._hacia(lado)
            causa = (
                CausaComando.CORRECCION_DERECHA
                if comando is ComandoMovimiento.DERECHA
                else CausaComando.CORRECCION_IZQUIERDA
            )
            return comando, causa
        if magnitud <= zona - hist:
            return ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO
        # Banda de histéresis: se mantiene el último comando de seguimiento. Sin
        # historial, avanzar es la salida segura: no se inventa una corrección.
        if self._seguimiento is None:
            return ComandoMovimiento.AVANZAR, CausaComando.SEGUIMIENTO
        return self._seguimiento

    def _hacia(self, lado: Lado) -> ComandoMovimiento:
        """Comando que acerca el robot al lado donde está la línea.

        ``invertir_lados`` existe por el montaje: si la cámara va girada respecto
        al chasis, o los motores están cruzados, seguir la línea exige girar al
        lado contrario del que parece. En vez de rehacer el montaje en plena
        pista, se invierte aquí y el resto del sistema no cambia.
        """
        derecha = lado is Lado.DERECHA
        if self._params.invertir_lados:
            derecha = not derecha
        return ComandoMovimiento.DERECHA if derecha else ComandoMovimiento.IZQUIERDA

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

        if self._tras_stop > 0:
            # Recién salido de un STOP: la señal estaba SOBRE la pista y puede
            # tapar la línea. Se avanza recto y se deja que reaparezca por debajo
            # del octágono, en vez de girar buscándola.
            self._tras_stop -= 1
            return DecisionControl(
                comando=ComandoMovimiento.AVANZAR,
                causa=CausaComando.SEGUIMIENTO,
                lateral=self._lateral,
            )

        if self._lateral is None:
            return DecisionControl(
                comando=ComandoMovimiento.DETENER,
                causa=CausaComando.PERDIDA_SIN_MEMORIA,
                lateral=None,
            )

        # La gracia está expresada en TURNOS (órdenes enviadas), no en fotogramas.
        # Con una cadencia de 12 fotogramas por orden, contar fotogramas agotaría
        # la búsqueda antes de mandar la primera y el robot se pararía sin llegar
        # a reubicarse: es lo que dejaba la recuperación muerta en la pista.
        paso = max(1, self._params.fotogramas_por_orden)
        limite = self._params.n_gracia_busqueda * paso
        if self._lateral.fotogramas_perdidos > limite:
            # La gracia se agotó: el robot se detiene, pero **no se queda
            # clavado**. Cada `_REINTENTOS_BUSQUEDA` turnos vuelve a asomarse
            # hacia el lado memorizado. Sin este reintento, al quedarse parado la
            # línea no volvía a entrar en el cuadro y el robot quedaba muerto
            # sobre la pista al salir de una curva; con él puede reubicarse sin
            # barrer en redondo. La memoria de fotogramas_perdidos sigue congelada
            # (FR-020); el reintento lo lleva su propio contador.
            self._reintento += 1
            if (self._reintento // paso) % _REINTENTOS_BUSQUEDA == 0:
                return DecisionControl(
                    comando=self._hacia(self._lateral.lado),
                    causa=CausaComando.RECUPERACION,
                    lateral=self._lateral,
                )
            return DecisionControl(
                comando=ComandoMovimiento.DETENER,
                causa=CausaComando.GRACIA_AGOTADA,
                lateral=self._lateral,
            )

        self._reintento = 0
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

        comando = self._hacia(self._lateral.lado)
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
