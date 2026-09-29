"""Compositor: arbitraje de seguridad entre la ley de control y la FSM (T025).

Por qué existe este módulo
--------------------------
En cada fotograma, **dos** subsystems quieren decidir el comando del robot:

1. la ley de control de trayectoria, que sigue la línea;
2. la máquina de estados PARE/SIGA, que exige detenerse ante un PARE.

Si ambos tuvieran el mismo rango, un PARE confirmado en el fotograma 812 podría
ser pisado por una corrección de dirección en ese mismo instante, y el robot
**giraría en vez de detenerse**. Eso no es un error de precisión: es un fallo de
seguridad y un «No cumple» directo en el criterio de reconocimiento de PARE de la
rúbrica. Este módulo es el árbitro que hace imposible ese resultado.

La precedencia (contract ``api-control.md`` §3) es de tres niveles y se aplica en
este orden:

====  ==========================================  =========================
Nivel Condición                                   Comando final
====  ==========================================  =========================
1     la FSM no autoriza el movimiento           ``DETENER`` / ``VETO_FSM``
2     el control propone ``DETENER``              ``DETENER`` / su causa
3     cualquier otro caso                        el propuesto / su causa
====  ==========================================  =========================

**Por qué el veto gana, en una frase (para la defensa oral)**: la ley de control
optimiza seguir la pista; la FSM optimiza no atropellar un PARE. Cuando las dos
objetivos entran en conflicto no hay un compromiso razonable, y la única salida
segura es parar.

**La causa es parte del contrato, no decoración**: los tres niveles terminan a
veces en ``DETENER``, y solo la causa distingue «el control perdió la línea» de
«el PARE paró al robot». Sin ella, las métricas y el póster no podrían
demostrar que un PARE se respetó siempre (FR-027, SC-007).

**Sin E/S**: este módulo no abre sockets ni lee nada. ``src/vision/`` es lógica
pura y el enlace Bluetooth vive en ``src/transporte/`` (Constitución §II).

**Nota sobre la firma**: ``contracts/api-control.md`` §3 declaraba
``componer(decision, movimiento)``, que no puede construir el resultado porque
``DecisionCompuesta`` exige además ``posicion`` y ``permitido``. La firma real
recibe las tres entradas; la discrepancia quedó registrada en AGENTS.md §27 y
corregida en el contrato.
"""

from __future__ import annotations

from src.vision.modelos import (
    CausaComando,
    ComandoMovimiento,
    DecisionCompuesta,
    DecisionControl,
    DecisionMovimiento,
    PermisoMovimiento,
    PosicionLinea,
)

__all__ = ["componer"]


def componer(
    decision: DecisionControl,
    movimiento: DecisionMovimiento,
    posicion: PosicionLinea,
) -> DecisionCompuesta:
    """Compone la propuesta del control con el veredicto de la FSM.

    Args:
        decision: propuesta del control de trayectoria para este fotograma.
        movimiento: veredicto de la máquina de estados (tipo de 001, FR-026).
        posicion: posición estimada de la línea, que se propaga sin modificar.

    Returns:
        ``DecisionCompuesta`` con el comando final, su causa, la posición y el
        permiso de la FSM. Nunca lanza: la FSM no autoriza ⟹ ``DETENER``.

    Inmutable y sin estado: la precedencia depende solo de sus tres argumentos,
    de modo que la misma entrada da siempre la misma salida (Q6) y el módulo se
    puede probar entero sin necesidad de fotogramas de vídeo.
    """
    if movimiento.veredicto is PermisoMovimiento.NO_AUTORIZADO:
        # Nivel 1: el veto de la FSM. Gana sobre cualquier propuesta, incluso
        # sobre una que ya fuera `DETENER` (la causa es lo que las distingue).
        return DecisionCompuesta(
            comando=ComandoMovimiento.DETENER,
            causa=CausaComando.VETO_FSM,
            posicion=posicion,
            permitido=movimiento.veredicto,
        )

    # Niveles 2 y 3: la FSM autoriza, así que manda el control. Su comando y su
    # causa se propagan tal cual, sin reinterpretarlos: el compositor arbitra,
    # no decide.
    return DecisionCompuesta(
        comando=decision.comando,
        causa=decision.causa,
        posicion=posicion,
        permitido=movimiento.veredicto,
    )
