"""Orquestador del pipeline de visión por fotograma (T013).

Compone las etapas clásicas en orden: preprocesamiento → segmentación →
candidatos → detección/confirmación. Cada etapa solo usa primitivas autorizadas
de OpenCV y lógica propia; aquí no hay ninguna decisión de detección nueva
(Constitución §I–§II), solo composición, medición de latencia por
``time.perf_counter`` y el marcador de **visibilidad plena** por señal.

El marcador (data-model §12, SC-006) registra el PRIMER fotograma en el que la
señal aparece completamente dentro de la ROI de señales con área ≥ mínima; es
la base temporal de la latencia de decisión y se re-inicia cuando la ocurrencia
se re-arma (cierre de la ocurrencia anterior).

Garantías de contrato (api-pipeline.md):
- determinista: mismas entradas + misma configuración ⇒ misma salida;
- un fotograma vacío/ilegible devuelve un resultado vacío sin excepción
  (FR-014), con máscaras de tamaño 0 y ``latencia_ms`` no negativa;
- el módulo es puro: no captura cámara ni abre archivos.
"""

from __future__ import annotations

import time

import numpy as np

from .candidatos import ExtractorCandidatos
from .compositor import componer
from .configuracion import ParametrosConfiguracion
from .control_trayectoria import ControlTrayectoria
from .deteccion import Detector
from .modelos import (
    CandidatoSenal,
    CausaComando,
    ClaseSenal,
    ComandoMovimiento,
    DecisionCompuesta,
    DecisionControl,
    DecisionMovimiento,
    EventoSenal,
    MarcadorVisibilidadPlena,
    PermisoMovimiento,
    PosicionLinea,
    ResultadoProcesamiento,
    SenalConfirmada,
    TipoEvento,
)
from .posicion_linea import EstimadorLinea
from .preprocesamiento import Preprocesador
from .segmentacion import Segmentador

__all__ = [
    "PipelineVision",
]


def _dentro_de_roi(
    caja_px: tuple[int, int, int, int],
    roi_senales_px: tuple[int, int, int, int],
) -> bool:
    """True si la caja (x, y, w, h) cae por completo dentro de la ROI."""
    x, y, w, h = caja_px
    rx, ry, rw, rh = roi_senales_px
    return bool(x >= rx and y >= ry and x + w <= rx + rw and y + h <= ry + rh)


def _sin_confirmacion_atendida(
    eventos: list[EventoSenal], ocurrencia_id: int
) -> list[EventoSenal]:
    """Quita la re-confirmación de una ocurrencia que ya produjo su acción.

    La etapa de detección puede volver a emitir ``PARE_CONFIRMADO`` o
    ``SIGA_CONFIRMADO`` para la misma ocurrencia si la señal desaparece más de
    ``k_tolerancia`` fotogramas y vuelve a verse durante el cruce. Esa
    re-confirmación **no es una señal nueva**: si llegara a la FSM, volvería a
    detener al robot 3 s sobre la señal que ya está atravesando. Los demás
    eventos de la ocurrencia (``SENAL_PERDIDA``) se conservan para el registro.
    """
    tipos = (TipoEvento.PARE_CONFIRMADO, TipoEvento.SIGA_CONFIRMADO)
    return [
        evento
        for evento in eventos
        if not (evento.tipo in tipos and evento.ocurrencia_id == ocurrencia_id)
    ]


class PipelineVision:
    """Pipeline por fotograma: BGR → segmentación, candidatos y confirmación."""

    def __init__(self, params: ParametrosConfiguracion) -> None:
        self._preprocesador = Preprocesador(params)
        self._segmentador = Segmentador(params)
        self._extractor_candidatos = ExtractorCandidatos(params)
        self._detector = Detector(params)
        # Etapas de control (feature 002): posición de la línea y ley de control.
        # El compositor se aplica en `componer`, porque necesita el veredicto de
        # la FSM, que se actualiza fuera del pipeline.
        self._estimador = EstimadorLinea(params)
        self._control = ControlTrayectoria(params)
        self._area_minima_rel = params.area_minima_rel
        self._visibilidad_plena: dict[ClaseSenal, MarcadorVisibilidadPlena | None] = {
            ClaseSenal.PARE: None,
            ClaseSenal.SIGA: None,
        }

    def procesar(
        self,
        indice: int,
        t_s: float,
        imagen_bgr: np.ndarray,
    ) -> ResultadoProcesamiento:
        """Procesa un fotograma y devuelve el ``ResultadoProcesamiento``.

        La firma pública **no cambia** respecto a 001; los campos nuevos
        (``posicion`` y ``decision_control``) se añadieron con valor por defecto
        al resultado.
        """
        inicio = time.perf_counter()

        preprocesado = self._preprocesador.aplicar(imagen_bgr)
        segmentacion = self._segmentador.aplicar(preprocesado)
        candidatos = self._extractor_candidatos.extraer(
            mascara_roja=segmentacion.mascara_roja,
            mascara_verde=segmentacion.mascara_verde,
            roi_senales_px=segmentacion.roi_senales,
        )
        deteccion = self._detector.actualizar(
            candidatos,
            indice,
            t_s,
            permitir_rearme=not self._control.cruce_activo,
        )
        visibilidad = self._marcar_visibilidad(candidatos, segmentacion.roi_senales, indice, t_s)
        for clase in deteccion.clases_rearmadas:
            self._visibilidad_plena[clase] = None

        # Cruce de señal (feature 003): la primera confirmación de una ocurrencia
        # arma el cruce y pasa al resto del sistema; las re-confirmaciones de una
        # ocurrencia ya atendida se descartan para que la FSM no vuelva a
        # detener al robot por la misma señal física (ver `iniciar_cruce`).
        eventos = list(deteccion.eventos)
        for senal in deteccion.senales_confirmadas:
            if not self._control.iniciar_cruce(senal.clase, senal.ocurrencia_id):
                eventos = _sin_confirmacion_atendida(eventos, senal.ocurrencia_id)

        # Etapas de control: posición lateral → propuesta del control. El
        # estimador tolera máscaras vacías devolviendo una posición inválida
        # (FR-006), así que esto no puede romper un fotograma degradado.
        posicion = self._estimador.aplicar(segmentacion)
        decision_control = self._control.decidir(posicion)

        latencia_ms = (time.perf_counter() - inicio) * 1000.0

        return ResultadoProcesamiento(
            segmentacion=segmentacion,
            candidatos=candidatos,
            senales_confirmadas=list(deteccion.senales_confirmadas),
            eventos=eventos,
            latencia_ms=latencia_ms,
            visibilidad_plena=visibilidad,
            posicion=posicion,
            decision_control=decision_control,
        )

    def componer(
        self,
        resultado: ResultadoProcesamiento,
        movimiento: DecisionMovimiento,
    ) -> DecisionCompuesta:
        """Aplica el compositor de seguridad al resultado y al veredicto de la FSM.

        Es el tercer nivel de la integración ``estimador → control → compositor``:
        recibe lo ya calculado en :meth:`procesar` y el veredicto que produce la
        máquina de estados, y devuelve la ``DecisionCompuesta`` del fotograma.
        Si por algún motivo faltaran la posición o la propuesta del control (un
        resultado construido a mano), cae a ``DETENER`` por ``FALLO_SEGURO`` para
        no operar con datos ausentes.

        **Veto de la FSM: el control no debe contar la parada.** Mientras un PARE
        tiene al robot detenido, la señal tapa la línea; si el control siguiera
        acumulando "línea perdida" durante esos 3 s, al reanudar saldría en
        recuperación —girando— en vez de continuar recto sobre la pista. Por eso
        el veto avisa al control con ``sostener``.
        """
        if movimiento.veredicto is PermisoMovimiento.NO_AUTORIZADO:
            self._control.sostener()
        if resultado.posicion is None or resultado.decision_control is None:
            return componer(
                resultado.decision_control
                or DecisionControl(
                    comando=ComandoMovimiento.DETENER, causa=CausaComando.FALLO_SEGURO
                ),
                movimiento,
                resultado.posicion
                or PosicionLinea(
                    x_px=None,
                    x_norm=None,
                    error_norm=None,
                    ancho_banda_px=0.0,
                    confianza=0.0,
                    valida=False,
                ),
            )
        return componer(resultado.decision_control, movimiento, resultado.posicion)

    def reiniciar_control(self) -> None:
        """Reinicia la memoria del control entre corridas (FR-023)."""
        self._control.reiniciar()

    def _marcar_visibilidad(
        self,
        candidatos: list[CandidatoSenal],
        roi_senales_px: tuple[int, int, int, int],
        indice: int,
        t_s: float,
    ) -> list[MarcadorVisibilidadPlena]:
        """Marca la primera visibilidad plena de cada señal en su ocurrencia."""
        marcadores: list[MarcadorVisibilidadPlena] = []
        for candidato in candidatos:
            if not candidato.es_valido:
                continue
            if not _dentro_de_roi(candidato.caja_px, roi_senales_px):
                continue
            if candidato.area_rel < self._area_minima_rel:
                continue
            clase = candidato.clase_estimada
            if self._visibilidad_plena[clase] is None:
                marcador = MarcadorVisibilidadPlena(clase=clase, fotograma_idx=indice, t_s=t_s)
                self._visibilidad_plena[clase] = marcador
                marcadores.append(marcador)
        return marcadores