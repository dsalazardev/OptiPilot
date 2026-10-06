"""Test de integración del CLI en modo demostración (T026).

Invoca el CLI real (``src.main:main`` y, en un caso, ``python -m src.main``)
contra un directorio de fotogramas sintéticos y verifica el contrato de salida:
código de retorno, artefactos escritos y contenido de los métricas.

No hace falta footage real: el CLI acepta un directorio de imágenes
(``_iterar_directorio``), que es la vía offline del módulo. El footage de pista
entra por T027.

Contrato verificado aquí (``src/main.py``):
  * ``--fuente``    : video | directorio de imágenes | índice de cámara
  * ``--config``    : JSON de configuración (por defecto ``config/vision.json``)
  * ``--salida``    : directorio de artefactos (por defecto ``salidas/<id>``)
  * ``--diagnostico``: escribe ``frames/frame_<idx>.png`` anotados (SC-012)
  * ``--max-fotogramas`` y ``--anotacion`` (FR-025)
  * salidas: 0 OK, 1 error de ejecución, 2 entrada inválida
  * artefactos: ``eventos.jsonl`` y ``metricas.json``
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Sequence

import cv2
import pytest

from src.main import (
    CODIGO_ENTRADA_INVALIDA,
    CODIGO_ERROR_EJECUCION,
    CODIGO_OK,
    main,
)
from tests.integration._escenarios import fotograma_con, tramos_a_clases

RAIZ = Path(__file__).resolve().parents[2]
CONFIG_PROYECTO = RAIZ / "config" / "vision.json"

#: Fotogramas del guion largo: PARE 10-25, SIGA 106-121 (misma secuencia que T024).
GUION_LARGO = [(10, 26, "PARE"), (106, 122, "SIGA")]
TOTAL_LARGO = 131
F_PARE_CONFIRMADO = 12
F_SIGA_CONFIRMADO = 108
#: El cronómetro T=3,0 s se cumple 90 fotogramas después del PARE confirmado.
F_T_CUMPLIDO = 102


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------


def escribir_secuencia(
    directorio: Path,
    guion: Sequence[tuple[int, int, str | list[str]]],
    total: int,
) -> Path:
    """Vuelca el guion como PNGs numerados; devuelve el directorio fuente."""
    directorio.mkdir(parents=True, exist_ok=True)
    clases_por_fotograma = tramos_a_clases(total, guion)
    for indice, clases in enumerate(clases_por_fotograma):
        cv2.imwrite(str(directorio / f"f_{indice:04d}.png"), fotograma_con(clases))
    return directorio


def leer_eventos(ruta: Path) -> list[dict]:
    """Lee el JSONL de eventos; falla si alguna línea no es JSON válido."""
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    return [json.loads(linea) for linea in lineas if linea.strip()]


def tipos_de_evento(eventos: Sequence[dict]) -> list[str]:
    return [evento["tipo"] for evento in eventos]


def config_con_t(ruta: Path, t_parada_s: float) -> Path:
    """Copia la configuración del proyecto ajustando ``t_parada_s``."""
    datos = json.loads(CONFIG_PROYECTO.read_text(encoding="utf-8"))
    datos["t_parada_s"] = t_parada_s
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


def escribir_anotacion(ruta: Path, tramos: Sequence[dict]) -> Path:
    ruta.write_text(json.dumps(list(tramos), ensure_ascii=False), encoding="utf-8")
    return ruta


def correr(fuente: Path, salida: Path, *extra: str) -> tuple[int, dict, list[dict]]:
    """Ejecuta el CLI y devuelve ``(codigo, metricas, eventos)``."""
    codigo = main(
        [
            "--fuente",
            str(fuente),
            "--config",
            str(CONFIG_PROYECTO),
            "--salida",
            str(salida),
            *extra,
        ]
    )
    metricas = json.loads((salida / "metricas.json").read_text(encoding="utf-8"))
    eventos = leer_eventos(salida / "eventos.jsonl")
    return codigo, metricas, eventos


@pytest.fixture()
def fuente_larga(tmp_path: Path) -> Path:
    return escribir_secuencia(tmp_path / "frames_fuente", GUION_LARGO, TOTAL_LARGO)


@pytest.fixture()
def salida(tmp_path: Path) -> Path:
    return tmp_path / "salida"


# --------------------------------------------------------------------------
# Recorrido feliz y artefactos
# --------------------------------------------------------------------------


def test_corrida_completa_devuelve_codigo_ok(
    fuente_larga: Path, salida: Path
) -> None:
    codigo, metricas, _ = correr(fuente_larga, salida)
    assert codigo == CODIGO_OK
    assert metricas["frames_procesados"] == TOTAL_LARGO


def test_corrida_escribe_los_dos_artefactos(fuente_larga: Path, salida: Path) -> None:
    correr(fuente_larga, salida)
    assert (salida / "metricas.json").is_file()
    assert (salida / "eventos.jsonl").is_file()
    # metricas.json debe ser JSON recargable, no un volcado de texto.
    recargado = json.loads((salida / "metricas.json").read_text(encoding="utf-8"))
    assert recargado["corrida_id"] == salida.name


def test_metricas_json_tiene_todas_las_claves_del_contrato(
    fuente_larga: Path, salida: Path
) -> None:
    _, metricas, _ = correr(fuente_larga, salida)
    esperadas = {
        "corrida_id",
        "fuente",
        "frames_procesados",
        "ocurrencias_pare",
        "ocurrencias_siga",
        "detecciones_correctas",
        "falsos_positivos",
        "confusiones",
        "latencias_frames",
        "latencias_ms",
        "paradas",
        "fps_promedio",
        "latencia_media_ms",
        "latencia_p95_ms",
    }
    assert esperadas <= set(metricas)


def test_eventos_jsonl_registra_las_dos_confirmaciones(
    fuente_larga: Path, salida: Path
) -> None:
    _, _, eventos = correr(fuente_larga, salida)
    tipos = tipos_de_evento(eventos)
    assert tipos.count("PARE_CONFIRMADO") == 1
    assert tipos.count("SIGA_CONFIRMADO") == 1

    confirmaciones = [e for e in eventos if e["tipo"].endswith("_CONFIRMADO")]
    por_clase = {e["clase"]: e for e in confirmaciones}
    assert set(por_clase) == {"PARE", "SIGA"}
    assert por_clase["PARE"]["frame"] == F_PARE_CONFIRMADO
    assert por_clase["SIGA"]["frame"] == F_SIGA_CONFIRMADO
    for evento in confirmaciones:
        # Cada confirmación lleva su instante, su ocurrencia y su centro.
        assert isinstance(evento["ts"], float)
        assert evento["ocurrencia_id"] is not None
        assert len(evento["centro"]) == 2


def test_eventos_jsonl_incluye_las_transiciones_de_estado(
    fuente_larga: Path, salida: Path
) -> None:
    """El JSONL es la traza completa: eventos de señal *y* cambios de estado."""
    _, _, eventos = correr(fuente_larga, salida)
    transiciones = [e for e in eventos if e["tipo"] == "TRANSICION"]
    recorrido = [(t["origen"], t["destino"], t["causa"]) for t in transiciones]
    assert recorrido == [
        ("EN_MARCHA", "DETENIDO_MINIMO", "PARE_CONFIRMADO"),
        ("DETENIDO_MINIMO", "EN_MARCHA", "T_CUMPLIDO"),
    ]


def test_la_corrida_larga_cierra_una_parada_con_retardo(
    fuente_larga: Path, salida: Path
) -> None:
    """Con T=3,0 s el robot reanuda al cumplirse T y el retardo queda registrado."""
    _, metricas, _ = correr(fuente_larga, salida)
    assert len(metricas["paradas"]) == 1
    parada = metricas["paradas"][0]
    assert parada["t_configurado_s"] == pytest.approx(3.0)
    assert parada["inicio_t"] == pytest.approx(F_PARE_CONFIRMADO / 30.0, abs=1e-6)
    # La parada cierra al cumplirse T, no al llegar el SIGA.
    assert parada["fin_t"] == pytest.approx(F_T_CUMPLIDO / 30.0, abs=1e-6)
    assert parada["retardo_s"] == pytest.approx(0.0, abs=1e-6)


def test_latencia_de_decision_se_registra_en_fotogramas(
    fuente_larga: Path, salida: Path
) -> None:
    """SC-003: la latencia de decisión va en fotogramas, no en milisegundos."""
    _, metricas, _ = correr(fuente_larga, salida)
    # Ambas señales aparecen en su primer fotograma y se confirman N=3 después.
    assert metricas["latencias_frames"] == [2, 2]
    assert len(metricas["latencias_ms"]) == 2


def test_conteo_de_ocurrencias_es_uno_por_clase(fuente_larga: Path, salida: Path) -> None:
    _, metricas, _ = correr(fuente_larga, salida)
    assert metricas["ocurrencias_pare"] == 1
    assert metricas["ocurrencias_siga"] == 1


def test_sin_anotacion_no_se_contabilizan_falsos_positivos(
    fuente_larga: Path, salida: Path
) -> None:
    """Sin referencia el CLI cuenta ocurrencias pero no juzga acierto (Q3).

    Es la garantía de CHK017: sin anotación, una detección correcta no puede
    terminar contabilizada como error.
    """
    _, metricas, _ = correr(fuente_larga, salida)
    assert metricas["detecciones_correctas"] == 0
    assert metricas["falsos_positivos"] == 0
    assert metricas["confusiones"] == 0
    assert metricas["ocurrencias_pare"] + metricas["ocurrencias_siga"] == 2


# --------------------------------------------------------------------------
# Confronta con anotación de referencia (FR-025)
# --------------------------------------------------------------------------


def test_anotacion_coincidente_convierte_detecciones_en_aciertos(
    tmp_path: Path, fuente_larga: Path, salida: Path
) -> None:
    anotacion = escribir_anotacion(
        tmp_path / "anot.json",
        [
            {"clase": "PARE", "fotograma_inicio": 10, "fotograma_fin": 25},
            {"clase": "SIGA", "fotograma_inicio": 106, "fotograma_fin": 121},
        ],
    )
    _, metricas, _ = correr(fuente_larga, salida, "--anotacion", str(anotacion))
    assert metricas["detecciones_correctas"] == 2
    assert metricas["falsos_positivos"] == 0
    assert metricas["confusiones"] == 0


def test_anotacion_que_no_cubre_el_fotograma_confirmado_cuenta_falso_positivo(
    tmp_path: Path, fuente_larga: Path, salida: Path
) -> None:
    """La confrontación usa el fotograma de *confirmación*, no el de aparición.

    La ventana termina en 11, antes de que el PARE se confirme en 12: la
    detección no encuentra respaldo y se cuenta como falso positivo.
    """
    anotacion = escribir_anotacion(
        tmp_path / "anot_corta.json",
        [
            {"clase": "PARE", "fotograma_inicio": 10, "fotograma_fin": 11},
            {"clase": "SIGA", "fotograma_inicio": 106, "fotograma_fin": 121},
        ],
    )
    _, metricas, _ = correr(fuente_larga, salida, "--anotacion", str(anotacion))
    assert metricas["detecciones_correctas"] == 1  # solo el SIGA
    assert metricas["falsos_positivos"] == 1  # el PARE
    assert metricas["confusiones"] == 0


def test_anotacion_con_clase_distinta_registra_confusion(
    tmp_path: Path, fuente_larga: Path, salida: Path
) -> None:
    """Un PARE anotado como SIGA es una confusión, no un acierto ni un FP."""
    anotacion = escribir_anotacion(
        tmp_path / "anot_confusa.json",
        [
            {"clase": "SIGA", "fotograma_inicio": 10, "fotograma_fin": 25},
            {"clase": "SIGA", "fotograma_inicio": 106, "fotograma_fin": 121},
        ],
    )
    _, metricas, _ = correr(fuente_larga, salida, "--anotacion", str(anotacion))
    assert metricas["confusiones"] == 1
    assert metricas["detecciones_correctas"] == 1
    assert metricas["falsos_positivos"] == 0


def test_anotacion_vacia_es_equivalente_a_no_anotar(
    tmp_path: Path, fuente_larga: Path, salida: Path
) -> None:
    """``--anotacion`` con lista vacía deja los contadores de juicio en cero.

    ``Referencia.cargar([])`` produce una referencia sin tramos, así que
    ``consultar`` nunca marca nada y el módulo solo cuenta ocurrencias.
    """
    anotacion_vacia = escribir_anotacion(tmp_path / "anot_vacia.json", [])
    _, sin_anotacion, _ = correr(fuente_larga, salida)
    _, con_vacia, _ = correr(fuente_larga, salida, "--anotacion", str(anotacion_vacia))

    for clave in ("detecciones_correctas", "falsos_positivos", "confusiones"):
        assert sin_anotacion[clave] == 0
        assert con_vacia[clave] == 0
    # Y el conteo de ocurrencias no se altera por llevar referencia.
    assert con_vacia["ocurrencias_pare"] == sin_anotacion["ocurrencias_pare"] == 1
    assert con_vacia["ocurrencias_siga"] == sin_anotacion["ocurrencias_siga"] == 1


# --------------------------------------------------------------------------
# Registro de paradas
# --------------------------------------------------------------------------


def test_una_corrida_que_termina_detenida_no_registra_parada(
    fuente_larga, salida: Path
) -> None:
    """``paradas`` se cierra al reanudar; si nunca reanuda, no hay entrada."""
    fuente = escribir_secuencia(
        salida.parent / "solo_pare", [(10, 60, "PARE")], 80
    )
    _, metricas, _ = correr(fuente, salida)
    assert metricas["paradas"] == []
    assert metricas["ocurrencias_pare"] == 1


def test_la_parada_se_registra_con_T_y_retardo_al_reanudar(
    tmp_path: Path, salida: Path
) -> None:
    """Con T corto la parada se cierra al llegar el SIGA y queda en el resumen."""
    config = config_con_t(tmp_path / "config_t.json", t_parada_s=0.5)
    fuente = escribir_secuencia(
        tmp_path / "frames_t", [(10, 40, "PARE"), (20, 40, "SIGA")], 45
    )
    codigo = main(
        [
            "--fuente",
            str(fuente),
            "--config",
            str(config),
            "--salida",
            str(salida),
        ]
    )
    assert codigo == CODIGO_OK
    metricas = json.loads((salida / "metricas.json").read_text(encoding="utf-8"))

    assert len(metricas["paradas"]) == 1
    parada = metricas["paradas"][0]
    assert parada["t_configurado_s"] == pytest.approx(0.5)
    assert parada["inicio_t"] < parada["fin_t"]
    # T es una parada *mínima*: reanudar antes violaría FR-017, así que el
    # retardo respecto de la configuración no puede ser negativo.
    assert parada["retardo_s"] == pytest.approx(0.0, abs=1e-9)
    assert parada["fin_t"] - parada["inicio_t"] >= parada["t_configurado_s"]


# --------------------------------------------------------------------------
# Diagnóstico y límites
# --------------------------------------------------------------------------


def test_diagnostico_escribe_un_fotograma_anotado_por_entrada(
    fuente_larga: Path, salida: Path
) -> None:
    correr(fuente_larga, salida, "--diagnostico")
    frames = salida / "frames"
    assert frames.is_dir()
    escritos = sorted(frames.glob("frame_*.png"))
    assert len(escritos) == TOTAL_LARGO
    assert (frames / "frame_000000.png").is_file()
    anotado = cv2.imread(str(frames / f"frame_{F_PARE_CONFIRMADO:06d}.png"))
    assert anotado is not None and anotado.shape[:2] == (480, 640)


def test_sin_diagnostico_no_se_escriben_fotogramas(
    fuente_larga: Path, salida: Path
) -> None:
    correr(fuente_larga, salida)
    assert not (salida / "frames").exists()


def test_max_fotogramas_limita_el_procesamiento(fuente_larga: Path, salida: Path) -> None:
    _, metricas, _ = correr(fuente_larga, salida, "--max-fotogramas", "20")
    assert metricas["frames_procesados"] == 20
    # 20 fotogramas no alcanzan a confirmar el PARE (N=3 a partir del 10 sí alcanza,
    # pero no hay tiempo de reanudar), así que no debe haber señal de SIGA.
    assert metricas["ocurrencias_siga"] == 0


def test_el_corrida_id_toma_el_nombre_del_directorio_de_salida(
    fuente_larga: Path, tmp_path: Path
) -> None:
    salida = tmp_path / "corrida_0007"
    _, metricas, _ = correr(fuente_larga, salida)
    assert metricas["corrida_id"] == "corrida_0007"


def test_la_fuente_queda_registrada_en_las_metricas(fuente_larga: Path, salida: Path) -> None:
    _, metricas, _ = correr(fuente_larga, salida)
    assert metricas["fuente"] == str(fuente_larga)


def test_fotograma_ilegible_no_aborta_la_corrida(tmp_path: Path, salida: Path) -> None:
    """Degradación controlada: un PNG corrupto se omite con aviso (FR-027)."""
    fuente = escribir_secuencia(tmp_path / "frames_roto", [(10, 40, "PARE")], 30)
    (fuente / "f_0005.png").write_bytes(b"esto no es un png")
    codigo, metricas, _ = correr(fuente, salida)
    assert codigo == CODIGO_OK
    assert metricas["frames_procesados"] == 29
    assert metricas["ocurrencias_pare"] == 1


# --------------------------------------------------------------------------
# Códigos de error del contrato
# --------------------------------------------------------------------------


def test_fuente_inexistente_devuelve_entrada_invalida(tmp_path: Path, salida: Path) -> None:
    codigo = main(
        [
            "--fuente",
            str(tmp_path / "no_existe"),
            "--config",
            str(CONFIG_PROYECTO),
            "--salida",
            str(salida),
        ]
    )
    assert codigo == CODIGO_ENTRADA_INVALIDA


def test_directorio_sin_imagenes_devuelve_entrada_invalida(
    tmp_path: Path, salida: Path
) -> None:
    vacio = tmp_path / "vacio"
    vacio.mkdir()
    codigo = main(
        [
            "--fuente",
            str(vacio),
            "--config",
            str(CONFIG_PROYECTO),
            "--salida",
            str(salida),
        ]
    )
    assert codigo == CODIGO_ENTRADA_INVALIDA


def test_video_ilegible_devuelve_entrada_invalida(tmp_path: Path, salida: Path) -> None:
    falso_video = tmp_path / "falso.mp4"
    falso_video.write_bytes(b"no es un video")
    codigo = main(
        [
            "--fuente",
            str(falso_video),
            "--config",
            str(CONFIG_PROYECTO),
            "--salida",
            str(salida),
        ]
    )
    assert codigo == CODIGO_ENTRADA_INVALIDA


@pytest.mark.parametrize(
    "contenido",
    ["{ esto no es json", "[]", '{"roi_linea": {"x": 2.0}}'],
    ids=["json_roto", "lista", "roi_fuera_de_rango"],
)
def test_configuracion_invalida_devuelve_entrada_invalida(
    tmp_path: Path, salida: Path, contenido: str
) -> None:
    config = tmp_path / "config_mala.json"
    config.write_text(contenido, encoding="utf-8")
    fuente = escribir_secuencia(tmp_path / "frames", [(10, 40, "PARE")], 30)
    codigo = main(
        ["--fuente", str(fuente), "--config", str(config), "--salida", str(salida)]
    )
    assert codigo == CODIGO_ENTRADA_INVALIDA


def test_configuracion_inexistente_devuelve_entrada_invalida(
    tmp_path: Path, salida: Path
) -> None:
    fuente = escribir_secuencia(tmp_path / "frames", [(10, 40, "PARE")], 30)
    codigo = main(
        [
            "--fuente",
            str(fuente),
            "--config",
            str(tmp_path / "no_existe.json"),
            "--salida",
            str(salida),
        ]
    )
    assert codigo == CODIGO_ENTRADA_INVALIDA


@pytest.mark.parametrize(
    "contenido",
    ["{roto", '{"no": "es una lista"}'],
    ids=["json_roto", "objeto_en_vez_de_lista"],
)
def test_anotacion_invalida_devuelve_entrada_invalida(
    tmp_path: Path, salida: Path, contenido: str
) -> None:
    anotacion = tmp_path / "anot_mala.json"
    anotacion.write_text(contenido, encoding="utf-8")
    fuente = escribir_secuencia(tmp_path / "frames", [(10, 40, "PARE")], 30)
    codigo = main(
        [
            "--fuente",
            str(fuente),
            "--config",
            str(CONFIG_PROYECTO),
            "--salida",
            str(salida),
            "--anotacion",
            str(anotacion),
        ]
    )
    assert codigo == CODIGO_ENTRADA_INVALIDA


def test_falta_de_fuente_es_error_de_argumentos() -> None:
    """``--fuente`` es obligatorio: argparse debe cortar la ejecución."""
    with pytest.raises(SystemExit) as excepcion:
        main([])
    assert excepcion.value.code != CODIGO_OK


# --------------------------------------------------------------------------
# El punto de entrada real
# --------------------------------------------------------------------------


def test_python_m_src_main_termina_con_codigo_ok(
    fuente_larga: Path, salida: Path
) -> None:
    """Prueba de humo del entry point, incluido el ``sys.exit`` de __main__."""
    proceso = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.main",
            "--fuente",
            str(fuente_larga),
            "--config",
            str(CONFIG_PROYECTO),
            "--salida",
            str(salida),
        ],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    assert proceso.returncode == CODIGO_OK, proceso.stderr
    assert "Resumen de corrida" in proceso.stdout
    assert (salida / "metricas.json").is_file()
    assert (salida / "eventos.jsonl").is_file()


def test_python_m_src_main_propaga_entrada_invalida(
    tmp_path: Path, salida: Path
) -> None:
    proceso = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.main",
            "--fuente",
            str(tmp_path / "no_existe"),
            "--config",
            str(CONFIG_PROYECTO),
            "--salida",
            str(salida),
        ],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert proceso.returncode == CODIGO_ENTRADA_INVALIDA
