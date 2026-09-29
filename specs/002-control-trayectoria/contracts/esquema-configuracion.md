# Contrato: Esquema de Configuración (parámetros de control)

**Feature**: `specs/002-control-trayectoria` | **Fecha**: 2026-09-28 | **Spec**: [spec.md](../spec.md)

Define los parámetros **nuevos** que esta spec añade a `config/vision.json`, su validación y su
trazabilidad. **No redefine** los parámetros de `001`: esos se mantienen intactos.

---

## 1. Principio de integración

Los parámetros de control viven en el **mismo archivo** `config/vision.json` y se cargan con el
**mismo** mecanismo (`cargar_parametros`): defaults + archivo, con validación que lanza
`ConfiguracionInvalidaError(campo, motivo)`.

**No** se crea `config/control.json` ni una segunda función de carga, por dos razones:

1. La Constitución §II exige un módulo por etapa del pipeline, no un archivo por etapa; partir la
   configuración rompería el principio de «parámetros centralizados» de 001 (FR-024 de esa spec,
   FR-038 de esta).
2. `x_objetivo` y `roi_linea` están acoplados: el objetivo se expresa como fracción normalizada
   **relativa al ancho del fotograma**, igual que la ROI. Separarlos facilitaría el error de
   calibrar uno y olvidar el otro.

**Compatibilidad hacia atrás**: si `config/vision.json` no contiene las claves nuevas, se usan los
defaults de la tabla §3. Un archivo de configuración de la era 001 sigue siendo válido.

---

## 2. Formato

JSON plano, un bloque por concepto, coherente con el estilo de `config/vision.json` (llaves en
`snake_case`, números como literales, sin comentarios):

```json
{
  "x_objetivo": 0.5,
  "frac_anticipacion": 0.40,
  "frac_pico": 0.50,
  "umbral_confianza": 0.35,
  "zona_muerta": 0.10,
  "histeresis": 0.03,
  "n_gracia_busqueda": 5,
  "mac_bluetooth": "00:1B:10:21:2C:1B",
  "timeout_transporte_s": 0.20
}
```

**Tipos admitidos**: `float` para fracciones normalizadas, `int` para conteos de fotogramas, `str`
para la dirección MAC del robot.

---

## 3. Parámetros nuevos

### 3.1 Control de trayectoria

| Clave | Tipo | Default | Rango válido | Unidad | Trazabilidad |
|-------|------|---------|--------------|--------|--------------|
| `x_objetivo` | float | `0.5` | `[0.0, 1.0]` | fracción del ancho | FR-004, FR-005 |
| `zona_muerta` | float | `0.10` | `[0.0, 0.5)` | fracción del ancho | FR-012, FR-013 |
| `histeresis` | float | `0.03` | `[0.0, ∞)` | fracción del ancho | FR-012 |
| `n_gracia_busqueda` | int | `5` | `>= 0` | fotogramas | FR-019 |

**Significado de `x_objetivo`**: posición lateral, en fracción del ancho del fotograma, en la que la
línea se considera «centrada» y el robot avanza recto.

> **No es el centro geométrico por definición.** El default `0.5` coincide con el centro porque es el
> punto de partida que pide el Reto («respecto al centro»), pero el valor real depende del montaje de
> la cámara. Evidencia: en los videos de práctica de la misma pista, la posición mediana de la línea
> va de 190.0 a 286.5 px en un cuadro de 478 px (centro = 239), es decir ±0.1 respecto al centro.
> Calibrar contra el centro fijo produciría un sesgo sistemático. Ver `research.md` Decisión 3.

**Significado de `zona_muerta`**: si `|error_norm| < zona_muerta - histeresis`, el comando es
`AVANZAR`. Si `|error_norm| > zona_muerta + histeresis`, se corrige. En la banda intermedia el
comando se mantiene (histéresis).

> **Default justificado con evidencia.** Con `zona_muerta = 0.10`, la fracción de fotogramas de los
> videos de ruta ideal que queda sin corregir es: video1 40.6 %, video2 68.8 %, video3 82.4 %,
> video4 40.4 %. Zonas más estrechas (0.02–0.05) fuerzan correcciones innecesarias y suben la tasa
> de oscilación. Ver `research.md` Decisión 2.

**Significado de `n_gracia_busqueda`**: número de fotogramas que el robot sigue buscando hacia el
último lado conocido antes de emitir `DETENER`.

> **Default justificado con evidencia.** En `desarrilamiento/noReconoceIzquierda3.mp4` la desviación
> estándar de la velocidad de posición es 52.1 px/fotograma, frente a 14.5–20.0 px en `rutaIdeal`: las
> pérdidas reales se resuelven en pocos fotogramas. Una ventana de 5 captura los parpadeos sin
> permitir un giro prolongado fuera de pista. Ver `research.md` Decisión 4.

### 3.2 Posición de línea

| Clave | Tipo | Default | Rango válido | Unidad | Trazabilidad |
|-------|------|---------|--------------|--------|--------------|
| `frac_anticipacion` | float | `0.40` | `[0.0, 1.0)` | fracción del alto de la ROI | FR-001 |
| `frac_pico` | float | `0.50` | `(0.0, 1.0]` | fracción de la masa máxima | FR-004 |
| `umbral_confianza` | float | `0.35` | `[0.0, 1.0]` | adimensional | FR-006, FR-007 |

**Significado de `frac_anticipacion`**: desde qué fila de la ROI empieza la banda de lectura de la
posición. `0.40` descarta el 40 % superior de la ROI (la parte más lejana y ruidosa) y lee el tramo
cercano al robot, que es el pertinente para corregir a tiempo.

**Significado de `frac_pico`**: umbral relativo de masa que define el soporte del centroide. `0.50`
toma las columnas con al menos la mitad de la masa del pico, lo que estabiliza el centro frente a
una sola columna ruidosa.

**Significado de `umbral_confianza`**: por debajo de este valor, `valida = false` y el control entra
en modo recuperación (o `DETENER` si no hay memoria). Evita que una posición dudosa genere una
corrección.

### 3.3 Transporte

| Clave | Tipo | Default | Rango válido | Unidad | Trazabilidad |
|-------|------|---------|--------------|--------|--------------|
| `mac_bluetooth` | str | `00:1B:10:21:2C:1B` | `XX:XX:XX:XX:XX:XX` (6 pares hexadecimales) | — | FR-028 |
| `timeout_transporte_s` | float | `0.20` | `> 0.0` | segundos | FR-031 |

**Significado de `mac_bluetooth`**: dirección Bluetooth del mBot, el destino del enlace RFCOMM. El
canal es el estándar del perfil Serial Port Profile (**1**) y no se configura. El default es una
**suposición de trabajo**, no un dato del docente: es la P5 de `transporte-bluetooth.md` §8.

**Significado de `timeout_transporte_s`**: cota superior de una escritura bloqueada. Acota el peor caso
si el módulo BT está desconectado; el envío ocurre fuera del bucle de visión, pero aun así acotarlo
evita que el proceso se cuelgue.

---

## 4. Reglas de validación cruzada

Se evalúan **después** de la validación individual, y también fallan en carga con
`ConfiguracionInvalidaError`:

| # | Regla | Campo en el error | Motivo |
|---|-------|-------------------|--------|
| V1 | `zona_muerta + histeresis <= 0.5` | `zona_muerta` | Con un umbral efectivo ≥ 0.5 el robot quedaría ciego a media pista y no seguiría la línea. |
| V2 | `zona_muerta - histeresis >= 0.0` | `histeresis` | Si el umbral de retorno fuese negativo, la histéresis no tendría banda y la conmutación sería ambigua. |
| V3 | `frac_anticipacion < 1.0` | `frac_anticipacion` | Una anticipación de 1.0 vaciaría la banda de lectura; `PosicionLinea` nunca podría ser válida. |
| V4 | `frac_pico > 0.0` | `frac_pico` | Un umbral de 0 tomaría toda la ROI como soporte y el centroide se iría al centroide global, no al de la línea. |
| V5 | `mac_bluetooth` con formato `XX:XX:XX:XX:XX:XX` (6 pares hexadecimales) | `mac_bluetooth` | Una MAC mal escrita no falla en carga sino en el primer `connect`, es decir en plena pista, y el síntoma es un `enviar → False` sin causa clara. Se rechaza al arrancar. |
| V6 | `timeout_transporte_s > 0.0` | `timeout_transporte_s` | Con 0 el socket quedaría en modo bloqueante infinito. |

**Relación con el borde de la zona muerta (edge case)**: la pertenencia se define inclusiva por
dentro y exclusiva por fuera, de modo que la conmutación es determinista:

| Condición | Umbral | Resultado |
|-----------|--------|-----------|
| `\|e\| <= zona_muerta - histeresis` | interior | `AVANZAR` |
| `\|e\| >= zona_muerta + histeresis` | exterior | corrección |
| intermedia | banda | se mantiene el comando anterior |

---

## 5. Ejemplo completo (archivo resultante)

```json
{
  "roi_linea": { "x": 0.15, "y": 0.10, "w": 0.70, "h": 0.45 },
  "roi_senales": { "x": 0.10, "y": 0.05, "w": 0.80, "h": 0.55 },
  "rango_hsv_linea": { "h_min": 0, "h_max": 179, "s_min": 0, "s_max": 255, "v_min": 0, "v_max": 110 },
  "rangos_hsv_rojo": [
    { "h_min": 0, "h_max": 10, "s_min": 120, "s_max": 255, "v_min": 90, "v_max": 255 },
    { "h_min": 170, "h_max": 179, "s_min": 120, "s_max": 255, "v_min": 90, "v_max": 255 }
  ],
  "rango_hsv_verde": { "h_min": 45, "h_max": 85, "s_min": 100, "s_max": 255, "v_min": 70, "v_max": 255 },
  "kernel_morfologico_px": 5,
  "area_minima_rel": 0.001,
  "n_confirmacion": 3,
  "k_tolerancia": 2,
  "x_rearme": 5,
  "t_parada_s": 3.0,
  "presupuesto_latencia_frames": 8,
  "fps_objetivo": 30.0,
  "vertices_objetivo": 8,
  "tolerancia_vertices": 1,
  "aspecto_min": 0.70,
  "aspecto_max": 1.40,

  "x_objetivo": 0.5,
  "frac_anticipacion": 0.40,
  "frac_pico": 0.50,
  "umbral_confianza": 0.35,
  "zona_muerta": 0.10,
  "histeresis": 0.03,
  "n_gracia_busqueda": 5,
  "mac_bluetooth": "00:1B:10:21:2C:1B",
  "timeout_transporte_s": 0.20
}
```

Los nueve valores nuevos son los defaults documentados. **El archivo no se modifica en esta spec**:
los defaults del código ya permiten correr sin tocar la configuración, y el archivo versionado se
actualizará solo si el equipo decide fijar valores distintos del default (p. ej. un
`x_objetivo` recalibrado con el robot montado, o la MAC real del mBot de pista).

---

## 6. Calibración pendiente (documentada, no resuelta en software)

| Parámetro | Estado | Cómo se resolverá |
|-----------|--------|-------------------|
| `x_objetivo` | **Provisional (0.5)** | Recalibrar con footage del robot montado; registrar el valor medido y su incertidumbre. |
| `zona_muerta` | **Provisional (0.10)** | Recalibrar con cámara fija; verificar que la tasa de correcciones baja sin descarrilamiento. |
| `histeresis` | **Provisional (0.03)** | Ajustar según la respuesta real de los motores. |
| `n_gracia_busqueda` | **Provisional (5)** | Ajustar al tiempo de giro real del robot (cinemática definida por el docente). |
| `mac_bluetooth` | **Pendiente (suposición de trabajo)** | El default `00:1B:10:21:2C:1B` no es un dato del docente: hay que confirmarlo con él (P5 de `transporte-bluetooth.md` §8) y corregirlo aquí. |

**Principio VI**: estos vacíos se registran en `AGENTS.md` §27 como pendientes, no se asumen en
silencio. La Constitución lo exige expresamente para los valores que deja al docente.

---

## 7. Trazabilidad

| FR | Parámetros |
|----|------------|
| FR-005 | `x_objetivo` (validación de rango) |
| FR-010 | `frac_anticipacion` |
| FR-013 | `zona_muerta`, `histeresis` (+ reglas V1, V2) |
| FR-007 | `frac_pico`, `umbral_confianza` (+ reglas V3, V4) |
| FR-019 | `n_gracia_busqueda` |
| FR-028 | `mac_bluetooth` (+ regla V5) |
| FR-031 | `timeout_transporte_s` (+ regla V6) |
| FR-038 | Toda la tabla: centralizados, documentados, modificables sin tocar lógica |
