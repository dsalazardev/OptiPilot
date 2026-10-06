"""CLI de validación de OptiPilot: corre el pipeline sobre una fuente y deja evidencia.

Es el único punto del proyecto que abre archivos, escribe en disco e imprime.
``src/vision/`` permanece puro (contrato ``api-pipeline.md``: *«src/vision/ es
puro: no captura cámara, no abre archivos, no imprime; el I/O vive en
src/main.py, metricas.exportar() y visualizacion»*).

Uso::

    python -m src.main --fuente <ruta_video|directorio_imagenes|indice_camara|url_droidcam>
                       [--config config/vision.json]
                       [--diagnostico]
                       [--mostrar]
                       [--salida salidas/<corrida>]
                       [--max-fotogramas N]
                       [--anotacion refs.json]

Códigos de salida: ``0`` corrida completada, ``1`` error de ejecución,
``2`` configuración o fuente invalida.

Control manual por teclado (``--mostrar``)
-------------------------------------------
La ventana captura ``<KeyPress>`` y traduce el ``keysym``; el modo activo se
muestra en el título. ``m`` alterna entre ``AUTÓNOMO`` (manda el pipeline de
visión, valor inicial) y ``MANUAL`` (manda el teclado). Las teclas de movimiento
se ignoran en modo automático a propósito: son dos fuentes de verdad y en mitad
de una corrección no debe ganar una tecla suelta.

Las teclas se atienden en el hilo de la ventana y encolan directamente
(``ColaTransporte.encolar`` es O(1), sin E/S), de modo que ni el operador ni el
bucle de visión esperan al enlace ni al dibujado (SC-005, FR-031). El modo
manual existe solo con ``--mostrar``: sin ventana no hay teclado que lo active.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from src.transporte.base import Transporte
from src.transporte.cola import ColaTransporte
from src.transporte.simulado import TransporteSimulado
from src.transporte.spp import TransporteSPP
from src.vision.configuracion import (
    ConfiguracionInvalidaError,
    ParametrosConfiguracion,
    cargar_parametros,
)
from src.vision.maquina_estados import MaquinaEstados
from src.vision.metricas import MetricasControl, MetricasCorrida
from src.vision.modelos import (
    CausaComando,
    ClaseSenal,
    ComandoMovimiento,
    DecisionCompuesta,
    EstadoRobot,
    MarcadorVisibilidadPlena,
    Parada,
    PosicionLinea,
)
from src.vision.pipeline import PipelineVision
from src.vision.visualizacion import anotar

CODIGO_OK = 0
CODIGO_ERROR_EJECUCION = 1
CODIGO_ENTRADA_INVALIDA = 2

_EXTENSIONES_IMAGEN = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"})

class FuenteInvalidaError(ValueError):
    """La fuente de fotogramas no existe, no se puede abrir o está vacía."""

# -- fuente de fotogramas --------------------------------------------------

#: Esquemas que se pasan tal cual a ``cv2.VideoCapture``. DroidCam por WiFi sirve
#: el video del celular como URL —``http://IP:4747/video`` (MJPEG) o
#: ``rtsp://IP:554/...``— y esas rutas no existen en el sistema de archivos.
_ESQUEMAS_EN_VIVO = frozenset({"http", "https", "rtsp", "rtmp"})

#: Rotaciones que se pueden pedir con ``--rotar`` para enderezar la cámara en
#: vivo. El celular se monta **vertical**, pero DroidCam entrega el stream en
#: horizontal (1280x720 medido), así que por defecto se rota 90° en sentido
#: horario para que el ROI —calibrado en vertical— aplique tal cual.
_ROTACIONES: dict[str, int | None] = {
    "horario": cv2.ROTATE_90_CLOCKWISE,
    "antihorario": cv2.ROTATE_90_COUNTERCLOCKWISE,
    "180": cv2.ROTATE_180,
    "ninguna": None,
}

#: Rotación por defecto para las fuentes en vivo.
_ROTACION_POR_DEFECTO = "horario"


def _orientar(imagen: np.ndarray, rotacion: int | None) -> np.ndarray:
    """Endereza la imagen. Con ``rotacion`` nula, la devuelve intacta.

    Solo se aplica a fuentes en vivo: los videos y directorios de prueba ya están
    en la orientación con la que se calibró todo y rotarlos volvería irreducibles
    las pruebas de geometría.
    """
    if rotacion is None:
        return imagen
    return cv2.rotate(imagen, rotacion)


def _es_fuente_viva(fuente: str) -> bool:
    """True si la fuente es una cámara: un índice (``0``) o una URL de red.

    Sin esto, una URL de DroidCam caería en la rama de ``Path`` y el CLI la
    reportaría como «la fuente no existe», aunque la cámara esté sirviendo. Un
    archivo o un directorio existen en disco y nunca llevan esquema, así que la
    distinción es inequívoca en los dos sentidos.
    """
    if fuente.isdigit():
        return True
    esquema = fuente.split("://", 1)[0].lower() if "://" in fuente else ""
    return esquema in _ESQUEMAS_EN_VIVO

def _abrir_video(ruta: Path) -> tuple[cv2.VideoCapture, float]:
    captura = cv2.VideoCapture(str(ruta))
    if not captura.isOpened():
        captura.release()
        raise FuenteInvalidaError(f"no se pudo abrir el video: {ruta}")
    fps = float(captura.get(cv2.CAP_PROP_FPS))
    if not np.isfinite(fps) or fps <= 0:
        fps = 0.0
    return captura, fps


#: Segundos sin recibir un fotograma tras los cuales se da la fuente en vivo por
#: perdida. Un parón más largo que esto (WiFi que se cae, celular que se cierra)
#: no se distingue de un stream terminado, y preferimos cerrar a mostrar una
#: imagen congelada como si fuera real.
_TIMEOUT_SIN_FOTOGRAMA_S = 5.0


class _CapturaUltimo:
    """Entrega SIEMPRE el fotograma más reciente de una cámara en vivo.

    **El problema que resuelve.** Un stream MJPEG por WiFi llega encolado: si el
    bucle de visión consume más lento de lo que la cámara produce, cada segundo
    el atraso crece y el robot acaba decidiendo sobre una imagen de hace varios
    segundos. No es lentitud de cómputo, es *backlog*.

    **La solución.** Un hilo lee sin parar del ``cv2.VideoCapture`` real y
    sobrescribe un único hueco con el último fotograma. El consumidor llama a
    ``read()`` y recibe ese hueco: los fotogramas que quedaron atrás se descartan
    solos, así que el atraso queda acotado a ~1 fotograma en vez de crecer.

    El objeto es un doble de ``cv2.VideoCapture`` para lo que usa ``_iterar_captura``
    (``read``/``release``), de modo que esa función —y su reloj de pared— sigue
    sirviendo sin cambios.
    """

    def __init__(self, captura: cv2.VideoCapture, intervalo_s: float = 0.001) -> None:
        self._captura = captura
        self._intervalo_s = intervalo_s
        self._lock = threading.Lock()
        self._fotograma: np.ndarray | None = None
        self._leidos = 0
        self._consumidos = 0
        self._parar = threading.Event()
        self._hilo = threading.Thread(target=self._bucle, name="camara", daemon=True)
        self._hilo.start()

    def _bucle(self) -> None:
        while not self._parar.is_set():
            try:
                exito, imagen = self._captura.read()
            except Exception:  # noqa: BLE001 - la cámara no debe tumbar el hilo
                time.sleep(self._intervalo_s)
                continue
            if not exito or imagen is None:
                time.sleep(self._intervalo_s)
                continue
            with self._lock:
                self._fotograma = imagen
                self._leidos += 1

    def read(self) -> tuple[bool, np.ndarray | None]:
        """Devuelve el fotograma más reciente, esperando solo si no hay ninguno nuevo.

        Descarta los fotogramas que la cámara produjo mientras el consumidor
        procesaba el anterior: se devuelve el último, no el que siga en la cola.
        """
        limite = time.perf_counter() + _TIMEOUT_SIN_FOTOGRAMA_S
        while time.perf_counter() < limite:
            with self._lock:
                if self._leidos > self._consumidos:
                    self._consumidos = self._leidos
                    return True, self._fotograma
            time.sleep(self._intervalo_s)
        return False, None

    def release(self) -> None:
        """Detiene el hilo lector y libera la captura real."""
        self._parar.set()
        self._hilo.join(timeout=1.0)
        self._captura.release()


def _abrir_captura_viva(objetivo: int | str) -> cv2.VideoCapture | None:
    """Abre una cámara y le pide el búfer mínimo. ``None`` si no se pudo abrir.

    ``CAP_PROP_BUFFERSIZE=1`` es la otra mitad del arreglo del atraso: para una
    fuente en vivo, cada fotograma que el backend guarda por delante es atraso
    puro. No todos los backends lo respetan, pero cuando lo hacen se suma al
    efecto del hilo lector.
    """
    captura = cv2.VideoCapture(objetivo)
    if not captura.isOpened():
        captura.release()
        return None
    constante = getattr(cv2, "CAP_PROP_BUFFERSIZE", None)
    if constante is not None:
        try:
            captura.set(constante, 1)
        except Exception:  # noqa: BLE001 - el backend puede no soportarlo
            pass
    return captura


def _iterar_fotogramas(
    fuente: str,
    fps_por_defecto: float,
    max_fotogramas: int | None,
    rotacion: int | None = None,
) -> Iterator[tuple[int, float, np.ndarray]]:
    """Itera ``(indice, t_s, imagen)`` desde un video, un directorio o una cámara.

    Las fuentes en vivo usan reloj de pared (``reloj_real``) para que el
    cronómetro T del PARE mida segundos reales; los archivos y directorios usan
    ``indice / fps`` para que la máquina de estados reciba tiempos
    reproducibles (FR-017). Las fuentes en vivo se enderezan con ``_orientar``
    según ``rotacion`` para que el ROI calibrado aplique tal cual, y pasan por
    ``_CapturaUltimo`` para no arrastrar atraso de un stream MJPEG.
    """
    if _es_fuente_viva(fuente):
        # Un índice es un int; una URL se pasa como texto, sin reinterpretarla.
        objetivo: int | str = int(fuente) if fuente.isdigit() else fuente
        captura = _abrir_captura_viva(objetivo)
        if captura is None:
            raise FuenteInvalidaError(f"no se pudo abrir la fuente en vivo: {fuente}")
        # El hilo lector descarta los fotogramas atrasados: sin él, un stream
        # MJPEG por WiFi acumula atraso y el robot decide sobre imágenes viejas.
        envuelta = _CapturaUltimo(captura)
        try:
            for indice, t_s, imagen in _iterar_captura(
                envuelta, fps_por_defecto, max_fotogramas, reloj_real=True
            ):
                yield indice, t_s, _orientar(imagen, rotacion)
        finally:
            envuelta.release()
        return

    ruta = Path(fuente)
    if ruta.is_dir():
        yield from _iterar_directorio(ruta, fps_por_defecto, max_fotogramas)
        return
    if not ruta.exists():
        raise FuenteInvalidaError(f"la fuente no existe: {fuente}")

    captura, fps = _abrir_video(ruta)
    if fps <= 0:
        fps = fps_por_defecto
    try:
        yield from _iterar_captura(captura, fps, max_fotogramas)
    finally:
        captura.release()

def _iterar_captura(
    captura: cv2.VideoCapture,
    fps: float,
    max_fotogramas: int | None,
    reloj_real: bool = False,
) -> Iterator[tuple[int, float, np.ndarray]]:
    """Itera los fotogramas de una captura abierta.

    ``reloj_real`` mide el tiempo con ``time.perf_counter()`` en lugar de
    ``indice / fps``. El índice y el fps solo son una aproximación del tiempo
    transcurrido: si la cámara entrega los fotogramas más lento de lo que
    declara —DroidCam por WiFi fluctúa, y el streamer puede ir por detrás de la
    cámara— el cronómetro del PARE (T) se adelantaría o se atrasaría, y el
    robot no se detendría el tiempo que el profesor pidió. Con ``reloj_real``
    la parada dura segundos de verdad.

    Los archivos y directorios siguen con ``indice / fps`` a propósito: sus
    pruebas dependen de tiempos idénticos en cada ejecución (FR-017), y un reloj
    de pared las volvería irreducibles.
    """
    indice = 0
    t_inicio = time.perf_counter()
    while max_fotogramas is None or indice < max_fotogramas:
        exito, imagen = captura.read()
        if not exito or imagen is None:
            return
        t_s = time.perf_counter() - t_inicio if reloj_real else indice / fps
        yield indice, t_s, imagen
        indice += 1

def _iterar_directorio(
    directorio: Path,
    fps: float,
    max_fotogramas: int | None,
) -> Iterator[tuple[int, float, np.ndarray]]:
    rutas = sorted(
        ruta for ruta in directorio.iterdir() if ruta.suffix.lower() in _EXTENSIONES_IMAGEN
    )
    if not rutas:
        raise FuenteInvalidaError(f"el directorio no contiene imágenes: {directorio}")
    for indice, ruta in enumerate(rutas):
        if max_fotogramas is not None and indice >= max_fotogramas:
            return
        imagen = cv2.imread(str(ruta))
        if imagen is None:
            # Un archivo ilegible no aborta la corrida: es degradación controlada.
            print(f"[aviso] fotograma ilegible, se omite: {ruta}", file=sys.stderr)
            continue
        yield indice, indice / fps, imagen

# -- anotación de referencia (opcional) --------------------------------------

class Referencia:
    """Anotación de señales físicas por rango de fotogramas (Q3, FR-025).

    Formato JSON: una lista de ``{"clase": "PARE", "fotograma_inicio": int,
    "fotograma_fin": int}``. Sin este archivo el módulo solo aporta conteos y
    eventos, y las tasas de aceptación las calcula el flujo de análisis.
    """

    def __init__(self, tramos: Sequence[dict]) -> None:
        self._tramos = list(tramos)

    @classmethod
    def vacia(cls) -> "Referencia":
        return cls([])

    @classmethod
    def cargar(cls, ruta: Path) -> "Referencia":
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ConfiguracionInvalidaError("anotacion", str(error)) from error
        if not isinstance(datos, list):
            raise ConfiguracionInvalidaError(
                "anotacion", "se esperaba una lista de tramos"
            )
        return cls(datos)

    @property
    def tiene_tramos(self) -> bool:
        """Si hay anotación de referencia disponible para juzgar las detecciones."""
        return bool(self._tramos)

    def consultar(self, fotograma_idx: int) -> tuple[bool, ClaseSenal | None]:
        """Devuelve ``(anotada, clase_anotada)`` para ese fotograma."""
        for tramo in self._tramos:
            inicio = int(tramo.get("fotograma_inicio", 0))
            fin = int(tramo.get("fotograma_fin", inicio))
            if inicio <= fotograma_idx <= fin:
                return True, ClaseSenal(str(tramo["clase"]).upper())
        return False, None

def _construir_transporte(nombre: str, params: ParametrosConfiguracion) -> Transporte:
    """Crea el transporte pedido por ``--transporte`` (T035).

    ``simulado`` es el valor por defecto para que el CLI funcione sin hardware;
    ``spp`` usa el enlace RFCOMM real. Construir ``TransporteSPP`` **no** abre el
    socket: la conexión es perezosa (se abre en el primer ``enviar``), así que
    arrancar el CLI nunca depende de que el mBot esté encendido.
    """
    if nombre == "simulado":
        return TransporteSimulado()
    if nombre == "spp":
        return TransporteSPP(mac=params.mac_bluetooth, timeout_s=params.timeout_transporte_s)
    raise ConfiguracionInvalidaError("transporte", f"transporte desconocido: {nombre}")


class _BombeoTransporte:
    """Hilo que drena la cola hacia el transporte, fuera del bucle de visión.

    El bucle de visión solo llama a ``forzar`` (O(1), sin E/S); este hilo hace
    el ``sendall`` bloqueante. Esa separación es lo que garantiza que un enlace
    caído no congele la detección (FR-031, SC-005).

    El hilo es *daemon* y se detiene explícitamente al terminar la corrida; el
    ``esperar`` con timeout evita girar en vacío y permite un apagado rápido.
    """

    def __init__(
        self,
        cola: ColaTransporte,
        transporte: Transporte,
        intervalo_s: float = 0.005,
    ) -> None:
        self._cola = cola
        self._transporte = transporte
        self._intervalo_s = intervalo_s
        self._parar = threading.Event()
        self._hilo = threading.Thread(target=self._bucle, name="transporte", daemon=True)

    def iniciar(self) -> None:
        self._hilo.start()

    def detener(self) -> None:
        """Pide al hilo que termine y espera a que lo haga, con un último drenaje."""
        self._parar.set()
        self._hilo.join(timeout=1.0)
        # Un último intento para vaciar lo que quedara pendiente al cerrar.
        self._cola.drenar(self._transporte)

    def _bucle(self) -> None:
        while not self._parar.is_set():
            self._cola.drenar(self._transporte)
            self._parar.wait(self._intervalo_s)


#: Teclas que mueven el robot en modo manual. Los valores son ``keysym`` de
#: tkinter en minúsculas: se comparan contra ``evento.keysym.lower()``, de modo
#: que `w` y `W` caen en la misma entrada sin duplicar el mapa.
_TECLAS_MOVIMIENTO: dict[str, ComandoMovimiento] = {
    "w": ComandoMovimiento.AVANZAR,
    "a": ComandoMovimiento.IZQUIERDA,
    "d": ComandoMovimiento.DERECHA,
    "x": ComandoMovimiento.DETENER,
    "space": ComandoMovimiento.DETENER,
}

#: Tecla que alterna entre modo autónomo y modo manual.
_TECLA_MODO = "m"

#: Teclas que piden terminar la corrida. ``escape`` no tiene equivalente minúsculo
#: pero se incluye para que la comparación sea uniforme.
_TECLAS_CIERRE = frozenset({"q", "escape"})

_MODO_AUTONOMO = "AUTÓNOMO"
_MODO_MANUAL = "MANUAL"
#: Tecla de captura de pantalla. Es una lectura, no una orden: funciona igual en
#: los dos modos y no toca el robot.
_TECLA_CAPTURA = "c"

#: Silencio tolerado en modo manual antes de detener el robot por seguridad.
#: Es un *dead-man switch*: si el operador deja de mandar órdenes —se distrajo,
#: se fue a buscar algo, dejó el teclado a la vista sin vigilarlo— el robot se
#: para solo en lugar de quedarse siguiendo la última. 0.5 s es corto para que
#: el robot no recorra medio metro extra, y largo para no castigar a un operador
#: que está pensando cuál es la siguiente esquina.
_DEADMAN_S = 0.5

#: Granularidad con la que el vigilante despierta para comprobar el silencio. No
#: es la precisión de la parada, solo el margen de retraso con que se detecta: el
#: disparo real ocurre entre 0.5 s y 0.5 s + esta granularidad.
_DEADMAN_MUESTREO_S = 0.05

class _ControlManual:
    """Conmutador auto/manual y traducción de teclas a comandos de movimiento.

    **Quién manda.** En modo ``AUTÓNOMO`` (el inicial) el comando es el que
    compone el pipeline de visión. En modo ``MANUAL`` el comando es el de la
    última tecla pulsada. El bucle de visión consulta ``manual_activo`` en cada
    fotograma para decidir si encola su veredicto; ese es todo el punto de
    acoplamiento entre la ventana y el control.

    **Por qué vive en el hilo de la ventana y no en el de visión.** Los eventos
    de Tk se atienden en el hilo que creó el ``Tk``, y ``ColaTransporte.encolar``
    es O(1) y hace la E/S fuera del lock. Encolar desde el manejador cumple los
    dos requisitos a la vez: el operador no espera al enlace ni al dibujado, y el
    bucle de visión nunca se frena por una tecla (SC-005, FR-031).

    **Entrar en modo manual detiene el robot.** Sin esto el operador heredaría el
    último comando del pipeline («venía corrigiendo a la derecha») y creería que
    tiene el control cuando el robot sigue con la decisión anterior.

    **Dead-man: el silencio también es una orden.** Entregar el control a una
    persona es arriesgado por naturaleza: un modo manual sin vigilancia es un
    robot que sigue la última tecla que alguien pulsó hace diez segundos. En
    cuanto el operador deja de mandar órdenes de movimiento durante
    ``deadman_s`` —se distrajo, se fue a buscar algo, dejó el teclado a la vista
    sin vigilarlo— un vigilante en segundo plano encola ``DETENER``. Solo las
    teclas de movimiento reponen el margen: pulsar ``m`` o cerrar la ventana no
    cuenta como «sigo aquí», porque ninguna de las dos deja al robot en marcha.
    """

    def __init__(
        self,
        cola: ColaTransporte | None,
        deadman_s: float = _DEADMAN_S,
        directorio_capturas: Path | None = None,
    ) -> None:
        self._cola = cola
        self._deadman_s = deadman_s
        self._manual = threading.Event()
        self._cerrar = threading.Event()
        # Estado del dead-man. `_ultima_orden` guarda un reloj monotónico, no el
        # de pared: un ajuste de NTP puede mover el reloj de pared hacia atrás y
        # armar el plazo en el futuro, retrasando la parada justo cuando importa.
        self._ultima_orden = time.monotonic()
        self._parar_vigilante = threading.Event()
        self._vigilante: threading.Thread | None = None
        # Último fotograma que la ventana mostró, para la tecla de captura.
        self._ultimo_fotograma: np.ndarray | None = None
        self._directorio_capturas = (
            directorio_capturas if directorio_capturas is not None else Path("salidas") / "capturas"
        )
        # Último comando que el operador mandó. El visor lo usa en MANUAL para
        # mostrar lo que de verdad se transmite, no lo que el pipeline decidiría.
        self._comando_actual: ComandoMovimiento | None = None

    # -- estado ---------------------------------------------------------

    @property
    def cerrar(self) -> threading.Event:
        """Evento de terminación; lo consume ``_VentanaEnVivo``."""
        return self._cerrar

    @property
    def manual_activo(self) -> bool:
        """True si el operador tiene el control y manda el teclado."""
        return self._manual.is_set()

    @property
    def modo(self) -> str:
        """Etiqueta del modo activo, tal como se muestra en el título."""
        return _MODO_MANUAL if self._manual.is_set() else _MODO_AUTONOMO

    @property
    def comando_actual(self) -> ComandoMovimiento | None:
        """Último comando manual encolado, o ``None`` si aún no hubo ninguno.

        El visor lo consulta en MANUAL para dibujar la orden que el robot está
        recibiendo de verdad; en AUTÓNOMO queda a ``None`` porque el operador no
        manda nada.
        """
        return self._comando_actual

    # -- acciones -------------------------------------------------------

    def pedir_cierre(self) -> None:
        """Pide terminar la corrida. Los motores se detienen en el ``finally``."""
        self._parar_vigilante.set()
        self._cerrar.set()

    def alternar_modo(self) -> str:
        """Conmuta el modo y devuelve la etiqueta nueva."""
        if self._manual.is_set():
            self._manual.clear()
            self._detener_vigilante()
            nuevo = _MODO_AUTONOMO
        else:
            self._manual.set()
            nuevo = _MODO_MANUAL
            # El pipeline sigue calculando y midiendo, pero a partir de aquí no
            # transmite: el robot queda detenido hasta la primera tecla.
            self.enviar(ComandoMovimiento.DETENER)
            self._arrancar_vigilante()
        print(f"[modo] {nuevo}", file=sys.stderr)
        return nuevo

    # -- dead-man --------------------------------------------------------

    def _arrancar_vigilante(self) -> None:
        """Arranca el vigilante del modo manual, si no lo hay vivo.

        Solo existe en modo manual: en autónomo manda el pipeline y el vigilante
        podría detener el robot mientras la visión está corrigiendo, lo que sería
        un fallo de seguridad falso.
        """
        if self._vigilante is not None and self._vigilante.is_alive():
            return
        self._ultima_orden = time.monotonic()
        self._parar_vigilante.clear()
        self._vigilante = threading.Thread(
            target=self._bucle_vigilante, name="deadman", daemon=True
        )
        self._vigilante.start()

    def _detener_vigilante(self) -> None:
        """Termina el vigilante si lo hay vivo y espera a que salga."""
        self._parar_vigilante.set()
        vigilante, self._vigilante = self._vigilante, None
        if vigilante is not None:
            vigilante.join(timeout=1.0)

    def _bucle_vigilante(self) -> None:
        """Detiene el robot si ``deadman_s`` pasan sin orden de movimiento.

        Corre en su propio hilo porque el del bucle de visión puede estar
        bloqueado leyendo de la cámara, que es justo cuando más falta hace que
        el robot se detenga. Nunca lanza: una excepción aquí dejaría el hilo
        mudo y el dead-man desactivado sin que nadie lo note.
        """
        while not self._parar_vigilante.is_set():
            if not self._manual.is_set():
                return
            silencio = time.monotonic() - self._ultima_orden
            restante = self._deadman_s - silencio
            if restante > 0:
                # Espera el tiempo que falta en vez de un intervalo fijo: así el
                # disparo cae en el plazo sin depender del muestreo.
                if self._parar_vigilante.wait(min(restante, _DEADMAN_MUESTREO_S)):
                    return
                continue
            try:
                # Reponer el plazo evita reintentar en bucle. `enviar` deduplica
                # en la cola, así que las repeticiones posteriores no salen por
                # Bluetooth, pero no hace falta ni intentarlo.
                self._ultima_orden = time.monotonic()
                self.enviar(ComandoMovimiento.DETENER)
                print(
                    f"[dead-man] {self._deadman_s:.1f} s sin orden de movimiento: DETENER",
                    file=sys.stderr,
                )
            except Exception as exc:  # pragma: no cover - red de seguridad
                print(f"[dead-man] fallo al detener: {exc}", file=sys.stderr)

    # -- captura de pantalla --------------------------------------------

    def registrar_fotograma(self, fotograma: np.ndarray) -> None:
        """Guarda el fotograma que la ventana está mostrando.

        Lo llama ``_VentanaTkinter.dibujar`` justo antes de pintarlo. No hace
        falta candado porque ``dibujar`` y el manejador de teclas corren en el
        mismo hilo: el fotograma que se guarda es exactamente el que el operador
        ve cuando pulsa la tecla, no el que llega después.
        """
        self._ultimo_fotograma = fotograma

    def capturar_fotograma(self) -> str:
        """Guarda el fotograma actual en disco y devuelve la ruta.

        Sirve para dejar constancia de un estado concreto del robot —el momento
        en que la línea se perdió, en que aparece una señal, en que el operador
        toma el control— sin tener que reconstruirlo después desde el video.

        El nombre lleva marca de tiempo para que las capturas se ordenen solas.
        Dos capturas dentro del mismo segundo comparten nombre y la segunda
        sobrescribe a la primera; a velocidad de dedo humano es improbable, y
        prefiero un nombre limpio antes que un sufijo que hay que explicar.
        """
        fotograma = self._ultimo_fotograma
        if fotograma is None:
            return "sin fotograma que capturar todavía"
        self._directorio_capturas.mkdir(parents=True, exist_ok=True)
        nombre = f"captura_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        ruta = self._directorio_capturas / nombre
        if not cv2.imwrite(str(ruta), fotograma):
            return f"no se pudo escribir {ruta.as_posix()}"
        # `as_posix` para que el mensaje sea el mismo en Windows y en Linux; la
        # rúbrica y el póster citan rutas con `/`.
        print(f"[Captura guardada en {ruta.as_posix()}]", file=sys.stderr)
        return f"captura guardada en {ruta.as_posix()}"

    def enviar(self, comando: ComandoMovimiento) -> bool:
        """Encola un comando manual. Sin cola (pruebas) es una no-op."""
        self._comando_actual = comando
        if self._cola is None:
            return False
        return self._cola.encolar(comando)

    def interpretar(self, keysym: str) -> str | None:
        """Traduce una tecla a la acción correspondiente.

        Devuelve una descripción de lo hecho (para depurar por consola) o
        ``None`` si la tecla no está mapeada. Nunca lanza: un manejador de
        eventos que propaga excepciones rompe la ventana.
        """
        if not keysym:
            return None
        tecla = keysym.lower()

        if tecla in _TECLAS_CIERRE:
            self.pedir_cierre()
            return "cerrar"

        if tecla == _TECLA_MODO:
            return f"modo {self.alternar_modo()}"

        if tecla == _TECLA_CAPTURA:
            # Va antes del mapa de movimiento a propósito: capturar no es mover,
            # así que no debe reponer el margen del dead-man. Guardar una prueba
            # mientras el robot roda no cuenta como «sigo vigilando».
            return self.capturar_fotograma()

        comando = _TECLAS_MOVIMIENTO.get(tecla)
        if comando is None:
            return None
        if not self._manual.is_set():
            # Ignorar en vez de transmitir evita dos fuentes de verdad: en modo
            # autónomo el pipeline manda, y una tecla suelta no debe pelearse
            # con él a mitad de una corrección.
            return f"{comando.name} ignorado (modo {_MODO_AUTONOMO})"

        # Solo las órdenes de movimiento reponen el margen del dead-man. Parar
        # con `x` tampoco lo repone: el robot ya está detenido, así que un
        # disparo posterior del vigilante sería un `DETENER` redundante que la
        # cola deduplica igual.
        self._ultima_orden = time.monotonic()
        self.enviar(comando)
        return comando.name

#: Alto máximo del visor en píxeles. La imagen vertical (720x1280 tras rotar) no
#: cabe en una pantalla de 1080p junto a la barra de título, así que se reduce
#: SOLO para mostrarla: el pipeline y la captura usan la resolución completa.
_ALTO_MAX_VENTANA = 900


def _encajar_en_ventana(imagen: np.ndarray) -> np.ndarray:
    """Reduce la imagen para que quepa en pantalla. No toca la original."""
    alto = imagen.shape[0]
    if alto <= _ALTO_MAX_VENTANA:
        return imagen
    escala = _ALTO_MAX_VENTANA / alto
    ancho = max(1, int(imagen.shape[1] * escala))
    return cv2.resize(imagen, (ancho, _ALTO_MAX_VENTANA), interpolation=cv2.INTER_AREA)


class _VentanaTkinter:
    """Ventana tkinter que dibuja el último fotograma anotado.

    tkinter es biblioteca estándar y funciona con la compilación
    ``opencv-python-headless`` (que no trae ventanas propias). Todos los objetos
    Tk viven en el hilo de ``_VentanaEnVivo``; ``dibujar`` reemplaza la imagen y
    bombea los eventos para mantener la ventana viva y atendiendo al cierre.

    **Una sola captura, genérica.** Se enlaza ``<KeyPress>`` en vez de una tecla
    por binding: ``evento.keysym`` trae el carácter ya resuelto, así que un
    ``<KeyPress-w>`` no dispara con `W` y habría que duplicar cada mapa. Además
    ``space`` y ``escape`` no son teclas de carácter y no se podrían expresar con
    esa sintaxis.
    """

    def __init__(self, nombre: str, control: "_ControlManual") -> None:
        import tkinter as tk

        self._tk = tk
        self._control = control
        self._nombre = nombre
        self._raiz = tk.Tk()
        self._raiz.title(self._titulo())
        self._raiz.protocol("WM_DELETE_WINDOW", control.pedir_cierre)
        self._raiz.bind("<KeyPress>", self._al_presionar)
        self._etiqueta = tk.Label(self._raiz)
        self._etiqueta.pack()
        self._imagen = None
        # Sin foco la ventana no recibe teclas hasta que se la cliqueza, y en una
        # prueba frente al profesor eso se lee como "el teclado no funciona".
        try:
            self._raiz.focus_force()
        except tk.TclError:
            pass

    def _titulo(self) -> str:
        return f"{self._nombre}  [{self._control.modo}]"

    def _al_presionar(self, evento) -> None:
        """Traduce la tecla y refresca el título con el modo vigente."""
        descripcion = self._control.interpretar(str(evento.keysym))
        if descripcion is not None:
            print(f"[tecla] {evento.keysym}: {descripcion}", file=sys.stderr)
        # El modo puede haber cambiado con `m`, así que el título se recalcula en
        # cada pulsación: es una operación trivial frente a dibujar un fotograma.
        self._raiz.title(self._titulo())

    def dibujar(self, fotograma: np.ndarray) -> None:
        # Se registra a resolución completa: la captura con `c` debe guardar la
        # imagen real, no la reducida para la pantalla.
        self._control.registrar_fotograma(fotograma)
        visible = _encajar_en_ventana(fotograma)
        exito, png = cv2.imencode(".png", visible)
        if not exito:
            return
        self._imagen = self._tk.PhotoImage(master=self._raiz, data=png.tobytes())
        self._etiqueta.configure(image=self._imagen)
        self._raiz.update()

    def cerrar(self) -> None:
        self._raiz.destroy()

class _VentanaEnVivo:
    """Muestra el último fotograma anotado en una ventana, en su propio hilo.

    El bucle de visión solo llama a ``publicar`` (O(1), sin dibujar); el hilo
    de la ventana dibuja el último fotograma recibido y descarta los que
    lleguen mientras está ocupado, de modo que la ventana nunca frena la
    detección (FR-031, SC-005). Cerrar la ventana, pulsar ``q``/``Q``/``Escape``
    pide terminar la corrida. ``renderizador`` permite inyectar un doble de
    prueba sin abrir ventanas reales.

    **Es también el dueño de ``_ControlManual``** porque el modo manual se
    alcanza por teclado, y sin ventana no hay teclado: el modo manual existe
    únicamente con ``--mostrar``. El bucle de visión lee ``manual_activo`` para
    saber si encolar su veredicto o dejarlo en manos del operador.
    """

    def __init__(
        self,
        nombre: str = "OptiPilot",
        cola: ColaTransporte | None = None,
        renderizador: Callable[..., object] | None = None,
        intervalo_s: float = 0.01,
    ) -> None:
        self._nombre = nombre
        self._control = _ControlManual(cola)
        self._renderizador = renderizador if renderizador is not None else _VentanaTkinter
        self._intervalo_s = intervalo_s
        self._lock = threading.Lock()
        self._fotograma: np.ndarray | None = None
        self._nuevo = threading.Event()
        self._error: str | None = None
        self._hilo = threading.Thread(target=self._bucle_ventana, name="ventana", daemon=True)

    def iniciar(self) -> None:
        self._hilo.start()

    @property
    def control(self) -> _ControlManual:
        """Control manual compartido; lo usan la ventana y el bucle de visión."""
        return self._control

    @property
    def manual_activo(self) -> bool:
        """True si el operador maneja el robot con el teclado."""
        return self._control.manual_activo

    @property
    def cierre_pedido(self) -> bool:
        """True si el usuario cerró la ventana; no aplica si la ventana falló."""
        return self._control.cerrar.is_set() and self._error is None

    @property
    def error(self) -> str | None:
        """Mensaje del fallo del renderizador, si la ventana no pudo abrirse."""
        return self._error

    def publicar(self, fotograma: np.ndarray) -> None:
        """Deja el fotograma más reciente para el hilo de la ventana."""
        with self._lock:
            self._fotograma = fotograma
        self._nuevo.set()

    def detener(self) -> None:
        """Pide terminar al hilo de la ventana y espera su cierre."""
        self._control.pedir_cierre()
        self._hilo.join(timeout=2.0)

    def _tomar(self) -> np.ndarray | None:
        with self._lock:
            fotograma = self._fotograma
            self._fotograma = None
        return fotograma

    def _bucle_ventana(self) -> None:
        ventana = None
        try:
            ventana = self._renderizador(self._nombre, self._control)
            while not self._control.cerrar.is_set():
                if not self._nuevo.wait(self._intervalo_s):
                    continue
                self._nuevo.clear()
                fotograma = self._tomar()
                if fotograma is not None:
                    ventana.dibujar(fotograma)
        except Exception as error:
            self._error = str(error)
            self._control.pedir_cierre()
        finally:
            if ventana is not None:
                try:
                    ventana.cerrar()
                except Exception:
                    pass

# -- corrida ---------------------------------------------------------------

def _resolver_salida(salida: str | None) -> tuple[Path, str]:
    """Devuelve ``(directorio, corrida_id)``; sin ``--salida`` usa marca de tiempo."""
    if salida:
        directorio = Path(salida)
        return directorio, directorio.name or "corrida"
    corrida_id = "corrida_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("salidas") / corrida_id, corrida_id

def _resumen_consola(resumen: dict) -> str:
    lineas = [
        "=== Resumen de corrida ===",
        f"corrida_id          : {resumen['corrida_id']}",
        f"fuente              : {resumen['fuente']}",
        f"fotogramas          : {resumen['frames_procesados']}",
        f"ocurrencias PARE    : {resumen['ocurrencias_pare']}",
        f"ocurrencias SIGA    : {resumen['ocurrencias_siga']}",
        f"detecciones correctas: {resumen['detecciones_correctas']}",
        f"falsos positivos    : {resumen['falsos_positivos']}",
        f"confusiones         : {resumen['confusiones']}",
        f"paradas             : {len(resumen['paradas'])}",
    ]
    for indice, parada in enumerate(resumen["paradas"], start=1):
        lineas.append(
            f"  parada {indice}: inicio={parada['inicio_t']:.2f}s "
            f"T={parada['t_configurado_s']:.2f}s fin={parada['fin_t']:.2f}s "
            f"retardo={parada['retardo_s']:.2f}s"
        )
    latencias = resumen["latencias_frames"]
    lineas.append(
        f"latencia decision   : {latencias if latencias else 'sin datos'} (fotogramas)"
    )
    lineas.append(f"fps promedio        : {resumen['fps_promedio']:.2f}")
    lineas.append(
        f"latencia proc.      : media={resumen['latencia_media_ms']:.2f} ms "
        f"p95={resumen['latencia_p95_ms']:.2f} ms"
    )
    return "\n".join(lineas)

def _resumen_control_consola(resumen: dict) -> str:
    """Resumen del control de trayectoria para la consola (T032/T035)."""
    por_comando = resumen["fotogramas_por_comando"]
    return "\n".join(
        [
            "=== Resumen de control ===",
            f"correcciones        : {resumen['correcciones']}",
            "fotogramas por cmd  : "
            + " ".join(f"{clave}={valor}" for clave, valor in por_comando.items()),
            f"perdidas de linea   : {resumen['perdidas_linea']}",
            f"recuperaciones ok   : {resumen['recuperaciones_ok']}",
            f"recuperaciones fall.: {resumen['recuperaciones_fallidas']}",
            f"velocidad error px  : media={resumen['velocidad_error_px_media']:.2f} "
            f"p95={resumen['velocidad_error_px_p95']:.2f}",
            f"latencia decision   : media={resumen['latencia_decision_ms_media']:.2f} ms "
            f"p95={resumen['latencia_decision_ms_p95']:.2f} ms",
        ]
    )

#: Desviación (por encima de la zona muerta) a partir de la cual la corrección
#: gira en TODOS los turnos. Por debajo, se gira en turnos alternos.
_BANDA_GIRO_FUERTE = 0.15


def _intensidad_de_turno(
    decision: DecisionCompuesta,
    posicion: PosicionLinea | None,
    params: ParametrosConfiguracion,
    turno: int,
) -> ComandoMovimiento:
    """Modula la fuerza de la corrección en el turno que toca transmitir.

    La ley de control decide **hacia dónde** corregir. Con la cadencia de la
    pista —una orden cada ``fotogramas_por_orden``—, girar en TODOS los turnos
    mientras la desviación persiste es lo que hacía girar de más al robot: cada
    orden es una acción completa y encadenarlas equivale a un giro continuo.

    Aquí una desviación **moderada** se corrige en turnos alternos (giro, avance,
    giro, avance), de modo que el robot vuelve a medir la línea entre giro y
    giro y se reubica en vez de barrer. Solo una desviación **grande** gira en
    todos los turnos, que es cuando hace falta corregir de verdad.
    """
    comando = decision.comando
    if comando is not ComandoMovimiento.IZQUIERDA and comando is not ComandoMovimiento.DERECHA:
        return comando
    if posicion is None or not posicion.valida or posicion.error_norm is None:
        return comando
    if abs(posicion.error_norm) >= params.zona_muerta + _BANDA_GIRO_FUERTE:
        return comando
    return comando if turno % 2 == 0 else ComandoMovimiento.AVANZAR


def _correr(
    params: ParametrosConfiguracion,
    fuente: str,
    diagnostico: bool,
    directorio: Path,
    corrida_id: str,
    max_fotogramas: int | None,
    referencia: Referencia,
    cola: ColaTransporte,
    transporte: Transporte,
    metricas_control: MetricasControl,
    mostrar: bool = False,
    rotacion: int | None = None,
) -> MetricasCorrida:
    """Recorre la fuente componiendo pipeline, FSM, control, métricas, transporte
    y —si ``mostrar``— una ventana en vivo con el fotograma anotado."""
    pipeline = PipelineVision(params)
    maquina = MaquinaEstados(params, t_inicial=0.0)
    metricas = MetricasCorrida(corrida_id=corrida_id, fuente=fuente)
    #: Una orden cada ``fotogramas_por_orden``: el enlace del robot no admite más.
    cadencia = max(1, params.fotogramas_por_orden)
    #: Última orden que salió de verdad hacia el robot. El visor dibuja esta y no
    #: la propuesta del control, porque con la cadencia y la modulación de
    #: intensidad pueden no coincidir en el mismo fotograma.
    ultima_orden = None

    bombeo = _BombeoTransporte(cola, transporte)
    bombeo.iniciar()

    vista = _VentanaEnVivo(cola=cola) if mostrar else None
    if vista is not None:
        vista.iniciar()

    frames = None
    if diagnostico:
        frames = directorio / "frames"
        frames.mkdir(parents=True, exist_ok=True)

    marcadores: dict[ClaseSenal, MarcadorVisibilidadPlena] = {}
    inicio_parada: float | None = None

    try:
        for indice, t_s, imagen in _iterar_fotogramas(
            fuente, params.fps_objetivo, max_fotogramas, rotacion
        ):
            t_inicio_fotograma = time.perf_counter()
            resultado = pipeline.procesar(indice, t_s, imagen)

            for marcador in resultado.visibilidad_plena:
                marcadores.setdefault(marcador.clase, marcador)

            for evento in resultado.eventos:
                metricas.registrar_evento(evento)

            presentes = frozenset(senal.clase for senal in resultado.senales_confirmadas)
            estado = maquina.actualizar(presentes, resultado.eventos, t_s)

            for transicion in estado.transiciones_nuevas:
                metricas.registrar_transicion(transicion)

            for senal in resultado.senales_confirmadas:
                if referencia.tiene_tramos:
                    anotada, clase_anotada = referencia.consultar(senal.fotograma_idx)
                else:
                    # Sin referencia el módulo solo cuenta ocurrencias y no juzga acierto.
                    anotada, clase_anotada = None, None
                metricas.registrar_senal(
                    senal,
                    anotada=anotada,
                    clase_anotada=clase_anotada,
                )
                marcador = marcadores.get(senal.clase)
                if marcador is not None:
                    metricas.registrar_latencia_desde_marcador(
                        marcador, senal.fotograma_idx, senal.t_s
                    )

            metricas.registrar_fotograma(resultado.latencia_ms, t_s)

            # Control de trayectoria (feature 002): estimar → decidir → componer
            # con el veredicto de la FSM, y encolar el comando final. El bucle
            # NUNCA drena: eso lo hace el hilo de transporte (SC-005).
            decision = pipeline.componer(resultado, estado.decision)
            latencia_decision_ms = (time.perf_counter() - t_inicio_fotograma) * 1000.0
            metricas_control.registrar(decision, latencia_decision_ms)
            # El veredicto del pipeline se calcula y se mide siempre, también en
            # modo manual: es lo que permite comparar en la demo qué haría el
            # automático frente a lo que está haciendo el operador. Lo que se
            # suspende es solo la transmisión, no la observación.
            if vista is None or not vista.manual_activo:
                if decision.causa is CausaComando.VETO_FSM:
                    # PARE en curso: el DETENER gana y sale de inmediato, sin
                    # esperar el turno de la cadencia, y descarta cualquier
                    # movimiento que hubiera quedado pendiente.
                    ultima_orden = decision.comando
                    cola.forzar(ultima_orden)
                elif indice % cadencia == 0:
                    # Una sola orden por turno de la cadencia. `forzar` reemplaza
                    # lo pendiente en vez de acumularlo: el robot recibe siempre
                    # la decisión actual, nunca un atraso.
                    ultima_orden = _intensidad_de_turno(
                        decision, resultado.posicion, params, indice // cadencia
                    )
                    cola.forzar(ultima_orden)

            if inicio_parada is None and estado.estado is not EstadoRobot.EN_MARCHA:
                inicio_parada = t_s
            if estado.estado is EstadoRobot.EN_MARCHA and inicio_parada is not None:
                metricas.registrar_parada(
                    Parada.crear(
                        inicio_t=inicio_parada,
                        t_configurado_s=params.t_parada_s,
                        fin_t=t_s,
                    )
                )
                inicio_parada = None

            if frames is not None or vista is not None:
                manual = vista is not None and vista.manual_activo
                # En MANUAL el visor debe mostrar lo que el operador está
                # mandando, no lo que el pipeline habría mandado: si no, la
                # ventana mentiría justo cuando el operador cree tener el control.
                comando_mostrado = (
                    vista.control.comando_actual
                    if manual
                    else (ultima_orden or decision.comando)
                )
                anotada = anotar(
                    imagen,
                    resultado,
                    estado,
                    params,
                    decision,
                    comando_mostrado=comando_mostrado,
                    modo=_MODO_MANUAL if manual else _MODO_AUTONOMO,
                )
                if frames is not None:
                    cv2.imwrite(str(frames / f"frame_{indice:06d}.png"), anotada)
                if vista is not None:
                    vista.publicar(anotada)

            if vista is not None and vista.cierre_pedido:
                break
    except KeyboardInterrupt:
        # Ctrl+C es una parada voluntaria del operador, no un fallo del sistema:
        # se abandona el bucle y se devuelven las métricas acumuladas para que
        # `main` las exporte. Sin esto, `metricas.exportar()` nunca se alcanzaba
        # y una corrida de laboratorio terminaba sin resumen.
        print(
            "[aviso] interrumpido por el operador (Ctrl+C); se guardan las metricas",
            file=sys.stderr,
        )
    finally:
        # Parada de seguridad. El robot no puede quedarse ejecutando el último
        # comando (por ejemplo IZQUIERDA) cuando el operador cierra la ventana,
        # pulsa `q` o interrumpe la corrida: seguiría girando hasta que lo
        # apaguen a mano. Se encola ANTES de detener el bombeo para que el hilo
        # de transporte todavía lo envíe; `bombeo.detener()` hace además un
        # último drenaje.
        cola.encolar(ComandoMovimiento.DETENER)
        bombeo.detener()
        if vista is not None:
            vista.detener()
            if vista.error is not None:
                print(f"[aviso] ventana en vivo: {vista.error}", file=sys.stderr)

    return metricas

def _parsear_args(argv: Sequence[str] | None) -> argparse.Namespace:
    analizador = argparse.ArgumentParser(
        prog="python -m src.main",
        description="CLI de validación de OptiPilot (visión clásica, sin IA entrenada).",
    )
    analizador.add_argument(
        "--fuente",
        required=True,
        help=(
            "ruta de video, directorio de imágenes, índice de cámara (0) "
            "o URL de red de DroidCam (http://IP:4747/video, rtsp://IP:554/...)"
        ),
    )
    analizador.add_argument(
        "--config",
        default="config/vision.json",
        help="ruta del JSON de configuración (por defecto: config/vision.json)",
    )
    analizador.add_argument(
        "--diagnostico",
        action="store_true",
        help="escribe fotogramas anotados por etapa (SC-012)",
    )
    analizador.add_argument(
        "--mostrar",
        action="store_true",
        help=(
            "muestra la imagen anotada en vivo y activa el control por teclado. "
            "En modo AUTÓNOMO manda el pipeline; con 'm' se pasa a MANUAL, donde "
            "'w' avanza, 'a'/'d' corrigen, 'x' o espacio detienen, y "
            "'q'/'Q'/Escape terminan la corrida. 'c' guarda el fotograma actual "
            "en salidas/capturas/"
        ),
    )
    analizador.add_argument(
        "--salida",
        default=None,
        help="directorio de salida; por defecto salidas/<corrida_id>",
    )
    analizador.add_argument(
        "--max-fotogramas",
        type=int,
        default=None,
        help="procesa como máximo N fotogramas",
    )
    analizador.add_argument(
        "--anotacion",
        default=None,
        help="JSON de referencia para confrontar detecciones (opcional, FR-025)",
    )
    analizador.add_argument(
        "--transporte",
        choices=("simulado", "spp"),
        default="simulado",
        help="transporte hacia el robot: 'simulado' (por defecto, sin hardware) o 'spp' (RFCOMM real)",
    )
    analizador.add_argument(
        "--rotar",
        choices=tuple(_ROTACIONES),
        default=_ROTACION_POR_DEFECTO,
        help=(
            "orientación de la cámara EN VIVO: 'horario' (por defecto), "
            "'antihorario', '180' o 'ninguna'. Sirve para el celular montado "
            "vertical cuando DroidCam entrega la imagen horizontal. No afecta a "
            "videos ni a directorios."
        ),
    )
    return analizador.parse_args(argv)

def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada del CLI; devuelve el código de salida del contrato."""
    args = _parsear_args(argv)

    try:
        params = cargar_parametros(Path(args.config) if args.config else None)
    except ConfiguracionInvalidaError as error:
        print(f"[error] configuracion invalida: {error}", file=sys.stderr)
        return CODIGO_ENTRADA_INVALIDA

    referencia = Referencia.vacia()
    if args.anotacion:
        try:
            referencia = Referencia.cargar(Path(args.anotacion))
        except ConfiguracionInvalidaError as error:
            print(f"[error] {error}", file=sys.stderr)
            return CODIGO_ENTRADA_INVALIDA

    directorio, corrida_id = _resolver_salida(args.salida)

    try:
        transporte = _construir_transporte(args.transporte, params)
    except ConfiguracionInvalidaError as error:
        print(f"[error] {error}", file=sys.stderr)
        return CODIGO_ENTRADA_INVALIDA

    cola = ColaTransporte()
    metricas_control = MetricasControl()

    try:
        metricas = _correr(
            params=params,
            fuente=args.fuente,
            diagnostico=args.diagnostico,
            directorio=directorio,
            corrida_id=corrida_id,
            max_fotogramas=args.max_fotogramas,
            referencia=referencia,
            cola=cola,
            transporte=transporte,
            metricas_control=metricas_control,
            mostrar=args.mostrar,
            rotacion=_ROTACIONES[args.rotar],
        )
    except FuenteInvalidaError as error:
        print(f"[error] fuente invalida: {error}", file=sys.stderr)
        return CODIGO_ENTRADA_INVALIDA
    except ConfiguracionInvalidaError as error:
        print(f"[error] configuracion invalida: {error}", file=sys.stderr)
        return CODIGO_ENTRADA_INVALIDA
    finally:
        transporte.cerrar()

    try:
        ruta_eventos, ruta_metricas = metricas.exportar(directorio)
        ruta_control = directorio / "metricas_control.json"
        with ruta_control.open("w", encoding="utf-8") as archivo:
            json.dump(metricas_control.resumen(), archivo, ensure_ascii=False, indent=2)
            archivo.write("\n")
    except OSError as error:
        print(f"[error] no se pudieron escribir los artefactos: {error}", file=sys.stderr)
        return CODIGO_ERROR_EJECUCION

    print(_resumen_consola(metricas.resumen()))
    if cola.ultimo_error() is not None:
        print(f"[aviso] transporte: {cola.ultimo_error()}", file=sys.stderr)
    print(_resumen_control_consola(metricas_control.resumen()))
    print(f"eventos  : {ruta_eventos}")
    print(f"metricas  : {ruta_metricas}")
    print(f"control   : {ruta_control}")
    return CODIGO_OK

if __name__ == "__main__":
    sys.exit(main())
