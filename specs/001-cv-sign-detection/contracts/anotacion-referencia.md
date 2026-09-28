# Contrato: Anotación de Referencia

**Propósito**: definir el formato, el procedimiento y el tamaño de la anotación de referencia que
sirve de denominador a las tasas de aceptación (Q3, FR-025) y al IoU de la línea (SC-010).

**Por qué existe este contrato**: los criterios SC-001, SC-002 y SC-010 son *medibles*, pero hasta
ahora ningún artefacto definía **cómo se anota** ni **cuánto se anota**. Existían dos formatos
distintos e incompletos: el de señales, implementado en `src/main.py` (clase `Referencia`) pero
documentado solo en el docstring del código; y el de la máscara de línea, **inexistente**. Este
contrato consolida ambos.

**Trazabilidad**: `spec.md` §SC-001/§SC-002/§SC-010 · `data-model.md` §Ocurrencia · T031, T027, T030 ·
checklist CHK024, CHK031.

---

## 1. Anotación de señales (existente, sin cambios)

Ya implementada y en uso por el CLI mediante `--anotacion`. Se documenta aquí para que el contrato
sea completo.

**Formato** — archivo JSON con una lista de tramos, uno por señal física de la pista:

```json
[
  { "clase": "PARE", "fotograma_inicio": 310, "fotograma_fin": 428 },
  { "clase": "SIGA", "fotograma_inicio": 902, "fotograma_fin": 1015 }
]
```

| Campo | Tipo | Regla |
|-------|------|-------|
| `clase` | `"PARE"` \| `"SIGA"` | Obligatorio. Mayúsculas. |
| `fotograma_inicio` | int | Primer fotograma en que la señal es visible dentro de la ROI. |
| `fotograma_fin` | int | Último fotograma en que lo es. `fotograma_inicio` si es un solo fotograma. |

**Semántica del denominador**: cada tramo es **una ocurrencia** (Q3). Las tasas de SC-001, SC-002 y
SC-003 se calculan como `detecciones_correctas / ocurrencias_anotadas` de la clase correspondiente.

**Sin este archivo** el módulo funciona igual: `MetricasCorrida.registrar_senal` recibe
`anotada=None` y **solo aporta conteos**, sin juzgar acierto ni error
(`contracts/api-pipeline.md` §Métricas).

**Tamaño del corpus de señales.** SC-001 y SC-002 exigen el 100 % de las ocurrencias, así que el
denominador debe ser auditable:

| Parámetro | Valor mínimo | Justificación |
|-----------|---------------|---------------|
| Videos | **≥ 2** | Un video no distingue método de accidente afortunado. |
| Ocurrencias PARE | **≥ 3** en total | Tres detecciones consecutivas con una señal fallada detectan el error; una sola no. |
| Ocurrencias SIGA | **≥ 3** en total | Ídem; además, un SIGA perdido detiene la carrera (§ spec §SC-002). |
| Ocurrencias por clase **por video** | **≥ 1** | Evita que las tres ocurrencias estén todas en la misma toma. |

Si la pista del curso ofrece menos de estos umbrales, **se reporta el denominador real y se declara
el criterio no evaluable al 100 %** — no se rellena con una afirmación. Un 100 % sobre 1
ocurrencia no es evidencia de nada y no debe aparecer en el póster como tal.

---

## 2. Anotación de la máscara de línea (nuevo)

### 2.1 Formato

Archivo `anotacion_linea.json` en el mismo directorio que el video, con esta forma:

```jsonc
{
  "video": "pista_01.mp4",
  "resolucion": [640, 480],
  "formato": "png_binario",
  "metodo": "pintado manual de la línea guía sobre el fotograma original, grosor ~3 px",
  "mascaras": {
    "42":  "anotacion/pista_01/mascara_000042.png",
    "57":  "anotacion/pista_01/mascara_000057.png"
  }
}
```

| Campo | Tipo | Obligatorio | Regla |
|-------|------|-------------|-------|
| `video` | str | sí | Nombre del video al que corresponde. Debe coincidir con el archivo fuente. |
| `resolucion` | [int, int] | sí | `[ancho, alto]` del video. Las máscaras deben tener exactamente estas dimensiones. |
| `formato` | str | sí | Solo `"png_binario"` en v1. |
| `metodo` | str | sí | Descripción libre del procedimiento seguido.Obligatoria para la trazabilidad. |
| `mascaras` | object | sí | Mapa `índice de fotograma (str) → ruta relativa al directorio del JSON`. |

**Máscara PNG**: imagen de un solo canal, valores **0 o 255** únicamente, sin antialias, misma
resolución que el fotograma. `255` = píxel de la línea guía; `0` = fondo. Una máscara vacía (todo
0) es un error de anotación, no un caso válido: la línea debe ser visible en todo fotograma anotado.

### 2.2 Procedimiento

1. La anotación se realiza **sin ver la salida del algoritmo**. Anotar sobre la predicción hace la
   evaluación circular y el IoU meaningless. Si existe más de una persona, las anotaciones se
   resuelven por consenso; si no, una sola persona y se registra su identidad en `metodo`.
2. Se parte del **fotograma original** del video, sin los filtros del módulo.
3. La línea se pinta siguiendo el centro de la guía visible, con grosor constante (~3 px) para
   absorber el error de localización inevitable a esa escala.
4. Solo se anotan fotogramas en los que la línea es visible **dentro de la ROI de línea**
   (`roi_linea` de `config/vision.json`). Fuera de la ROI no hay predicción con la cual comparar, y
   anotarlos contaminaría la media del IoU a la baja.
5. Se usan valores binarios estrictos (0/255). Una máscara con valores intermedios se rechaza.

### 2.3 Tamaño del subconjunto

| Parámetro | Valor | Justificación |
|-----------|-------|---------------|
| Fotogramas por video | **≥ 20** | Suficiente para que la media del IoU tenga dispersión interpretable. |
| Paso de muestreo | **cada 15 fotogramas** (≈ 0,5 s a 30 fps) | Cobertura temporal de toda la corrida sin que el trabajo manual sea inviable. |
| Videos en el corpus | **≥ 2** | Ninguna decisión se valida con una sola toma: una única corrida no distingue un método de un accidente afortunado. |
| Totales | **≥ 40 fotogramas** | Suma de los anteriores. |

Si un fotograma del paso de muestreo no tiene línea visible dentro de la ROI, **se omite y se
registra el siguiente**. El subconjunto final se reporta explícitamente con su tamaño real.

### 2.4 Cálculo del IoU

Para cada fotograma anotado, entre la predicción `mascara_linea` y la máscara de referencia:

```
IoU = |predicción ∩ referencia| / |predicción ∪ referencia|
```

Reglas:

- Si ambos conjuntos son vacíos, el fotograma **no cuenta** (no hay línea que evaluar).
- Si solo uno es vacío, `IoU = 0` (fallo de detección completo, no ausencia de datos).
- **SC-010 se cumple si la media del IoU sobre todos los fotogramas anotados del corpus es ≥ 0,60.**
- Se reportan además **mediana, mínimo y desviación estándar**, y el desglose por video: una media
  alta sostenida por un solo video no es evidencia de robustez.

### 2.5 Qué NO es la línea guía

La máscara de línea es un **subconjunto de la ROI de línea**, no la pista completa. La comparación
es entre la predicción y la referencia **recortadas a la misma ROI**, para que un cambio de
parámetros de la ROI no altere artificialmente el IoU.

---

## 3. Relación entre los dos formatos

| | Señales | Máscara de línea |
|---|---------|-------------------|
| Unidad anotada | **tramo de fotogramas** (una señal física) | **fotograma individual** (píxeles) |
| Formato | JSON con lista de tramos | JSON + PNG binario por fotograma |
| Alimenta | SC-001, SC-002, SC-003, SC-004 | SC-010 |
| Carga el CLI | `--anotacion` | `--anotacion-linea` (previsto, T027) |
| Necesario para | evaluar aciertos de detección | evaluar la máscara de la guía |

Ambos denominan la **misma corrida de evaluación** y deben cubrir los mismos videos: no es válido
medir SC-001 sobre un video y SC-010 sobre otro.

---

## 4. Validez de la evaluación

Una evaluación es válida solo si cumple **todo** lo siguiente. Si falla cualquiera, los números no
se publican como resultado y se reporta como no evaluado:

1. El corpus cumple el tamaño mínimo de §2.3 y se reporta su tamaño real.
2. Las máscaras tienen la resolución declarada y valores binarios estrictos.
3. La anotación se hizo sin acceso a la salida del algoritmo (§2.2.1).
4. Los mismos videos respaldan las métricas de señales y las de línea (§3).
5. Se ejecutó con los parámetros de `config/vision.json` versionados junto al resultado, de modo que
   el resultado sea reproducible.

---

**Nota de alcance**: este contrato define el formato y el procedimiento. La carga del archivo y el
cálculo del IoU se implementan en T027. El registro de los valores observados en el protocolo de
evaluación corresponde a T030.
