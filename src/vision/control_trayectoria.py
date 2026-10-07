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
from dataclasses import dataclass

from src.vision.configuracion import ParametrosConfiguracion
from src.vision.modelos import (
    CausaComando,
    ClaseSenal,
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


@dataclass(frozen=True)
class _CruceSenal:
    """Señal confirmada que el robot está atravesando (PARE o SIGA).

    Mientras exista un cruce, una línea que no se ve **no es una pista
    perdida**: es la señal tapándola. El cruce no dura una cantidad fija de
    fotogramas ni de turnos —cada señal puede tardar un tiempo distinto en
    quedar atrás—, sino hasta que la línea vuelva a detectarse.
    """

    clase: ClaseSenal
    ocurrencia_id: int


class ControlTrayectoria:
    """Convierte la posición lateral estimada en un comando de movimiento.

    Es **stateful**: mantiene el último lado en que se vio la línea y el último
    comando de seguimiento —que hacen posible la histéresis y la recuperación—
    y el **cruce de señal** en curso. El estado avanza creando instancias nuevas
    de ``LadoConocido`` (frozen), nunca mutando las viejas, para que cada paso
    sea comparable y auditable (FR-018).

    **Señal sobre la pista frente a línea perdida.** El estimador es honesto: si
    el octágono tapa la línea, devuelve una posición inválida, exactamente igual
    que si la línea se hubiera salido del cuadro. La diferencia no está en la
    medición sino en el contexto: cuando una señal se confirma, el pipeline avisa
    con :meth:`iniciar_cruce` y este control deja de interpretar la ausencia como
    una pérdida. Sin ese contexto, el robot trataba el cruce como un
    ``descarrilamiento`` y salía a buscar la pista de lado a lado en plena señal.
    """

    def __init__(self, params: ParametrosConfiguracion) -> None:
        self._params = params
        self._lateral: LadoConocido | None = None
        self._seguimiento: tuple[ComandoMovimiento, CausaComando] | None = None
        #: Fotogramas transcurridos desde que se agotó la gracia de búsqueda. Se
        #: lleva aparte de ``fotogramas_perdidos`` para no romper el congelado de
        #: la memoria (FR-020) que documenta el diagnóstico.
        self._reintento = 0
        #: Señal que el robot está atravesando, si hay alguna. Mientras exista,
        #: una posición inválida no entra en ``_sin_linea``: la señal está
        #: tapando la línea y hay que seguir recto, no buscar.
        self._cruce: _CruceSenal | None = None
        #: Fotogramas que lleva sin verse la señal del cruce activo. Se reinicia
        #: a 0 en cuanto se ve y al final de cada fotograma vetado (el robot
        #: parado no se está alejando del cartel).
        self._ausencia = 0
        #: Último fotograma en que se vio un PARE. Sostiene la «gracia larga»:
        #: ninguna ocurrencia nueva puede volver a parar hasta que el cartel
        #: lleve ``x_rearme_cruce`` fotogramas fuera de pantalla.
        self._ultimo_pare_visto: int | None = None
        #: Ocurrencias ya atendidas: una misma ``ocurrencia_id`` produce una
        #: sola acción aunque la señal desaparezca y vuelva durante el cruce.
        self._ocurrencias_atendidas: set[int] = set()
        #: True mientras la FSM veta el movimiento (parada del PARE). ``decidir``
        #: lo consume al fotograma siguiente; el compositor lo renueva en cada
        #: fotograma vetado, así que el cruce sobrevive toda la parada.
        self._sostenido = False
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
            # El aviso del compositor dura un fotograma: se consume aquí.
            sostenido = self._sostenido
            self._sostenido = False

            if self._cruce is not None:
                if not sostenido and (
                    # La señal salió de pantalla y la línea está de vuelta:
                    # seguimiento normal otra vez.
                    (pos.valida and self._ausencia >= self._params.x_rearme)
                    # Red de seguridad: la señal lleva tanto fuera que ya no
                    # puede estar tapando nada; si la línea no volvió, decide
                    # la recuperación normal.
                    or self._ausencia >= self._params.x_rearme_cruce
                ):
                    self._cruce = None
                else:
                    # La señal sigue en pantalla (o el robot está detenido por
                    # el PARE): avanzar recto aunque la línea se vea por un
                    # lado. No se busca ni se gira: el cartel está encima.
                    self._fotograma += 1
                    return DecisionControl(
                        comando=ComandoMovimiento.AVANZAR,
                        causa=CausaComando.CRUCE_SENAL,
                        lateral=self._lateral,
                    )

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
        self._cruce = None
        self._ausencia = 0
        self._ultimo_pare_visto = None
        self._ocurrencias_atendidas.clear()
        self._sostenido = False
        self._fotograma = 0

    def iniciar_cruce(self, clase: ClaseSenal, ocurrencia_id: int) -> bool:
        """Avisa que una señal se confirmó y el robot va a atravesarla.

        Devuelve ``True`` la **primera** vez que se ve esa ocurrencia —y entonces
        su confirmación debe llegar normalmente al resto del sistema— y ``False``
        si ya fue atendida: una misma ``ocurrencia_id`` solo produce una acción,
        aunque la señal desaparezca y vuelva a aparecer mientras el robot la
        cruza, y aunque el detector la rearme por ``x_rearme``.

        Este aviso es lo que separa «la señal tapa la línea» de «perdí la pista».
        """
        if ocurrencia_id in self._ocurrencias_atendidas:
            return False
        self._ocurrencias_atendidas.add(ocurrencia_id)
        self._cruce = _CruceSenal(clase=clase, ocurrencia_id=ocurrencia_id)
        self._ausencia = 0
        self._reintento = 0
        return True

    def observar_senal(self, presentes: frozenset[ClaseSenal]) -> None:
        """Registra qué señales se ven en este fotograma (lo llama el pipeline).

        Hace dos cosas que ``decidir`` no puede hacer por sí solo, porque no
        recibe las señales:

        - El **cruce solo termina cuando su señal deja de verse** (más la línea
          de vuelta): mientras el cartel esté en pantalla el robot sigue recto,
          aunque la línea asome por un lado. Sin esto el cruce moría al primer
          trozo de línea y el robot se ponía a buscar encima de la señal.
        - Tras un **PARE**, ninguna ocurrencia nueva puede volver a detener al
          robot hasta que el cartel lleve ``x_rearme_cruce`` fotogramas fuera de
          pantalla: el mismo PARE no se procesa dos veces por lento que vaya el
          robot, y solo se vuelve a aceptar si de verdad se perdió de vista.
        """
        if ClaseSenal.PARE in presentes:
            self._ultimo_pare_visto = self._fotograma
        if self._cruce is None:
            return
        self._ausencia = 0 if self._cruce.clase in presentes else self._ausencia + 1

    @property
    def cruce_activo(self) -> bool:
        """¿El robot está atravesando una señal confirmada?"""
        return self._cruce is not None

    @property
    def rearme_bloqueado(self) -> bool:
        """¿Debe el detector abstenerse de cerrar ocurrencias (rearmar)?

        Se bloquea mientras hay cruce y, tras un PARE visto, hasta que pase la
        gracia larga ``x_rearme_cruce``. Es lo que impide que el mismo cartel
        genere una ocurrencia nueva y vuelva a parar al robot.
        """
        if self._cruce is not None:
            return True
        if self._ultimo_pare_visto is None:
            return False
        return (self._fotograma - self._ultimo_pare_visto) < self._params.x_rearme_cruce

    def sostener(self) -> None:
        """Marca que la FSM tiene el movimiento vetado en este fotograma (PARE).

        **Por qué hace falta.** Mientras el robot está parado en el STOP la señal
        tapa la línea. El cruce debe sobrevivir a toda la parada y la cuenta de
        ausencia se reinicia: el robot detenido no se está alejando del cartel,
        así que al reanudar empieza a contar de cero y el avance recto dura al
        menos la ventana completa.

        La señal SIGA no pasa por aquí: no veta el movimiento, así que el cruce
        avanza sin detenerse.
        """
        self._sostenido = True
        self._seguimiento = None
        self._reintento = 0
        self._ausencia = 0
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
        # el reintento de búsqueda: ya no hace falta.
        self._reintento = 0
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
        """Pérdida de línea: buscar hacia el lado memorizado, o parar si no hay.

        Solo se llega aquí **sin cruce de señal activo**: si una señal confirmada
        está siendo atravesada, ``decidir`` devuelve el avance recto antes de
        entrar a esta rama, porque la línea ausente es la señal tapándola y no
        una pista perdida.
        """
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
