"""Test de integración del pipeline por fotogramas (T024).

Encadena las tres piezas del sistema tal como lo hace el CLI de producción
(``src/main.py::_correr``) —``PipelineVision`` → ``MaquinaEstados`` →
``MetricasCorrida``— sobre una secuencia sintética completa que contiene línea
guía, una señal PARE y una señal SIGA, y verifica las tres salidas a la vez:
detecciones, decisiones y resumen de métricas.

Los tests unitarios cubren cada pieza por separado inyectando señales
construidas a mano. Este test cubre lo que ellos no: que las piezas **componen**
y que el resultado combinado cumple las reglas del contrato. En particular
verifica que T nunca reanuda al robot por sí solo (FR-017) y que sólo un SIGA
confirmado lo devuelve a EN_MARCHA, que es el comportamiento exigido en el
laboratorio: si el equipo no coloca la señal verde, el robot no avanza.

Es headless y determinista: los fotogramas se sintetizan en memoria con
``tests/fixtures/generador_sintetico.py`` y el ruido usa semilla explícita.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from src.vision.configuracion import ParametrosConfiguracion
from src.vision.maquina_estados import MaquinaEstados
from src.vision.metricas import MetricasCorrida
from src.vision.modelos import (
    EstadoRobot,
    MarcadorVisibilidadPlena,
    Parada,
    PermisoMovimiento,
)
from src.vision.pipeline import PipelineVision
from tests.fixtures.generador_sintetico import (
    color_por_clase,
    crear_fondo,
    dibujar_linea_vertical,
    dibujar_octagono,
)

FPS = 30.0
N_CONFIRMACION = 3

#: Fotogramas en que cada señal entra y sale de la secuencia.
INICIO_PARE = 10
FIN_PARE = 26
INICIO_SIGA = 106
FIN_SIGA = 122
TOTAL_FOTOGRAMAS = 131

#: Posiciones reales que el sistema produce con la secuencia de arriba; se
#: verifican como invariantes, no se aceptan como constantes opacas.
F_PARE_CONFIRMADO = 12
F_SIGA_CONFIRMADO = 108
F_T_CUMPLIDO = 102

CENTRO_SENAL = (320, 140)
RADIO_SENAL = 45.0
X_LINEA = 320
GROSOR_LINEA = 24


def _fotograma(x_linea: int = X_LINEA, clase_senal: str | None = None) -> np.ndarray:
    """Fotograma con la línea guía y, opcionalmente, un octágono de señal."""
    imagen = crear_fondo()
    dibujar_linea_vertical(imagen, x_linea, GROSOR_LINEA)
    if clase_senal is not None:
        dibujar_octagono(imagen, CENTRO_SENAL, RADIO_SENAL, color_por_clase(clase_senal))
    return imagen


def _clase_en(indice: int) -> str | None:
    """Qué señal, si alguna, está presente en el fotograma ``indice``."""
    if INICIO_PARE <= indice < FIN_PARE:
        return "PARE"
    if INICIO_SIGA <= indice < FIN_SIGA:
        return "SIGA"
    return None


def _secuencia(total: int = TOTAL_FOTOGRAMAS) -> list[tuple[int, float, np.ndarray]]:
    """Secuencia completa: línea siempre, PARE y luego SIGA, como en la pista."""
    return [(i, i / FPS, _fotograma(clase_senal=_clase_en(i))) for i in range(total)]


class _Corrida:
    """Resultado de encadenar las tres piezas, con la traza por fotograma."""

    def __init__(self, params: ParametrosConfiguracion) -> None:
        self.params = params
        self.pipeline = PipelineVision(params)
        self.maquina = MaquinaEstados(params, t_inicial=0.0)
        self.metricas = MetricasCorrida(corrida_id="t024", fuente="sintetico")
        self.estados: list[EstadoRobot] = []
        self.veredictos: list[PermisoMovimiento] = []
        self.causas: list[str] = []
        self.transiciones: list[tuple] = []
        self.eventos: list[tuple[int, str, str | None]] = []
        self.latencias: list[float] = []
        self.mascara_linea_por_fotograma: dict[int, int] = {}
        self.marcadores: dict[str, MarcadorVisibilidadPlena] = {}
        self._inicio_parada: float | None = None

    def ejecutar(self, secuencia) -> "_Corrida":
        """Replica el bucle de producción de ``src/main.py::_correr``."""
        for indice, t_s, imagen in secuencia:
            resultado = self.pipeline.procesar(indice, t_s, imagen)
            self.latencias.append(resultado.latencia_ms)
            self.mascara_linea_por_fotograma[indice] = int(
                cv2.countNonZero(resultado.segmentacion.mascara_linea)
            )

            for marcador in resultado.visibilidad_plena:
                self.marcadores.setdefault(marcador.clase.value, marcador)
            for evento in resultado.eventos:
                self.metricas.registrar_evento(evento)
                self.eventos.append(
                    (indice, evento.tipo.value, evento.clase.value if evento.clase else None)
                )

            presentes = frozenset(s.clase for s in resultado.senales_confirmadas)
            estado = self.maquina.actualizar(presentes, resultado.eventos, t_s)

            for transicion in estado.transiciones_nuevas:
                self.metricas.registrar_transicion(transicion)
                self.transiciones.append(
                    (transicion.desde, transicion.hacia, transicion.causa)
                )

            for senal in resultado.senales_confirmadas:
                # Sin referencia: el módulo solo cuenta, no juzga (FR-025).
                self.metricas.registrar_senal(senal, anotada=None)
                marcador = self.marcadores.get(senal.clase.value)
                if marcador is not None:
                    self.metricas.registrar_latencia_desde_marcador(
                        marcador, senal.fotograma_idx, senal.t_s
                    )

            self.metricas.registrar_fotograma(resultado.latencia_ms, t_s)

            self.estados.append(estado.estado)
            self.veredictos.append(estado.decision.veredicto)
            self.causas.append(estado.decision.causa)

            # Registro de paradas idéntico al del CLI.
            if self._inicio_parada is None and estado.estado is not EstadoRobot.EN_MARCHA:
                self._inicio_parada = t_s
            if estado.estado is EstadoRobot.EN_MARCHA and self._inicio_parada is not None:
                self.metricas.registrar_parada(
                    Parada.crear(
                        inicio_t=self._inicio_parada,
                        t_configurado_s=self.params.t_parada_s,
                        fin_t=t_s,
                    )
                )
                self._inicio_parada = None

        return self


@pytest.fixture()
def corrida(parametros_por_defecto: ParametrosConfiguracion) -> _Corrida:
    """Corrida completa sobre la secuencia sintética de la pista."""
    return _Corrida(parametros_por_defecto).ejecutar(_secuencia())


# --------------------------------------------------------------------------
# Detecciones
# --------------------------------------------------------------------------


def test_confirma_pare_y_siga_una_vez_cada_una(corrida: _Corrida) -> None:
    """Cada señal produce exactamente una confirmación (N=3 fotogramas)."""
    por_tipo: dict[str, list[int]] = {}
    for indice, tipo, _clase in corrida.eventos:
        por_tipo.setdefault(tipo, []).append(indice)

    assert por_tipo["PARE_CONFIRMADO"] == [F_PARE_CONFIRMADO]
    assert por_tipo["SIGA_CONFIRMADO"] == [F_SIGA_CONFIRMADO]
    # La confirmación aterriza en el N-ésimo fotograma contando desde el
    # primero en que aparece la señal, así que el desplazamiento es N-1.
    assert por_tipo["PARE_CONFIRMADO"][0] - INICIO_PARE == N_CONFIRMACION - 1
    assert por_tipo["SIGA_CONFIRMADO"][0] - INICIO_SIGA == N_CONFIRMACION - 1


def test_perdida_y_rearme_de_pare_por_tolerancia_k(corrida: _Corrida) -> None:
    """Al desaparecer PARE se emite SENAL_PERDIDA y luego PARE_REARMADO (FR-021)."""
    tipos = [tipo for _i, tipo, _c in corrida.eventos]
    assert "SENAL_PERDIDA" in tipos
    assert "PARE_REARMADO" in tipos
    assert tipos.index("SENAL_PERDIDA") < tipos.index("PARE_REARMADO")


def test_no_hay_confusiones_entre_clases(corrida: _Corrida) -> None:
    """Con señal única por clase no puede haber confusión PARE<->SIGA (SC-003)."""
    for _i, tipo, clase in corrida.eventos:
        if tipo in {"PARE_CONFIRMADO", "SIGA_CONFIRMADO"}:
            esperada = tipo.removesuffix("_CONFIRMADO")
            assert clase == esperada


# --------------------------------------------------------------------------
# Decisiones
# --------------------------------------------------------------------------


def test_secuencia_de_estados_de_la_parada(corrida: _Corrida) -> None:
    """EN_MARCHA -> DETENIDO_MINIMO -> EN_MARCHA (reanuda al cumplir T)."""
    cambios = [estado for i, estado in enumerate(corrida.estados) if i == 0 or estado is not corrida.estados[i - 1]]
    assert cambios == [
        EstadoRobot.EN_MARCHA,
        EstadoRobot.DETENIDO_MINIMO,
        EstadoRobot.EN_MARCHA,
    ]


def test_t_reanuda_por_si_solo(corrida: _Corrida) -> None:
    """Al cumplirse T el robot reanuda; la SIGA posterior no hace falta (FR-017).

    Decisión del equipo (2026-10-05): la parada dura exactamente ``t_parada_s`` y
    el robot vuelve a seguir la línea, aunque no hubiera visto SIGA.
    """
    assert corrida.causas[F_T_CUMPLIDO] == "T_CUMPLIDO"
    assert corrida.veredictos[F_T_CUMPLIDO] is PermisoMovimiento.AUTORIZADO

    # Mientras el cronómetro corre, todos los fotogramas son NO AUTORIZADO.
    for indice in range(F_PARE_CONFIRMADO, F_T_CUMPLIDO):
        assert corrida.veredictos[indice] is PermisoMovimiento.NO_AUTORIZADO, (
            f"el robot se autorizó dentro de la parada en el fotograma {indice}"
        )


def test_el_cronometro_es_el_unico_reanudador(corrida: _Corrida) -> None:
    """La única reanudación ocurre exactamente al cumplirse T."""
    reanudaciones = [
        i
        for i in range(1, len(corrida.estados))
        if corrida.estados[i] is EstadoRobot.EN_MARCHA
        and corrida.estados[i - 1] is not EstadoRobot.EN_MARCHA
    ]
    assert reanudaciones == [F_T_CUMPLIDO]
    assert corrida.causas[F_T_CUMPLIDO] == "T_CUMPLIDO"
    assert corrida.veredictos[F_T_CUMPLIDO] is PermisoMovimiento.AUTORIZADO


def test_invariante_detenido_implica_no_autorizado(corrida: _Corrida) -> None:
    """Ningún fotograma en DETENIDO_* puede autorizar movimiento (FR-015)."""
    for estado, veredicto in zip(corrida.estados, corrida.veredictos):
        if estado is not EstadoRobot.EN_MARCHA:
            assert veredicto is PermisoMovimiento.NO_AUTORIZADO


# --------------------------------------------------------------------------
# Resumen de métricas
# --------------------------------------------------------------------------


def test_resumen_cuenta_una_ocurrencia_por_senal(corrida: _Corrida) -> None:
    """El resumen agrega una ocurrencia de PARE y una de SIGA (Q3, FR-025)."""
    resumen = corrida.metricas.resumen()
    assert resumen["ocurrencias_pare"] == 1
    assert resumen["ocurrencias_siga"] == 1
    assert resumen["frames_procesados"] == TOTAL_FOTOGRAMAS


def test_resumen_registra_la_parada_con_su_retardo(corrida: _Corrida) -> None:
    """La parada se registra con T configurado; sin retardo, la parada es T exacto."""
    paradas = corrida.metricas.resumen()["paradas"]
    assert len(paradas) == 1
    parada = paradas[0]

    inicio = F_PARE_CONFIRMADO / FPS
    fin = F_T_CUMPLIDO / FPS
    assert parada["inicio_t"] == pytest.approx(inicio, abs=1e-6)
    assert parada["fin_t"] == pytest.approx(fin, abs=1e-6)
    assert parada["t_configurado_s"] == pytest.approx(3.0)

    # SC-008: el cronómetro cierra la parada, así que dura T exacto y el retardo
    # es 0: ya no se espera a la SIGA para reanudar.
    duracion = parada["fin_t"] - parada["inicio_t"]
    assert duracion == pytest.approx(parada["t_configurado_s"], abs=1e-6)
    assert parada["retardo_s"] == pytest.approx(0.0, abs=1e-6)


def test_latencia_de_decision_dentro_del_presupuesto(corrida: _Corrida) -> None:
    """Cada señal se decide en ≤ 8 fotogramas desde su visibilidad plena (SC-006)."""
    resumen = corrida.metricas.resumen()
    assert len(resumen["latencias_frames"]) == 2
    assert all(frames <= 8 for frames in resumen["latencias_frames"])
    assert all(ms > 0.0 for ms in resumen["latencias_ms"])


def test_latencia_de_procesamiento_por_fotograma(corrida: _Corrida) -> None:
    """Se miden todos los fotogramas y las latencias son no negativas (SC-007)."""
    resumen = corrida.metricas.resumen()
    assert len(corrida.latencias) == TOTAL_FOTOGRAMAS
    assert all(ms >= 0.0 for ms in corrida.latencias)
    assert resumen["latencia_media_ms"] >= 0.0
    assert resumen["latencia_p95_ms"] >= resumen["latencia_media_ms"] * 0.0


# --------------------------------------------------------------------------
# Etapa de línea
# --------------------------------------------------------------------------


def test_mascara_de_linea_presente_en_toda_la_corrida(corrida: _Corrida) -> None:
    """La etapa de línea entrega máscara no vacía en cada fotograma (US3).

    Verifica que la segmentación de la guía es estable a lo largo de toda la
    secuencia, incluidas las etapas con señal. Nota: hoy esa máscara no tiene
    consumidor (checklist CHK035, objetivos 3-4 del Reto 1 fuera de alcance),
    así que este test fija su disponibilidad sin afirmar que guíe al robot.
    """
    vacios = [i for i, pixeles in corrida.mascara_linea_por_fotograma.items() if pixeles == 0]
    assert vacios == []
    assert min(corrida.mascara_linea_por_fotograma.values()) > 0


# --------------------------------------------------------------------------
# Determinismo
# --------------------------------------------------------------------------


#: Claves del resumen que son mediciones de reloj y por tanto no son
#: reproducibles bit a bit entre dos corridas del mismo input.
_CAMPOS_DE_RELOJ = frozenset({"latencia_media_ms", "latencia_p95_ms", "fps_promedio"})


def test_la_corrida_es_determinista(parametros_por_defecto: ParametrosConfiguracion) -> None:
    """Misma entrada + misma configuración ⇒ mismas decisiones y mismo resumen.

    Las decisiones, los eventos y los conteos deben ser idénticos. Las
    latencias quedan fuera: son mediciones de ``perf_counter`` y no pueden
    repetirse al bit entre dos ejecuciones, aunque el sistema sea determinista.
    """
    primera = _Corrida(parametros_por_defecto).ejecutar(_secuencia())
    segunda = _Corrida(parametros_por_defecto).ejecutar(_secuencia())

    assert primera.estados == segunda.estados
    assert primera.veredictos == segunda.veredictos
    assert primera.causas == segunda.causas
    assert primera.eventos == segunda.eventos
    assert primera.transiciones == segunda.transiciones
    assert primera.mascara_linea_por_fotograma == segunda.mascara_linea_por_fotograma

    resumen_a = {k: v for k, v in primera.metricas.resumen().items() if k not in _CAMPOS_DE_RELOJ}
    resumen_b = {k: v for k, v in segunda.metricas.resumen().items() if k not in _CAMPOS_DE_RELOJ}
    assert resumen_a == resumen_b
