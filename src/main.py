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
    ClaseSenal,
    ComandoMovimiento,
    EstadoRobot,
    MarcadorVisibilidadPlena,
    Parada,
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


def _iterar_fotogramas(
    fuente: str,
    fps_por_defecto: float,
    max_fotogramas: int | None,
) -> Iterator[tuple[int, float, np.ndarray]]:
    """Itera ``(indice, t_s, imagen)`` desde un video, un directorio o una cámara.

    Las fuentes en vivo usan reloj de pared (``reloj_real``) para que el
    cronómetro T del PARE mida segundos reales; los archivos y directorios usan
    ``indice / fps`` para que la máquina de estados reciba tiempos
    reproducibles (FR-017).
    """
    if _es_fuente_viva(fuente):
        # Un índice es un int; una URL se pasa como texto, sin reinterpretarla.
        objetivo: int | str = int(fuente) if fuente.isdigit() else fuente
        captura = cv2.VideoCapture(objetivo)
        if not captura.isOpened():
            captura.release()
            raise FuenteInvalidaError(f"no se pudo abrir la fuente en vivo: {fuente}")
        fps = float(captura.get(cv2.CAP_PROP_FPS))
        if not np.isfinite(fps) or fps <= 0:
            fps = fps_por_defecto
        try:
            yield from _iterar_captura(captura, fps, max_fotogramas, reloj_real=True)
        finally:
            captura.release()
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

    El bucle de visión solo llama a ``encolar`` (O(1), sin E/S); este hilo hace
    el ``sendall`` bloqueante. Esa separación es lo que garantiza que un enlace
    caído no congele la detección (FR-031, SC-005).

    El hilo es *daemon* y se detiene explícitamente al terminar la corrida; el
    ``esperar`` con timeout evita girar en vacío y permite un apagado rápido.
    """

    def __init__(self, cola: ColaTransporte, transporte: Transporte, intervalo_s: float = 0.005) -> None:
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
        exito, png = cv2.imencode(".png", fotograma)
        if not exito:
            return
        # Antes de pintarlo, para que la tecla de captura guarde justo lo que el
        # operador tiene delante de los ojos.
        self._control.registrar_fotograma(fotograma)
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
) -> MetricasCorrida:
    """Recorre la fuente componiendo pipeline, FSM, control, métricas, transporte
    y —si ``mostrar``— una ventana en vivo con el fotograma anotado."""
    pipeline = PipelineVision(params)
    maquina = MaquinaEstados(params, t_inicial=0.0)
    metricas = MetricasCorrida(corrida_id=corrida_id, fuente=fuente)

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
        for indice, t_s, imagen in _iterar_fotogramas(fuente, params.fps_objetivo, max_fotogramas):
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
                cola.encolar(decision.comando)

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
                anotada = anotar(imagen, resultado, estado, params, decision)
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
