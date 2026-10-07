"""Estimación de la posición lateral de la línea guía (Objetivo 3 del Reto 1).

**Técnicas autorizadas y únicamente ellas** (Reto 1, §«Se permite el uso de»):
operaciones aritméticas y lógicas sobre la máscara binaria — suma por columna,
comparación con umbral (grosor y pico), conteo de filas cubiertas (continuidad)
y media ponderada. No se usa transformada de Hough, ``cv2.fitLine`` ni ninguna
biblioteca que localice la línea por su cuenta (FR-003, Principio I de la
Constitución).

**Por qué el centroide del pico y no el centro del run más largo.** Medido sobre
los 9 vídeos reales (2026-09-28, 478×850): el centroide del pico con soporte
≥ 50 % da una desviación de posición entre fotogramas de 50.5/56.7 px, frente a
78.4/78.9 px del método del run más largo; y dos estimadores independientes
correlacionan +0.76/+0.86, luego la señal es genuina. La elección y las
alternativas descartadas están en ``research.md``, Decisión 1.

**Selección entre varias líneas (líneas trampa).** El perfil de columnas puede
tener varios tramos: la pista guía y líneas negras trampa, más delgadas, que
entran en el ROI. Un pico alto no distingue una de otra —una trampa delgada y
continua tiene la misma masa por columna que la pista—, así que el estimador
construye **un candidato por tramo** y elige con tres criterios, en este orden:

1. **grosor**: se descartan los tramos más delgados que
   ``grosor_minimo_rel`` × ancho del fotograma. Es el criterio que separa la
   pista de las trampas: la diferencia declarada es el grosor, no el color.
2. **grosor × continuidad**: entre los candidatos válidos gana el de mayor
   puntaje, que favorece a la vez la banda ancha y la que cubre más filas.
3. **coherencia con la trayectoria**: si hay memoria del último ``x`` válido, se
   prefieren los candidatos que no se alejen más de ``salto_maximo_rel`` × ancho
   del fotograma; así una trampa que aparece en el ROI no le roba la posición a
   la pista que el robot venía siguiendo. Si nada es coherente (curva fuerte),
   decide el puntaje para no perder la línea.

Este módulo sigue siendo determinista (mismas entradas en el mismo orden ⇒
misma salida); la única memoria es la última ``x_px`` válida y solo se usa para
desempatar, no para medir.

**Qué no decide este módulo.** No sabe hacia qué lado gira el robot: sólo
informa dónde está la línea. La equivalencia con el giro físico depende del
montaje y es un riesgo declarado en la spec.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.vision.configuracion import ParametrosConfiguracion
from src.vision.modelos import PosicionLinea, ResultadoSegmentacion

__all__ = ["EstimadorLinea"]

#: Un candidato solo compite con el mejor si su puntaje (grosor × continuidad)
#: no baja de esta fracción suya. Evita que una trampa delgada que pase el
#: filtro de grosor desplace a la pista por estar más cerca de la memoria.
_FRACCION_PUNTAJE_MINIMO = 0.5


@dataclass(frozen=True)
class _Candidato:
    """Tramo de la máscara con su grosor, continuidad y posición.

    ``x_px`` es la coordenada absoluta (centroide ponderado del tramo), en la
    misma escala que la ``PosicionLinea`` que devuelve el estimador.
    """

    inicio: int
    fin: int
    x_px: float
    ancho_px: int
    masa: float
    continuidad: float

    @property
    def puntaje(self) -> float:
        """Grosor efectivo: ancho del tramo por la fracción de filas cubiertas."""
        return self.ancho_px * self.continuidad


class EstimadorLinea:
    """Calcula la posición lateral de la línea en un fotograma.

    Mantiene **una** memoria —la última ``x_px`` válida— para preferir, entre
    varios candidatos, el coherente con la trayectoria que el robot venía
    siguiendo (FR-008). Es determinista y la memoria no interviene en la
    medición: una línea única se lee igual con o sin ella.
    """

    def __init__(self, params: ParametrosConfiguracion) -> None:
        self._params = params
        self._x_anterior: float | None = None

    def reiniciar(self) -> None:
        """Olvida la trayectoria; se llama entre corridas (FR-023, como el control)."""
        self._x_anterior = None

    def aplicar(self, seg: ResultadoSegmentacion) -> PosicionLinea:
        """Estima la posición de la línea dentro de la ROI de línea.

        Devuelve siempre una ``PosicionLinea``. Si no hay ningún candidato
        (máscara vacía, ruido suelto o solo líneas más delgadas que la pista),
        el resultado es inválido y **no trae posición**: es imposible que el
        control consuma un número inventado (Q2, FR-006).
        """
        x_roi, y_roi, ancho_roi, alto_roi = seg.roi_linea
        if ancho_roi <= 0 or alto_roi <= 0:
            return _invalida()

        mascara = np.asarray(seg.mascara_linea, dtype=np.uint8)
        if mascara.ndim != 2 or y_roi + alto_roi > mascara.shape[0] or x_roi + ancho_roi > mascara.shape[1]:
            return _invalida()

        # 1. Recorte de la ROI y de la banda de lectura: `frac_anticipacion`
        # descarta el tramo superior de la ROI —la parte más lejana, que es la
        # que más se estrecha y más ruido acumula— y lee el tramo cercano al
        # robot, que es el pertinente para corregir a tiempo (técnica autorizada:
        # recorte de regiones de interés).
        y_fin = y_roi + alto_roi
        y_banda = y_roi + int(alto_roi * self._params.frac_anticipacion)
        if y_fin - y_banda <= 0:
            return _invalida()
        banda = mascara[y_banda:y_fin, x_roi : x_roi + ancho_roi]
        if banda.size == 0 or not banda.any():
            return _invalida()

        # 2. Proyección de columnas: suma aritmética de la máscara binaria.
        # Vectorizada, sin bucles por píxel (Q7, FR-010).
        perfil = banda.sum(axis=0, dtype=np.float64)
        masa_total = float(perfil.sum())
        if masa_total <= 0.0:
            return _invalida()

        # 3. Soporte: columnas con masa >= `frac_pico` del máximo. Dentro del
        # soporte puede haber varios tramos (la pista y una o más trampas).
        maximo = float(perfil.max())
        if maximo <= 0.0:
            return _invalida()
        soporte = perfil >= (maximo * self._params.frac_pico)
        if not soporte.any():
            # Solo sería posible si frac_pico fuera 0, que la configuración
            # rechaza (V4); se mantiene la guarda por seguridad.
            return _invalida()
        ancho_fotograma = float(mascara.shape[1])

        # 4. Un candidato por tramo, con el filtro de grosor. El centroide se
        # calcula dentro del tramo: promediar entre modos distintos sería
        # inventar una línea que no existe (contrato §1).
        candidatos = self._candidatos(perfil, banda, _tramos(soporte), x_roi, ancho_fotograma)
        if not candidatos:
            return _invalida()
        elegido = self._elegir(candidatos, ancho_fotograma)

        # 5. Coordenadas del fotograma. `x_norm` se normaliza por el ancho del
        # FOTOGRAMA, no por el de la ROI: es lo que hace que `x_objetivo = 0.5`
        # equivalga al centro geométrico (239 px de 478 en el footage medido) y lo
        # que deja el error en la misma escala con independencia de cómo se
        # recorte la ROI (Q4, Q5).
        x_px = elegido.x_px
        x_norm = x_px / ancho_fotograma
        error_norm = x_norm - self._params.x_objetivo

        # 6. Confianza: qué fracción de la masa de la banda sostiene el tramo
        # elegido (señal frente a ruido), penalizada por proximidad al borde de
        # la ROI (una línea pegada al borde se trata como pérdida, no como
        # posición en el borde). Un segundo candidato comparable baja la
        # dominancia (~0.5): con el umbral por defecto se elige el mejor y con
        # un umbral alto se rechaza la escena.
        confianza = self._confianza(
            perfil, elegido.inicio, elegido.fin, elegido.masa, masa_total
        )
        if confianza < self._params.umbral_confianza:
            return _invalida()
        if elegido.inicio <= 0 or elegido.fin >= ancho_roi:
            # Tramo pegado al borde exacto de la ROI: pérdida, no posición.
            return _invalida()
        if x_px < 0 or x_px > mascara.shape[1]:
            return _invalida()

        self._x_anterior = x_px
        return PosicionLinea(
            x_px=x_px,
            x_norm=x_norm,
            error_norm=error_norm,
            ancho_banda_px=float(elegido.ancho_px),
            confianza=confianza,
            valida=True,
        )

    def _candidatos(
        self,
        perfil: np.ndarray,
        banda: np.ndarray,
        tramos: list[tuple[int, int]],
        x_roi: int,
        ancho_fotograma: float,
    ) -> list[_Candidato]:
        """Tramos del soporte que superan el grosor mínimo de la pista.

        La continuidad se mide sobre la propia banda: fracción de filas de la
        banda que tienen al menos un píxel en las columnas del tramo. Una línea
        discontinua (o un fragmento) puntúa menos que una continua del mismo
        ancho.
        """
        minimo_px = self._params.grosor_minimo_rel * ancho_fotograma
        alto = banda.shape[0]
        candidatos: list[_Candidato] = []
        for inicio, fin in tramos:
            ancho_px = fin - inicio
            if ancho_px < minimo_px:
                continue
            pesos = perfil[inicio:fin]
            masa = float(pesos.sum())
            if masa <= 0.0:
                continue
            filas = int(banda[:, inicio:fin].any(axis=1).sum())
            continuidad = (filas / alto) if alto > 0 else 0.0
            centro_rel = float((np.arange(inicio, fin) * pesos).sum() / masa)
            candidatos.append(
                _Candidato(
                    inicio=inicio,
                    fin=fin,
                    x_px=x_roi + centro_rel,
                    ancho_px=ancho_px,
                    masa=masa,
                    continuidad=continuidad,
                )
            )
        return candidatos

    def _elegir(self, candidatos: list[_Candidato], ancho_fotograma: float) -> _Candidato:
        """Elige el candidato por grosor/continuidad y coherencia de trayectoria.

        Primero se descarta lo que no compite con el mejor puntaje (una trampa
        delgada que haya pasado el filtro de grosor). Después, si hay memoria
        del último ``x``, se prefieren los candidatos dentro de
        ``salto_maximo_rel`` × ancho del fotograma; si ninguno lo está (la pista
        se movió más que eso, p. ej. en una curva), decide el puntaje.
        """
        mejor = max(c.puntaje for c in candidatos)
        competitivos = [c for c in candidatos if c.puntaje >= _FRACCION_PUNTAJE_MINIMO * mejor]
        if self._x_anterior is not None:
            salto_px = self._params.salto_maximo_rel * ancho_fotograma
            coherentes = [c for c in competitivos if abs(c.x_px - self._x_anterior) <= salto_px]
            if coherentes:
                return max(coherentes, key=lambda c: c.puntaje)
        return max(competitivos, key=lambda c: c.puntaje)

    def _confianza(
        self,
        perfil: np.ndarray,
        inicio: int,
        fin: int,
        masa_principal: float,
        masa_total: float,
    ) -> float:
        """Dominancia del tramo elegido en [0, 1], penalizada por borde.

        Dos factores, medibles sobre la proyección:
        - dominancia: masa del tramo elegido sobre la masa de TODA la banda
          (cuánta señal hay frente a ruido); un segundo candidato comparable
          baja la dominancia a ~0.5, que es la señal de ambigüedad;
        - borde: el tramo no debe pegarse a los extremos de la ROI.

        La ambigüedad **no** se penaliza aquí: cuando hay varios candidatos el
        estimador elige uno —el de mayor grosor × continuidad y coherente con la
        trayectoria— y nunca promedia entre modos. Un umbral de confianza alto
        sigue sirviendo para exigir una escena sin ambigüedad.
        """
        dominancia = masa_principal / masa_total if masa_total > 0 else 0.0

        ancho_roi = perfil.size
        # 1.0 cuando el tramo está lejos de los bordes; baja a 0 si lo toca.
        borde = min(1.0, min(inicio, ancho_roi - fin) / max(1.0, 0.10 * ancho_roi))

        return float(max(0.0, min(1.0, dominancia * borde)))


def _tramos(soporte: np.ndarray) -> list[tuple[int, int]]:
    """Tramos contiguos de ``True`` como pares ``(inicio, fin_exclusivo)``.

    Vectorizado con ``np.diff`` sobre el vector de soporte; el coste es O(ancho),
    no O(ancho × alto), que es lo que exige Q7.
    """
    if soporte.size == 0 or not soporte.any():
        return []
    cambios = np.diff(soporte.astype(np.int8))
    inicios = (np.flatnonzero(cambios == 1) + 1).tolist()
    finales = (np.flatnonzero(cambios == -1) + 1).tolist()
    if soporte[0]:
        inicios.insert(0, 0)
    if soporte[-1]:
        finales.append(int(soporte.size))
    return list(zip(inicios, finales))


def _invalida() -> PosicionLinea:
    """Posición inválida: sin posición y con confianza cero (Q2, FR-006)."""
    return PosicionLinea(
        x_px=None,
        x_norm=None,
        error_norm=None,
        ancho_banda_px=0.0,
        confianza=0.0,
        valida=False,
    )
