"""Estimación de la posición lateral de la línea guía (Objetivo 3 del Reto 1).

**Técnicas autorizadas y únicamente ellas** (Reto 1, §«Se permite el uso de»):
operaciones aritméticas y lógicas sobre la máscara binaria — suma por columna,
comparación con el valor máximo y media ponderada. No se usa transformada de
Hough, ``cv2.fitLine`` ni ninguna biblioteca que localice la línea por su cuenta
(FR-003, Principio I de la Constitución).

**Por qué el centroide del pico y no el centro del run más largo.** Medido sobre
los 9 vídeos reales (2026-09-28, 478×850): el centroide del pico con soporte
≥ 50 % da una desviación de posición entre fotogramas de 50.5/56.7 px, frente a
78.4/78.9 px del método del run más largo; y dos estimadores independientes
correlacionan +0.76/+0.86, luego la señal es genuina. La elección y las
alternativas descartadas están en ``research.md``, Decisión 1.

**Qué no decide este módulo.** No sabe hacia qué lado gira el robot: sólo
informa dónde está la línea. La equivalencia con el giro físico depende del
montaje y es un riesgo declarado en la spec.
"""

from __future__ import annotations

import numpy as np

from src.vision.configuracion import ParametrosConfiguracion
from src.vision.modelos import PosicionLinea, ResultadoSegmentacion

__all__ = ["EstimadorLinea"]


class EstimadorLinea:
    """Calcula la posición lateral de la línea en un fotograma.

    Es determinista y sin estado entre llamadas: todo el contexto viene de la
    ``ResultadoSegmentacion`` del fotograma y de los parámetros inyectados
    (FR-008, Principio IV).
    """

    def __init__(self, params: ParametrosConfiguracion) -> None:
        self._params = params

    def aplicar(self, seg: ResultadoSegmentacion) -> PosicionLinea:
        """Estima la posición de la línea dentro de la ROI de línea.

        Devuelve siempre una ``PosicionLinea``. Si no hay un pico dominante, el
        resultado es inválido y **no trae posición**: es imposible que el
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

        # 3. Pico dominante y banda de soporte (columnas con masa >= frac_pico
        # del máximo). La pertenencia es inclusiva por dentro: una columna
        # exactamente en el umbral cuenta como parte de la banda.
        maximo = float(perfil.max())
        if maximo <= 0.0:
            return _invalida()
        i_pico = int(np.argmax(perfil))
        soporte = perfil >= (maximo * self._params.frac_pico)
        if not soporte[i_pico]:
            # Solo sería posible si frac_pico fuera 0, que la configuración
            # rechaza (V4); se mantiene la guarda por seguridad.
            return _invalida()

        # 4. El soporte puede partirse en varios tramos contiguos: si el hueco
        #    entre ellos tiene masa, son modos distintos y promediar entre ellos
        #    sería inventar una línea que no existe (contrato §1). El centroide se
        #    calcula sólo dentro del tramo que contiene el pico, y la masa de los
        #    demás tramos penaliza la confianza.
        tramos = _tramos(soporte)
        principal = next((t for t in tramos if t[0] <= i_pico < t[1]), None)
        if principal is None:
            return _invalida()
        inicio, fin = principal
        pesos = perfil[inicio:fin]
        masa_principal = float(pesos.sum())
        if masa_principal <= 0.0:
            return _invalida()
        # `np.arange` ya produce índices absolutos dentro de la ROI: no se suma
        # `inicio` otra vez, o la posición se desplazaría dos veces su offset.
        x_roi_pico = float((np.arange(inicio, fin) * pesos).sum() / masa_principal)
        ancho_banda = float(fin - inicio)
        masa_otros = masa_total - masa_principal

        # 5. Coordenadas del fotograma. `x_norm` se normaliza por el ancho del
        # FOTOGRAMA, no por el de la ROI: es lo que hace que `x_objetivo = 0.5`
        # equivalga al centro geométrico (239 px de 478 en el footage medido) y lo
        # que deja el error en la misma escala con independencia de cómo se
        # recorte la ROI (Q4, Q5).
        ancho_fotograma = float(mascara.shape[1])
        x_px = x_roi + x_roi_pico
        x_norm = x_px / ancho_fotograma
        error_norm = x_norm - self._params.x_objetivo

        # 6. Confianza: qué fracción de la masa total sostiene el tramo del pico,
        #    penalizada por ambigüedad (masa comparable en otro tramo) y por
        #    proximidad al borde de la ROI (una línea pegada al borde se trata
        #    como pérdida, no como posición en el borde).
        confianza = self._confianza(perfil, inicio, fin, masa_principal, masa_total)
        if confianza < self._params.umbral_confianza:
            return _invalida()
        if i_pico == 0 or i_pico == ancho_roi - 1:
            # Pico en el borde exacto de la ROI: pérdida, no posición en el borde.
            return _invalida()
        if x_px < 0 or x_px > mascara.shape[1]:
            return _invalida()

        return PosicionLinea(
            x_px=x_px,
            x_norm=x_norm,
            error_norm=error_norm,
            ancho_banda_px=ancho_banda,
            confianza=confianza,
            valida=True,
        )

    def _confianza(
        self,
        perfil: np.ndarray,
        inicio: int,
        fin: int,
        masa_principal: float,
        masa_total: float,
    ) -> float:
        """Dominancia del tramo del pico en [0, 1], penalizada por borde y ambigüedad.

        Tres factores, todos medibles sobre la proyección:
        - dominancia: masa del tramo del pico sobre la masa total de la banda;
        - borde: el tramo no debe pegarse a los extremos de la ROI;
        - ambigüedad: masa de los OTROS tramos frente a la del tramo del pico.

        La ambigüedad se mide sobre tramos separados y no sobre «la mejor columna
        que queda al apagar el soporte»: con esa otra definición, dos bandas
        disjuntas (con un hueco de masa cero entre ellas) se leerían como un
        único soporte enorme con confianza 1.0, que es precisamente el promedio
        entre modos distintos que el contrato prohíbe.
        """
        dominancia = masa_principal / masa_total if masa_total > 0 else 0.0

        ancho_roi = perfil.size
        # 1.0 cuando el tramo está lejos de los bordes; baja a 0 si lo toca.
        borde = min(1.0, min(inicio, ancho_roi - fin) / max(1.0, 0.10 * ancho_roi))

        # 0.0 si no hay otro modo; → 1.0 si los otros tramos pesan como el principal.
        ambiguedad = 0.0 if masa_principal <= 0 else min(1.0, (masa_total - masa_principal) / masa_principal)

        return float(max(0.0, min(1.0, dominancia * borde * (1.0 - ambiguedad))))


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
