"""Cola de desacople entre el bucle de visión y la radio (T030, FR-031/FR-032).

El problema que resuelve
------------------------
El bucle de visión debe correr a ~30 fps y tomar decisiones de forma continua.
Si el envío al robot se hiciera dentro de ese bucle, un enlace caído bloquearía
el ``sendall`` hasta agotar el timeout en **cada** fotograma, y el robot dejaría
de reaccionar mientras el software espera a la radio. Eso rompe el requisito de
tiempo real (SC-005).

Este módulo separa las dos escalas de tiempo:

```text
bucle de visión (rápido)              hilo de transporte (lento, bloqueante)
────────────────────────              ────────────────────────────────────────
cola.encolar(comando)  [O(1)]  ───▶   cola.drenar(transporte)  [hace el sendall]
```

``encolar`` solo añade a una lista en memoria: O(1), sin E/S. El envío real
ocurre en ``drenar``, que vive en **otro hilo**. El bucle de visión nunca llama a
``drenar`` (T14 del contrato); ese es el invariante que hace no bloqueante al
bucle.

Deduplicación (FR-032)
----------------------
A 30 fps, la misma corrección de dirección se recalcularía idéntica durante
varios fotogramas seguidos. Reenviarla treinta veces por segundo no aporta nada
y satura la radio. ``encolar`` descarta un comando **solo** cuando es idéntico al
último ya enviado y no hay nada pendiente: así se transmiten las *transiciones*
de estado, que es la información útil.

Seguridad
---------
``drenar`` nunca propaga excepciones: un fallo deja el comando **en la cola**
para reintentarlo y lo registra en ``ultimo_error`` (FR-034). Un fallo de
transporte cambia la *entrega*, nunca la *decisión* de control.
"""

from __future__ import annotations

import threading
from collections import deque

from src.transporte.base import Transporte
from src.vision.modelos import ComandoMovimiento

__all__ = ["ColaTransporte"]


class ColaTransporte:
    """Cola FIFO de comandos pendientes, segura entre hilos.

    El estado está protegido por un ``Lock`` porque ``encolar`` lo llama el
    hilo de visión y ``drenar`` el hilo de transporte. **La E/S ocurre fuera del
    lock**: si ``drenar`` mantuviera el lock durante un ``sendall`` bloqueado,
    ``encolar`` esperaría a la radio y se reintroduciría exactamente el problema
    que esta clase elimina.
    """

    def __init__(self) -> None:
        self._pendientes: deque[ComandoMovimiento] = deque()
        self._ultimo_enviado: ComandoMovimiento | None = None
        self._ultimo_error: str | None = None
        self._lock = threading.Lock()

    def encolar(self, comando: ComandoMovimiento) -> bool:
        """Añade un comando a la cola. O(1) y **sin E/S** (FR-031).

        Returns:
            ``True`` si el comando quedó encolado; ``False`` si se descartó por
            ser idéntico al último enviado y no haber nada pendiente (FR-032).
        """
        with self._lock:
            if not self._pendientes and comando is self._ultimo_enviado:
                return False
            self._pendientes.append(comando)
            return True

    def drenar(self, transporte: Transporte) -> int:
        """Transmite los comandos pendientes en orden FIFO (T12).

        Se detiene al primer fallo: el comando que falló **permanece** en la
        cabeza de la cola para que un ``drenar`` posterior lo reintente (T13).
        Nunca lanza, aunque el transporte esté desconectado (FR-034, Q22).

        Returns:
            Cuántos comandos se transmitieron con éxito en esta llamada.
        """
        transmitidos = 0
        while True:
            with self._lock:
                if not self._pendientes:
                    return transmitidos
                comando = self._pendientes[0]

            # La llamada bloqueante ocurre FUERA del lock: el bucle de visión
            # no debe esperar al enlace para poder encolar el siguiente comando.
            try:
                aceptado = transporte.enviar(comando)
                error = None if aceptado else transporte.ultimo_error()
            except Exception as exc:  # noqa: BLE001 - la frontera no propaga nada
                aceptado = False
                error = f"{type(exc).__name__}: {exc}"

            with self._lock:
                if aceptado:
                    self._pendientes.popleft()
                    self._ultimo_enviado = comando
                    self._ultimo_error = None
                    transmitidos += 1
                else:
                    self._ultimo_error = error or "envío rechazado"
                    return transmitidos

    def pendientes(self) -> int:
        """Número de comandos en espera; un backlog creciente delata un enlace sano (T15)."""
        with self._lock:
            return len(self._pendientes)

    def ultimo_enviado(self) -> ComandoMovimiento | None:
        """Último comando transmitido con éxito, o ``None`` si no hubo ninguno."""
        with self._lock:
            return self._ultimo_enviado

    def ultimo_error(self) -> str | None:
        """Último fallo de envío registrado, o ``None`` (FR-034)."""
        with self._lock:
            return self._ultimo_error

    def vaciar(self) -> None:
        """Descarta lo pendiente sin transmitirlo.

        Se usa al cerrar el CLI o entre corridas. No toca ``ultimo_enviado``,
        para que la deduplicación siga siendo válida tras un vaciado.
        """
        with self._lock:
            self._pendientes.clear()

    def forzar(self, comando: ComandoMovimiento) -> None:
        """Deja ``comando`` como único pendiente, aunque repita el último enviado.

        **Por qué existe.** El enlace del robot recibe **una orden cada
        ``fotogramas_por_orden`` fotogramas** (12 en la pista, ≈0.4 s): el bucle
        de visión llama a este método en cada turno para mandar la decisión
        vigente, sea o no distinta de la anterior. Con
        ``encolar`` la deduplicación descartaría esa repetición —el robot se
        quedaría con la primera orden y se pararía—, así que aquí se encola
        siempre.

        **Y por qué vacía antes.** Dejar el comando como *único* pendiente hace
        dos cosas a la vez: el robot recibe la decisión **actual** y nunca un
        atraso acumulado si el enlace falló un momento; y cuando la FSM veta el
        movimiento (PARE en curso) el ``DETENER`` no puede salir detrás de una
        corrección rezagada. Durante los 3 s de la parada ningún comando de
        movimiento puede colarse.
        """
        with self._lock:
            self._pendientes.clear()
            self._pendientes.append(comando)
