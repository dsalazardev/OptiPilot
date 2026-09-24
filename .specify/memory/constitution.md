# OptiPilot Constitution

<!--
Sync Impact Report
- Version change: 1.0.0 → 2.0.0
- Modified principles: VI. «Trazabilidad Documental y Proceso OpenSpec» → VI. «Trazabilidad
  Documental y Proceso de Planificación (Spec Kit)»
- Modified sections: Governance (herramienta vigente y enmiendas); Flujo de Desarrollo y Puertas de
  Calidad (evidencia de estado con artefactos de Spec Kit)
- Added sections: ninguna
- Removed sections: ninguna
- Rationale: reconocer Spec Kit (adoptado en el commit `docs(spec-kit)`; constitución en
  `.specify/memory/constitution.md`; artefactos en `specs/###-feature/`) como herramienta activa de
  gobernanza y planificación; OpenSpec pasa a herramienta complementaria sin duplicar trabajo.
  Bump MAJOR por redefinición del flujo de gobernanza exigido (Principio VI).
- Follow-up TODOs: alinear las referencias a OpenSpec en `AGENTS.md` en un cambio subsecuente.
- Historial: v1.0.0 (2026-09-24) — ratificación inicial (6 principios, restricciones técnicas y
  puertas de calidad).
-->

## Core Principles

### I. Restricción Técnica Absoluta: Visión Clásica (NON-NEGOTIABLE)

Todo algoritmo del proyecto MUST construirse exclusivamente con las técnicas autorizadas por el
Reto 1 (enumeradas en «Restricciones Técnicas y de Plataforma»). Queda terminantemente prohibido
usar: redes neuronales artificiales, deep learning, modelos preentrenados, detectores YOLO/SSD/
Faster R-CNN o equivalentes, cascadas Haar, servicios externos de IA, y cualquier algoritmo o
biblioteca que detecte automáticamente la línea o las señales sin que el equipo implemente la
lógica. Toda dependencia nueva MUST justificarse como primitiva de propósito general y MUST NOT
delegar la decisión de detección.

Una violación de este principio no admite trade-off: es un «No cumple» directo en los criterios 5
y 6 de la rúbrica e invalida el entregable.

**Rationale**: la rúbrica califica como «No cumple» el uso de deep learning, cascadas Haar o
modelos preentrenados; cumplir esta restricción es condición de existencia del proyecto, no una
preferencia técnica.

### II. Arquitectura de Pipeline Explícito por Etapas

El sistema MUST organizarse como un pipeline de etapas explícitas y desacopladas: captura de cámara
→ preprocesamiento y reducción de ruido → segmentación (color, umbralización, K-Means básico) →
detección y análisis de contornos → cálculo de la posición de la línea respecto al centro →
control de trayectoria → detección e identificación de señales (octágonos) → máquina de estados
PARE/SIGA → registro de métricas.

Cada etapa del pipeline MUST:

- residir en un módulo o conjunto de funciones con una única responsabilidad dentro de `src/`, con
  contrato de entrada/salida claro;
- implementar su lógica en el proyecto; la biblioteca aporta primitivas autorizadas, nunca la
  decisión;
- documentar en el código qué técnica autorizada implementa y con qué propósito (alimenta la
  explicación del póster y la defensa oral);
- poder inspeccionarse aisladamente mediante sus salidas intermedias (máscaras, contornos, imágenes
  anotadas), porque la solución MUST ser explicable etapa por etapa.

MUST NOT existir capas, paquetes ni abstracciones sin una responsabilidad real: la estructura se
justifica por el pipeline, no por nombres de carpetas (`src/models/` y `src/services/` no
constituyen arquitectura mientras nada los defina).

**Rationale**: el reto exige justificar cómo el algoritmo identifica la línea, reconoce las señales
y controla el robot (criterios 5, 9 y 12 de la rúbrica); un pipeline explícito es la única forma
verificable de lograrlo.

### III. Organización del Código y Dependencias Reproducibles

- El runtime declarado en `pyproject.toml` (`requires-python`) es Python ≥3.14, sobre un venv
  gestionado con uv (`.venv`), que MUST NOT versionarse.
- Toda dependencia MUST declararse en `pyproject.toml` antes de importarse y instalarse con uv en
  el venv local. MUST NOT importarse paquetes no declarados ni asumirse su presencia.
- Las dependencias del material de clase (por ejemplo `cv2` y `sklearn` en los notebooks) MUST NOT
  tratarse como dependencias del producto por defecto; se adoptan solo cuando un cambio lo
  justifique.
- Las dependencias que automaticen la detección de la línea o las señales quedan prohibidas por el
  Principio I, aunque sean «herramientas de visión» convencionales.
- El código MUST organizarse por etapa del pipeline, con nombres claros y en el idioma del dominio;
  los comentarios de etapa que nombran la técnica autorizada son parte del estándar de calidad.
- MUST NOT commitear: `.venv`, `.env`, secretos, tokens, ni cachés generadas.
- Los árboles generados para agentes MUST regenerarse con su herramienta; MUST NOT editarse a mano.

**Rationale**: hoy no hay dependencias declaradas ni lockfile, y el venv no ejecuta ni el material
del curso (falta OpenCV): sin disciplina de dependencias, el proyecto no es reproducible ni
auditable.

### IV. Tiempo Real y Comportamiento Determinista

La lógica de decisión MUST ser determinista y apta para el bucle de tiempo real a la tasa de la
cámara:

- sin fuentes de azar no controladas (en K-Means, fijar semilla y parámetros de forma explícita);
- sin operaciones bloqueantes ni cómputo pesado innecesario en el camino crítico;
- con tolerancia a fallos: la pérdida momentánea de la línea o de una señal MUST tolerarse sin
  descarrilamiento, y el sistema SHOULD recuperar la trayectoria de forma autónoma.

La máquina de estados MUST ser explícita y auditable (al menos: EN MARCHA, DETENIDO POR PARE,
REANUDACIÓN/RECUPERACIÓN), con transiciones documentadas. Umbrales, velocidades y tiempos MUST ser
parámetros configurables y documentados, nunca números mágicos dispersos.

Los valores que el reto deja al docente (duración de la parada PARE — «el tiempo establecido por el
docente» — y número de intentos) MUST exponerse como configuración y confirmarse con el docente.
MUST NOT asumirse en silencio.

**Rationale**: la competencia puntúa tiempo total, descarrilamientos, intervención manual y
capacidad de recuperación; un comportamiento repetible y parametrizado es lo que permite mejorar
esas métricas y explicarlas.

### V. Calidad Verificable: Pruebas y Evidencia Medible

- Toda lógica determinista (umbrales de segmentación, geometría de contornos, cálculo de posición,
  control y transiciones de la máquina de estados) MUST poder probarse sin hardware, con imágenes
  sintéticas y/o fotogramas de los videos de práctica.
- Las pruebas MUST ser headless (sin cámara ni GUI). Al introducir el primer test, su runner MUST
  declararse en `pyproject.toml` y los comandos MUST documentarse en el mismo cambio.
- Cada etapa del pipeline MUST validarse con imágenes o video reales antes de integrarse; la
  validación final de referencia es la ejecución en pista.
- Las métricas de la rúbrica (tiempo de recorrido, cumplimiento PARE y SIGA, descarrilamientos,
  intervenciones humanas, recuperación de trayectoria) MUST registrarse y reportarse con honestidad.
- MUST NOT documentarse como implementado nada que no exista ni maquillarse resultados; los vacíos
  y fallos se reportan.

**Rationale**: la rúbrica premia resultados medibles y el análisis de aciertos, errores y
limitaciones (criterios 7 y 11); sin evidencia verificable no hay puntaje, y sin pruebas la
depuración en pista se vuelve manual e inestable.

### VI. Trazabilidad Documental y Proceso de Planificación (Spec Kit)

- `documents/**` es la fuente de verdad académica del reto y MUST tratarse como material de solo
  lectura; no se reescribe sin justificación y aprobación explícitas.
- Todo trabajo no trivial MUST pasar por el flujo de planificación vigente — Spec Kit (spec → plan →
  tasks → implementación; artefactos en `specs/###-feature/`) —; la implementación se realiza solo
  cuando existen tareas aprobadas. OpenSpec se mantiene como herramienta complementaria y no se
  duplica el trabajo entre ambos flujos.
- Cada cambio MUST declarar qué etapas del pipeline implementa y qué técnicas autorizadas usa; esa
  trazabilidad alimenta el póster, la defensa oral y la revisión de cumplimiento.
- Los vacíos, conflictos o inconsistencias documentales MUST registrarse (por ejemplo, en la
  sección de inconsistencias de `AGENTS.md`) en lugar de resolverse en silencio.
- `AGENTS.md` MUST actualizarse en el mismo cambio que modifique el estado real del proyecto.

**Rationale**: el proyecto separa documentación, planificación y código; sin trazabilidad no es
posible explicar ni auditar la solución ante la rúbrica (criterios 5, 9, 10 y 11).

## Restricciones Técnicas y de Plataforma

**Caja de herramientas autorizada (normativa; Reto 1)**: operaciones lógicas y aritméticas sobre
imágenes; conversión entre espacios de color (RGB, HSV, CIELab); recorte de regiones de interés
(ROI); redimensionamiento y rotación de imágenes; umbralización; segmentación por color; K-Means en
su modalidad básica; operaciones morfológicas (erosión, dilatación, apertura y cierre); suavizado y
reducción de ruido; detección de bordes mediante Canny; detección y análisis de contornos;
identificación de formas geométricas simples; propiedades básicas de contornos (área, perímetro,
centroide, aproximación poligonal, relación de aspecto).

**Técnicas y herramientas prohibidas (normativa; Reto 1)**: redes neuronales artificiales; deep
learning; modelos previamente entrenados; detectores basados en YOLO, SSD, Faster R-CNN o
equivalentes; cascadas Haar; servicios externos de inteligencia artificial; algoritmos o
bibliotecas que realicen automáticamente la detección de la línea o las señales sin que el equipo
implemente la lógica correspondiente.

**Plataforma y entorno**:

- Runtime: Python ≥3.14 (venv gestionado con uv, sin `pip` propio del venv); sin lockfile por
  ahora; si se adopta uno, MUST documentarse.
- Entorno verificado (2026-09-24): `numpy`, `scipy`, `scikit-learn`, `matplotlib` y `pillow`
  instalados; **OpenCV no está instalado ni declarado**. Todo cambio que requiera `cv2` MUST
  declararlo e instalarlo en el mismo cambio.
- Hardware del robot, cámara y canal de comunicación: **no definidos en el repositorio**. MUST
  decidirse y documentarse en el cambio que los necesite; MUST NOT asumirse interfaces.
- Entorno de desarrollo Windows 11 con el repositorio dentro de OneDrive: evitar rutas largas y
  binarios pesados versionados; `.venv` está excluido de git (aunque OneDrive lo sincronice).

## Flujo de Desarrollo y Puertas de Calidad

**Antes de implementar** (basado en la checklist operativa de `AGENTS.md`):

1. Verificar el estado real con evidencia (archivos, `git`, artefactos de `specs/`) y clasificarlo
   (implementado / parcial / solo documentado / planificado / indeterminado); está prohibido
   promover documentación a «implementado».
2. Confirmar que el cambio usa cero técnicas prohibidas y solo técnicas autorizadas; ante duda,
   consultar antes de avanzar.
3. Revisar el material del curso correspondiente (Fundamentos, K-Means, notebooks) cuando el cambio
   implemente una etapa de visión.
4. Identificar los archivos a tocar; no editar materiales académicos, archivos generados de agentes
   ni placeholders sin decisión explícita.

**Implementación y validación**:

5. Cada tarea corresponde a una etapa identificable del pipeline y declara la técnica autorizada
   que implementa.
6. Pruebas headless de la lógica determinista y validación con footage real; prohibido inventar
   resultados.
7. Medición de las métricas de la rúbrica cuando el cambio afecte el comportamiento en pista.

**Calidad académica de la solución**:

8. Explicabilidad: cualquier integrante del equipo MUST poder explicar cada etapa y cada decisión
   (criterios 9 y 12 de la rúbrica).
9. Diferenciación: las decisiones MUST justificar una estrategia propia y documentar en qué se
   distingue de las soluciones convencionales (criterio 8).
10. Evidencia para entregables: la documentación de etapas y resultados MUST bastar para construir
    el póster y el análisis de resultados (criterios 10 y 11).

## Governance

- Esta constitución prevalece sobre las demás prácticas del repositorio. Para hechos de
  comportamiento rige el orden: código/configuración > pruebas > documentos funcionales >
  notebooks > comentarios > historial. Para requisitos y restricciones, los documentos oficiales
  del reto prevalecen sobre todo lo demás, incluido el código: código que viole el Reto 1 es no
  conforme por definición.
- **Enmiendas**: toda modificación requiere (a) propuesta documentada (un cambio en el flujo vigente
  —Spec Kit— o justificación equivalente), (b) aprobación del responsable del proyecto, (c) plan de
  migración cuando cambie prácticas existentes, y (d) incremento de versión con actualización de
  `Last Amended` en la línea de versión.
- **Versionado semántico**: MAJOR para eliminación o redefinición incompatible de principios o
  gobernanza; MINOR para un nuevo principio, sección o expansión material; PATCH para aclaraciones
  y correcciones sin cambio de significado.
- **Herramienta vigente de gobernanza**: Spec Kit es la herramienta activa de planificación y
  trazabilidad (constitución en `.specify/memory/constitution.md`; especificaciones, planes y tareas
  en `specs/`). Sus comandos y artefactos (`/speckit.*`) son el mecanismo de gobernanza de los
  cambios; OpenSpec queda disponible para su propio ciclo, sin obligación de duplicación.
- **Revisión de cumplimiento**: toda revisión o PR MUST verificar el cumplimiento de los
  principios. Las violaciones que la constitución permite justificar MUST justificarse
  explícitamente en la sección Complexity Tracking del plan; en caso contrario, el cambio no se
  aprueba. Una violación del Principio I MUST NOT justificarse: el cambio se rechaza.
- `AGENTS.md` es la guía operativa de runtime para los agentes; ante conflicto con esta
  constitución prevalece la constitución, y `AGENTS.md` MUST actualizarse en el mismo cambio.
- Los vacíos del reto dependientes del docente (duración de PARE, geometría de la pista, número de
  intentos) MUST registrarse como riesgos y resolverse con el docente; MUST NOT silenciarse.

**Version**: 2.0.0 | **Ratified**: 2026-09-24 | **Last Amended**: 2026-09-24
