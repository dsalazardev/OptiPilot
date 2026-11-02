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
from typing import TYPE_CHECKING

import numpy as np

from .candidatos import ExtractorCandidatos
from .compositor import componer
from .configuracion import ParametrosConfiguracion
from .control_trayectoria import ControlTrayectoria
from .deteccion import Detector
from .localizacion_senales import LocalizadorSenales
from .modelos import (
    CandidatoSenal,
    CausaComando,
    ClaseSenal,
    ClaseSenalExtra,
    ClasificacionCNN,
    ColorRegion,
    ComandoMovimiento,
    DecisionCompuesta,
    DecisionControl,
    DecisionMovimiento,
    EventoSenal,
    MarcadorVisibilidadPlena,
    ModoMarcha,
    PermisoMovimiento,
    PosicionLinea,
    PrediccionSenal,
    RegionSenal,
    ResultadoProcesamiento,
    SenalConfirmada,
    TipoEvento,
)
from .posicion_linea import EstimadorLinea
from .preprocesamiento import Preprocesador, ResultadoPreprocesamiento
from .segmentacion import Segmentador

if TYPE_CHECKING:
    from src.clasificacion.base import ClasificadorSenales

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

    def __init__(
        self,
        params: ParametrosConfiguracion,
        clasificador: "ClasificadorSenales | None" = None,
    ) -> None:
        self._params = params
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
        # Etapa CNN opcional (specs/004): el localizador clásico propone
        # regiones y el clasificador decide la clase. Sin clasificador, el
        # camino clásico de 001 queda intacto.
        self._clasificador = clasificador
        self._localizador = (
            LocalizadorSenales(params) if clasificador is not None else None
        )
        self._extra_clase: ClaseSenalExtra | None = None
        self._extra_conteo = 0
        self._modo_marcha = ModoMarcha.SIGA

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
        clasificaciones_cnn: list[ClasificacionCNN] = []
        rechazadas_cnn = 0
        if self._clasificador is not None:
            candidatos, clasificaciones_cnn, rechazadas_cnn = self._detectar_con_cnn(
                preprocesado, imagen_bgr
            )
        else:
            candidatos = self._extractor_candidatos.extraer(
                mascara_roja=segmentacion.mascara_roja,
                mascara_verde=segmentacion.mascara_verde,
                roi_senales_px=segmentacion.roi_senales,
            )
        deteccion = self._detector.actualizar(
            candidatos,
            indice,
            t_s,
            permitir_rearme=not self._control.rearme_bloqueado,
        )
        for senal in deteccion.senales_confirmadas:
            if senal.clase in (ClaseSenal.PARE, ClaseSenal.SIGA):
                self._modo_marcha = ModoMarcha.SIGA
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
        # El control necesita saber qué señales siguen en pantalla: el cruce no
        # termina mientras su cartel se vea (aunque la línea asome), y tras un
        # PARE la gracia larga cuenta desde la última vez que se vio.
        self._control.observar_senal(deteccion.presentes)

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
            clasificaciones_cnn=clasificaciones_cnn,
            rechazadas_cnn=rechazadas_cnn,
            modo_marcha=self._modo_marcha,
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
        """Reinicia las memorias entre corridas (FR-023).

        Incluye la del estimador (última posición válida, usada para la
        coherencia de trayectoria): entre corridas no debe sobrevivir.
        """
        self._control.reiniciar()
        self._estimador.reiniciar()
        self._extra_clase = None
        self._extra_conteo = 0
        self._modo_marcha = ModoMarcha.SIGA

    def _detectar_con_cnn(
        self,
        pre: ResultadoPreprocesamiento,
        imagen_bgr: np.ndarray,
    ) -> tuple[list[CandidatoSenal], list[ClasificacionCNN], int]:
        """Localiza regiones, las clasifica y construye candidatas PARE/SIGA."""
        if self._localizador is None or self._clasificador is None:
            return [], [], 0

        if imagen_bgr is None or imagen_bgr.ndim != 3 or imagen_bgr.size == 0:
            return [], [], 0

        candidatos: list[CandidatoSenal] = []
        clasificaciones: list[ClasificacionCNN] = []
        rechazadas = 0
        mejor_extra: PrediccionSenal | None = None
        for region in self._localizador.propuestas(pre):
            prediccion = self._clasificador.clasificar(imagen_bgr)
            if prediccion.confianza < self._params.umbral_confianza_senal:
                rechazadas += 1
                continue
            if not self._clase_coherente(region, prediccion):
                rechazadas += 1
                continue
            if prediccion.clase_senal is not None:
                candidatos.append(self._candidato(region, prediccion))
                clasificaciones.append(
                    ClasificacionCNN(
                        prediccion=prediccion,
                        caja_px=region.caja_px,
                        centro_px=region.centro_px,
                    )
                )
            elif prediccion.clase_extra is not None:
                clasificaciones.append(
                    ClasificacionCNN(
                        prediccion=prediccion,
                        caja_px=region.caja_px,
                        centro_px=region.centro_px,
                    )
                )
                if mejor_extra is None or prediccion.confianza > mejor_extra.confianza:
                    mejor_extra = prediccion
            else:
                rechazadas += 1

        if mejor_extra is not None and mejor_extra.clase_extra is not None:
            self._actualizar_extra(mejor_extra.clase_extra)
        else:
            self._reset_extra()
        return candidatos, clasificaciones, rechazadas

    def _clase_coherente(
        self, region: RegionSenal, prediccion: PrediccionSenal
    ) -> bool:
        """La clase de la CNN debe ser coherente con el color y la forma clásicos.

        El color de la máscara restringe la clase posible y el número de vértices
        descarta manchas que no tienen la forma de la señal. Sin esta compuerta,
        una mancha verde grande se clasificaba como SIGA y una zona amarilla
        rectangular como ZONA ESCOLAR en footage sin señales.
        """
        objetivo = self._params.vertices_objetivo
        tolerancia = self._params.tolerancia_vertices
        octagono = abs(region.n_vertices - objetivo) <= tolerancia

        if prediccion.clase_senal is ClaseSenal.PARE:
            return region.color is ColorRegion.ROJO and octagono
        if prediccion.clase_senal is ClaseSenal.SIGA:
            return region.color is ColorRegion.VERDE and octagono
        if prediccion.clase_extra is ClaseSenalExtra.ZONA_ESCOLAR:
            return region.color is ColorRegion.AMARILLO and region.n_vertices >= 5
        if prediccion.clase_extra is ClaseSenalExtra.VELOCIDAD_60:
            return region.color is ColorRegion.ROJO and region.n_vertices >= 6
        return False

    @staticmethod
    def _candidato(region: RegionSenal, prediccion: PrediccionSenal) -> CandidatoSenal:
        clase = prediccion.clase_senal
        if clase is None:
            raise ValueError("un candidato CNN exige una clase PARE/SIGA")
        return CandidatoSenal(
            clase_estimada=clase,
            centro_px=region.centro_px,
            area_px=region.area_px,
            area_rel=region.area_rel,
            n_vertices=region.n_vertices,
            caja_px=region.caja_px,
            aspecto=region.aspecto,
            es_valido=True,
            confianza_cnn=prediccion.confianza,
        )

    def _actualizar_extra(self, clase: ClaseSenalExtra) -> None:
        """Confirma una clase extra tras ``n_confirmacion_extra`` predicciones."""
        if clase is self._extra_clase:
            self._extra_conteo += 1
        else:
            self._extra_clase = clase
            self._extra_conteo = 1
        if self._extra_conteo >= self._params.n_confirmacion_extra:
            self._modo_marcha = self._modo_para_extra(clase)

    def _reset_extra(self) -> None:
        """Rompe la racha de una clase extra; el modo ya confirmado persiste."""
        self._extra_clase = None
        self._extra_conteo = 0

    @staticmethod
    def _modo_para_extra(clase: ClaseSenalExtra) -> ModoMarcha:
        if clase is ClaseSenalExtra.ZONA_ESCOLAR:
            return ModoMarcha.ZONA_ESCOLAR
        return ModoMarcha.VELOCIDAD_60

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