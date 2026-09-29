# AGENTS.md — OptiPilot

**Bootstrap and operating manual for AI agents working in this repository.**

- **Generated:** 2026-09-22 (de una inspección de solo lectura del repositorio).
- **Última actualización:** 2026-09-28, tercera pasada del mismo día. La anterior registró el **cambio de protocolo de transporte** ordenado por el profesor; esta cierra la feature 002 (transporte, compositor, cola, métricas, cableado e integración) con la app lista para la pista.
- **Basis:** rama `feature/002-control-trayectoria`. Commits: `b2ea2f5` (spec 002), `3ddee48` (US1, estimador), `8341f04` (US2/US3, control), `8647132` (compositor + spp ASCII). La cola de transporte, las métricas de control, el cableado de `main.py` y los tests de integración/footage están **sin commitear**.
- **Language:** este documento está en inglés (estándar para archivos bootstrap de agentes); el material de origen del proyecto está en español. Conserva en español los términos del dominio: *Reto 1, PARE, SIGA, rúbrica, descarrilamiento*.

---

## 0. Read this first

Read order for a new agent joining this project:

| # | Read | Why |
|---|------|-----|
| 1 | This file, end to end | State, constraints, rules |
| 2 | `documents/markdawn/Reto-1.md` | The functional specification of what will be built |
| 3 | `documents/markdawn/Rubrica-Reto-1.md` | How the work is evaluated (12 criteria) |
| 4 | `documents/markdawn/FundamentosVisionArtificial.md` + `documents/markdawn/18-K-MEANS-Basico.md` | The allowed technique toolbox (course material) |
| 5 | `specs/001-cv-sign-detection/`, then `openspec/config.yaml` | The Spec Kit feature that carries the work, and the idle OpenSpec config |
| 6 | `pyproject.toml`, `src/**`, `tests/**` | The actual code and test state |

Re-verification quick commands (run from the repo root):

```bash
git rev-parse --abbrev-ref HEAD   # expect: feature/002-control-trayectoria
git status --short                # working tree state
uv run pytest -q                  # full suite (428 passed, 12 skipped)
openspec list --json              # active OpenSpec changes
openspec --version                # CLI version
```

---

## 1. Project Overview

**OptiPilot** is the working name (appears only in `pyproject.toml` and `.idea/optipilot.iml`; there is no README) of an academic software project whose goal is the **"Reto 1" of a computer-vision course at Universidad de Caldas**: the *brain* of an autonomous line-following robot that uses a camera, classical image processing only, and must react to two traffic signs (red octagon = **PARE** / stop; green octagon = **SIGA** / go).

**Current reality (do not skip):** the repository contains **a working, tested implementation** of the vision pipeline, the deterministic state machine, run metrics, a validation CLI, trajectory control, the safety compositor, the transport queue, and 428 automated tests. What does **not** exist yet: the annotated reference corpus needed to score SC-010, the teacher's stop duration, the poster, and validation against the real robot (the RFCOMM link has never run on hardware).

**Status snapshot**

| Area | State | Evidence |
|------|-------|----------|
| Academic materials (challenge, rubric, class decks, notebooks) | Present — source of truth | `documents/**` |
| CV pipeline (preprocess → segment → candidates → confirm) | **Implemented** | `src/vision/{preprocesamiento,segmentacion,candidatos,deteccion,pipeline}.py` |
| Deterministic FSM (PARE stops, SIGA resumes) | **Implemented** | `src/vision/maquina_estados.py` |
| Run metrics + visualization + validation CLI | **Implemented** | `src/vision/metricas.py`, `visualizacion.py`, `src/main.py` |
| Tests | **Present** — 428 passing (342 unit, 86 integration) | `tests/unit/`, `tests/integration/` |
| Reference annotation corpus (SC-010 ground truth) | **Absent** — required by `contracts/anotacion-referencia.md` §2 | no `anotacion_linea.json` in the repo |
| Real footage | **Absent in this copy** — was never tracked (`.gitignore:180` ignores `videos/`); 9 portrait 478×850 videos documented but not present | no `documents/videos/` on disk |
| Signal detection on real footage | **Not demonstrated** — 0 confirmations observed | see §27 |
| Bluetooth link to the mBot (US4) | **Partially implemented** — `TransporteSPP` sends one ASCII byte over RFCOMM; never run against real hardware | `src/transporte/spp.py` |
| `ColaTransporte` / `TransporteSimulado` | **Absent** — T027, T028, T030 pending | no `src/transporte/{cola,simulado}.py` |
| CI/CD for the product | Absent; 1 generated Copilot-setup workflow | `.github/workflows/copilot-setup-steps.yml` |
| Python environment | Complete: CPython 3.14 + OpenCV + NumPy + pytest, **zero third-party deps for the robot link** | `.venv/`, `pyproject.toml` |
| Git | Feature 002 on `feature/002-control-trayectoria`; `main`/`dev` still at Fase 2 | `git log`, `git branch -av` |

---

## 2. Project Purpose and Context

- **Domain:** mobile robotics + classical computer vision (image processing), real-time decision making.
- **Academic context:** course material is authored by *Felipe Buitrago Carmona — Facultad Inteligencia Artificial e Ingenierías, Universidad de Caldas* (visible on every page of the PDF/PPTX materials). The commit author is *Daner Alejandro Salazar Colorado* and the single commit is titled "add a documents of class" — the repo is the student workspace for the course challenge. **«INFERENCE»** from those two facts; no other context file exists.
- **Deliverables of the challenge** (see §3): a visual poster/material + a live robot demonstration in a competition.
- **Hard constraint:** the challenge forbids deep learning and any "auto-detection without your own logic" (see §10–§11). Any agent that introduces such techniques makes the project non-compliant by definition.

---

## 3. Reto 1 — Functional and Academic Context

Sources (equivalent content; verified line-by-line against each other): `documents/markdawn/Reto-1.md` ≡ `documents/documents/Reto-1.docx`; `documents/markdawn/Rubrica-Reto-1.md` ≡ `documents/documents/Rubrica-Reto-1.xlsx`. No contradictions found between the markdown transcriptions and the binary originals.

**General objective (verbatim from Reto-1):**

> "Diseñar e implementar un algoritmo de visión artificial que permita a un robot móvil seguir una línea sobre una pista, corregir su trayectoria y reconocer señales representadas mediante octágonos rojos y verdes, sin utilizar técnicas de aprendizaje profundo."

**Specific objectives (7, summarized):**

1. Capture and analyze images from the robot's camera.
2. Identify the guide line via image processing/segmentation.
3. Compute the line's position relative to the robot's center.
4. Generate control actions to correct trajectory and avoid derailing (*descarrilamiento*).
5. Detect and identify the red and green octagons at different points of the track.
6. Stop on PARE; resume on SIGA.
7. Compare the strategy against other teams; explain advantages, limitations, improvements.

**The signals**

| Signal | Appearance | Required behavior |
|--------|-----------|-------------------|
| PARE | Red octagon | Robot stops for "the time established by the teacher" — duration is **not specified anywhere in the repo** (undetermined; see §28) |
| SIGA | Green octagon | Robot resumes its run |

**Deliverables:** (1) a poster or visual material showing methodology, processing stages, and results; (2) a practical demonstration during the competition.

**Competition scoring factors (from Reto-1):** total time to complete the track; PARE compliance; SIGA compliance; number of derailments; need for manual intervention; ability to recover the trajectory.

**Provided resources:** a Google Drive folder with practice videos (link inside `Reto-1.md`: `https://drive.google.com/drive/folders/1m6mazLjCKPlwaVpH-arGSYZMF_P2KC77`) — external, not in the repo, useful as test footage.

---

## 4. Reto 1 — Evaluation Rubric

`documents/markdawn/Rubrica-Reto-1.md` (≡ the `.xlsx`). 12 criteria; each evaluated as *Cumple / Cumple parcialmente / No cumple* (thresholds of "1–3" vs "more than 3" errors described inline in the source):

1. **Corrección de trayectoria** — timely corrections, stable trajectory.
2. **Intervenciones humanas** — 0 interventions for full compliance.
3. **Reconocimiento señal PARE** — correct in all occurrences.
4. **Reconocimiento señal SIGA** — correct in all occurrences.
5. **Uso de técnicas de visión artificial** — correct, integrated, and *justified* use of allowed techniques.
6. **Cumplimiento de las restricciones** — 0 unauthorized techniques; **using deep learning, Haar cascades, or pretrained models is explicitly a "No cumple"**.
7. **Tiempo de recorrido** — "Menor tiempo, mayor puntaje" (the only criterion with no partial levels).
8. **Diferenciación de la estrategia** — the approach must differ clearly from other teams'.
9. **Comunicación verbal** — explain methodology, decisions, results.
10. **Póster o presentación visual** — all stages, techniques, and results clearly shown.
11. **Análisis de resultados** — successes, errors, difficulties, limitations, improvements.
12. **Participación del equipo** — every member understands and can explain the solution.

**What this means for coding decisions:** code must be *explainable stage-by-stage* (criterion 5/9), the strategy should be distinctive (criterion 8), and results must be measurable/reportable (criteria 7/11).

---

## 5. Current Project State

Classification of everything in the repo (the distinction between documentation and implementation is critical here):

**Implemented**
- Git repository; feature 002 work on branch `feature/002-control-trayectoria` (`origin/main` remains at Fase 2).
- PyCharm project files (`.idea/**`).
- Spec Kit installation (`.specify/**`, 21 tracked files) — the tool that produced `specs/**`.
- OpenSpec initialization (`openspec/config.yaml`; `specs/` and `changes/archive/` empty with `.gitkeep`).
- OpenSpec-generated agent tooling for 4 tool targets (§22–23).
- Academic material set in `documents/**` (available, not authored by the repo owner).
- **Full CV pipeline** in `src/vision/`, stage by stage, all using allowed techniques only:
  - `preprocesamiento.py` — Gaussian blur (5×5), BGR→HSV, ROI cropping (T009).
  - `segmentacion.py` — HSV `inRange` masks for line/red/green, morphological open+close (T010).
  - `candidatos.py` — `findContours` + `approxPolyDP`, area/aspect/vertex filters (T011).
  - `deteccion.py` — temporal confirmation (N=3) with tolerance K=2 and re-arm (T012).
  - `pipeline.py` — orchestration, degradation, per-stage diagnostics (T013).
  - `maquina_estados.py` — deterministic FSM; PARE stops, SIGA resumes (T018).
  - `posicion_linea.py` — `EstimadorLinea`: lateral line position, band, dominant peak, anticipation; **consumes `mascara_linea`** (002/US1).
  - `control_trayectoria.py` — bang-bang with hysteresis, recovery, safe fallback (002/US2-3).
  - `compositor.py` — 3-level safety arbitration; FSM veto always ⟹ `DETENER` (T025).
  - `metricas.py` / `visualizacion.py` — run metrics and annotated frames (T020–T021).
- **Transport link** in `src/transporte/`: `base.py` (`Protocol Transporte`, no I/O), `spp.py` (`TransporteSPP`, one ASCII byte per command over RFCOMM; the only file that opens a socket), `simulado.py` (`TransporteSimulado`, test double) and `cola.py` (`ColaTransporte`, the decoupling queue). The CLI wires them via `--transporte {simulado,spp}` and drains in a background thread.
- Control metrics (`MetricasControl` in `metricas.py`) and the control evidence in `visualizacion.py`.
- Configuration in `config/vision.json`, validated on load by `configuracion.py`.
- Validation CLI `src/main.py` (`--fuente`, `--config`, `--diagnostico`, `--salida`, `--max-fotogramas`, `--anotacion`).
- 428 automated tests: 342 unit (`tests/unit/`) + 86 integration (`tests/integration/`).

**Documented but NOT implemented** (the robot/actuator boundary)
- Any camera capture on the real robot (the CLI opens files/indices; the camera is untested).
- Motor/actuator control: the FSM emits `DecisionMovimiento` *verdicts*, nothing drives wheels.
- The annotated reference corpus (`anotacion_linea.json` + PNG masks) for SC-010.
- The poster / visual material.
- PARE stop duration is provisional (`t_parada_s: 3.0`), pending the teacher's value.

**Planned / configured**
- Spec Kit (`.specify/`, workflow `speckit`) is the tool that carried the work; OpenSpec is initialized but idle (no changes, no specs).
- GitHub Copilot cloud-agent support is enabled (`openspec/config.yaml` → `githubCopilot.cloudAgent: true`).

**Undetermined**
- Robot platform/hardware, camera model, communication interface.
- PARE stop duration; track/sign geometry; team composition; poster format.
- Whether `src/models/` and `src/services/` are meant as architecture layers — the folders still contain only 0-byte `__init__.py`; the real code lives in `src/vision/`. Do **not** treat their names as evidence of an architecture.

---

## 6. Repository Structure

Real tree (79 tracked files; `.venv/` and `.git/` are local/ignored artifacts shown for completeness, size on disk at generation time: `.venv` ≈ 234 MB, `.git` ≈ 14 MB):

```text
OptiPilot/
├── .agents/                       # OpenSpec-generated agent tooling (target: "antigravity")
│   ├── skills/.openspec-target    #   contains the single word: antigravity
│   ├── skills/openspec-{apply-change,archive-change,explore,propose,sync-specs,update-change}/SKILL.md
│   └── workflows/opsx-{apply,archive,explore,propose,sync,update}.md
├── .claude/                       # OpenSpec-generated (target: Claude Code, colon syntax)
│   ├── commands/opsx/{apply,archive,explore,propose,sync,update}.md
│   └── skills/openspec-*/SKILL.md
├── .github/                       # OpenSpec-generated (GitHub Copilot)
│   ├── agents/openspec.agent.md
│   ├── prompts/opsx-{...}.prompt.md
│   ├── skills/openspec-*/SKILL.md
│   └── workflows/copilot-setup-steps.yml
├── .idea/                         # PyCharm project (7 tracked files; workspace.xml untracked)
├── .opencode/                     # OpenSpec-generated (OpenCode)
│   ├── commands/opsx-{...}.md
│   └── skills/openspec-*/SKILL.md
├── .venv/                         # local uv venv, Python 3.14.7 — git-ignored, NOT part of the repo
├── config/                        # vision.json — the only runtime configuration
│   └── vision.json
├── documents/                     # academic source material (16 MB)
│   ├── documents/                 #   binaries: Reto-1.docx, Rubrica-Reto-1.xlsx,
│   │                              #   18-K-MEANS-Basico.pptx, FundamentosVisionArtificial.pdf
│   ├── ipynb/                     #   4 class notebooks (Colab-style)
│   ├── markdawn/                  #   markdown transcriptions (folder name is a typo of "markdown";
│   │                              #   kept as-is — do not rename without an explicit decision)
│   └── videos/                    #   9 practice videos documented but ABSENT in this copy:
│                                  #   never tracked (`.gitignore:180` ignores `videos/`)
├── openspec/                      # config.yaml + specs/ + changes/archive/ (specs & changes empty with .gitkeep)
├── specs/                         # Spec Kit features (NOT OpenSpec) — 001-cv-sign-detection/ is the live record
├── .specify/                      # Spec Kit installation: constitution, templates, PS scripts, workflows
├── src/                           # Python package — see §11 for the real layout
├── tests/                         # unit/ (92) + integration/ (80 frozen) — see §18
├── .gitignore                     # Toptal "python" template (see §14)
├── pyproject.toml                 # deps and pytest config
└── uv.lock                        # versioned lockfile (committed)
```

Missing on purpose/absence: no `README*`, no `LICENSE`, no `CONTRIBUTING`, no product CI workflows.

---

## 7. Technology Stack

| Layer | What is actually used | Evidence |
|-------|----------------------|----------|
| Language | Python — declared `>=3.14` | `pyproject.toml` → `requires-python` |
| Local runtime | CPython **3.14.7**, uv-managed venv | `.venv/pyvenv.cfg`, `.venv/Scripts/python.exe --version` |
| Dependency management | Declared: `numpy>=2.4`, `opencv-python-headless>=4.13`; dev group: `pytest>=8`. `pyserial` was added then **removed** within the same day when the real protocol turned out to be RFCOMM | `pyproject.toml`, `uv.lock` |
| Computer vision | **OpenCV** (`opencv-python-headless`) — `cvtColor`, `inRange`, `morphologyEx`, `findContours`, `approxPolyDP`, `arcLength`, `boundingRect`, `VideoCapture`, `imwrite` | `src/vision/**`, `src/main.py` |
| Numerics | NumPy — masks as boolean/uint8 arrays, ROI boolean algebra | `src/vision/**` |
| Tests | pytest with two custom markers: `footage` (opt-in real video) and `perf` (benchmark) | `pyproject.toml` → `[tool.pytest.ini_options]` |
| Agent/workflow tooling | OpenSpec CLI **1.13.1** (`npm install -g @fission-ai/openspec`); generated files stamped `generatedBy: "1.13.1"` | CLI output, skill frontmatter, `.github/workflows/copilot-setup-steps.yml` |
| IDE | PyCharm (project SDK pinned to the local `.venv`) | `.idea/` |
| VCS | Git, branches `main` and `dev`, remote GitHub `dsalazardev/OptiPilot` | `git remote -v`, `git log` |
| OS/workspace | Windows 11; repo lives on `D:` (formerly OneDrive) | paths, `.venv` size note |

No build system beyond setuptools defaults; no formatter/linter configured (see §19).

---

## 8. Architecture and Application Flow

**Actual architecture: a linear stage pipeline, not a layered one.** `src/vision/` is the real package; its modules correspond one-to-one to the stages of Reto 1 and are wired in order by `PipelineVision`. `src/transporte/` is a second, deliberately separate package: it is the only place allowed to touch the network. `src/models/` and `src/services/` remain 0-byte package markers and are **not** part of the design.

**Actual application flow: implemented as a validation CLI, not as a robot controller.** The stages run per frame:

```text
frame (video / directory / camera index)
   │
   ▼ Preprocesador    Gaussian blur 5×5 → BGR2HSV → crop ROI línea / ROI señales
   │
   ▼ Segmentador      inRange HSV (línea, rojo, verde) → open+close → máscaras
   │
   ▼ ExtractorCandidatos  findContours → area/aspecto → approxPolyDP (8±1 vértices)
   │
   ▼ Confirmador      N=3 consecutive, tolerancia K=2, re-arm tras x_rearme
   │
   ▼ MaquinaEstados   SIGA → PERMITIR · PARE → DETENIDO (durante T) → SIGA → reanudar
   │
   ├─▶ MetricasCorrida    eventos, decisiones, tiempos → metricas.json
   └─▶ Visualizador       frames anotados (--diagnostico) → SC-012
```

The robot/actuator boundary is still open: `MaquinaEstados` emits `DecisionMovimiento` **verdicts** (with an explicit `causa`), and nothing yet drives wheels. Treat the following as the target behavior only, never as current state: camera acquisition on the real robot, motor control, and recovery from *descarrilamiento*.

---

## 9. Computer Vision Context — Technique Inventory

Where each element of the allowed toolbox actually appears today:

| Technique / concept | Where it is taught/shown | In `src/`? |
|---|---|---|
| Image as matrix; BGR channel order; pixel values | `FundamentosVisionArtificial.md` (PDF pages 1–4), notebook `1_Fundamentación.ipynb` | No |
| Color spaces RGB/HSV/CIELab + conversions (`COLOR_BGR2HSV`, `COLOR_BGR2LAB`) | `Fundamentos…md`, notebook `2_Espacios_de_Color.ipynb` | No |
| Logical/arithmetic ops: AND (`bitwise_and`), absolute difference (`absdiff`), thresholding | `Fundamentos…md`, notebook `3_OperacionesMatemáticas.ipynb` | No |
| Filters: Gaussian smoothing, Sobel, Laplacian; kernels/convolution | `Fundamentos…md` (sections *Filtros, Filtro Gaussiano*) | No |
| Edge detection: **Canny** (gradient magnitude/direction; strong/weak classification) | `Fundamentos…md` (*Algoritmo Canny*) | No |
| Morphology: dilation, erosion (and by extension opening/closing) | `Fundamentos…md` (*Operaciones Morfológicas*) | No |
| Contours: `findContours`, polygon approximation `approxPolyDP` (Douglas–Peucker), `boundingRect`, shape classification by vertex count (incl. **octágono = 8 sides**) | `Fundamentos…md` (*Detección Figuras Geométricas*) | No |
| K-Means (basic): centroids, distance, iterative assignment | `18-K-MEANS-Basico.md/.pptx`, notebook `4_Kmeans_Imagenes.ipynb` (K=3 image segmentation with sklearn) | No |
| ROI / image resize/rotate, noise reduction | listed as allowed in Reto-1; covered conceptually in the deck | No |

**«INFERENCE» (labeled):** the material's shape-classification pipeline (triangle→…→octagon by side count) lines up with detecting the octagonal PARE/SIGA signals, and notebook 4 (K-Means segmentation) lines up with color segmentation. No document states these mappings explicitly; they are natural candidate building blocks, not decided design.

---

## 10. Allowed Techniques (from Reto 1 — normative, verbatim)

> "Se permite el uso de:"
>
> - Operaciones lógicas y aritméticas sobre imágenes.
> - Conversión entre espacios de color como RGB, HSV y CIELab.
> - Recorte de regiones de interés.
> - Redimensionamiento y rotación de imágenes.
> - Umbralización.
> - Segmentación por color.
> - K-Means en su modalidad básica.
> - Operaciones morfológicas como erosión, dilatación, apertura y cierre.
> - Suavizado y reducción de ruido.
> - Detección de bordes mediante Canny.
> - Detección y análisis de contornos.
> - Identificación de formas geométricas simples.
> - Propiedades básicas de los contornos, como área, perímetro, centroide, aproximación poligonal y relación de aspecto.

(English gloss: logical/arithmetic ops; color-space conversions RGB/HSV/CIELab; ROI cropping; resize/rotate; thresholding; color segmentation; basic K-Means; morphology; smoothing/noise reduction; Canny; contour detection/analysis; simple geometric shape identification; contour properties — area, perimeter, centroid, polygon approximation, aspect ratio.)

Additionally: "El código deberá ser comprensible, estar organizado y permitir explicar claramente el funcionamiento de cada etapa del algoritmo."

## 11. Forbidden Techniques (from Reto 1 — normative, verbatim)

> "No se permite utilizar:"
>
> - Redes neuronales artificiales.
> - Deep learning.
> - Modelos previamente entrenados.
> - Detectores basados en YOLO, SSD, Faster R-CNN u otros métodos equivalentes.
> - Cascadas Haar.
> - Servicios externos de inteligencia artificial.
> - Algoritmos o bibliotecas que realicen automáticamente la detección de la línea o las señales sin que el equipo implemente la lógica correspondiente.

(English gloss: no neural networks, no deep learning, no pretrained models, no YOLO/SSD/Faster R-CNN-style detectors, no Haar cascades, no external AI services, and no libraries/algorithms that auto-detect the line or the signs without the team implementing the logic.)

The rubric makes violating this a **"No cumple"** in *Cumplimiento de las restricciones* ("utiliza deep learning, cascadas Haar o modelos preentrenados") and endangers *Uso de técnicas de visión artificial*.

**Practical consequence:** even "convenience" shortcuts must be scrutinized — e.g., a helper that localizes the line for you (outside the taught pipeline) can violate the last bullet. When in doubt, implement the stage explicitly and document which allowed technique it uses.

---

## 12. Source Code Organization

| File | Content | Status |
|------|---------|--------|
| `src/main.py` | Validation CLI: `argparse` with `--fuente`, `--config`, `--diagnostico`, `--salida`, `--max-fotogramas`, `--anotacion`; wires the pipeline loop, FSM, metrics, visualization; returns exit codes | **Implemented** (T022) |
| `src/vision/pipeline.py` | `PipelineVision.procesar` — orchestration, degradation, per-stage diagnostics | **Implemented** (T013) |
| `src/vision/preprocesamiento.py` | `Preprocesador.aplicar` — blur, HSV, ROI crop; degrades on empty frames (FR-014) | **Implemented** (T009) |
| `src/vision/segmentacion.py` | `Segmentador` — HSV `inRange` masks, open+close, `linea_detectada` | **Implemented** (T010) |
| `src/vision/candidatos.py` | `ExtractorCandidatos` — `findContours`, area/aspect/vertex filters, `approxPolyDP` | **Implemented** (T011) |
| `src/vision/deteccion.py` | `Confirmador` — N=3 consecutive, tolerance K=2, re-arm | **Implemented** (T012) |
| `src/vision/maquina_estados.py` | `MaquinaEstados` — deterministic FSM, `DecisionMovimiento` with explicit `causa` | **Implemented** (T018) |
| `src/vision/metricas.py` | `MetricasCorrida` — events, decisions, timings, `Referencia` scoring | **Implemented** (T020) |
| `src/vision/visualizacion.py` | Annotated frames per stage (SC-012) | **Implemented** (T021) |
| `src/vision/configuracion.py` | `ParametrosConfiguracion`, `RangoHSV`, `RectanguloNormalizado`, load-time validation | **Implemented** (T008) |
| `src/vision/posicion_linea.py` | `EstimadorLinea.aplicar` — band, dominant peak, anticipation fraction | **Implemented** (T013) |
| `src/vision/control_trayectoria.py` | `ControlTrayectoria.decidir` — bang-bang with hysteresis, recovery, safe fallback | **Implemented** (T017) |
| `src/vision/compositor.py` | `componer` — 3-level safety arbitration; FSM veto always ⟹ `DETENER` | **Implemented** (T025) |
| `src/vision/modelos.py` | Shared dataclasses/enums: `EstadoRobot`, `PermisoMovimiento`, `ClaseSenal`, `EventoDeteccion`, plus the 002 control block | **Implemented** |
| `src/transporte/base.py` | `Protocol Transporte` (no I/O): `enviar`, `cerrar`, `conectado`, `ultimo_error` | **Implemented** (T030 prerequisite) |
| `src/transporte/spp.py` | `TransporteSPP` — **the only file in the project that opens a socket**; one ASCII byte per command over RFCOMM | **Implemented** (T029) |
| `src/transporte/simulado.py` | `TransporteSimulado` — in-memory test double with `historial()` and `fallar_con(n)` | **Implemented** (T028) |
| `src/transporte/cola.py` | `ColaTransporte` — thread-safe decoupling queue; `encolar` O(1) without I/O, `drenar` FIFO | **Implemented** (T030) |
| `src/models/__init__.py` | empty | package marker; **not** an architecture layer |
| `src/services/__init__.py` | empty | package marker; **not** an architecture layer |

Entry point: `python -m src.main --fuente <ruta>`.

### 12.1 Robot link — the protocol the professor confirmed (2026-09-28)

The wire protocol **supersedes** the team's earlier design. The professor sent example
`Robot.py` code; the earlier 4-byte framed protocol with an XOR checksum over a
serial `COM` port was our own invention and is gone.

| Command | Byte | Meaning |
|---------|------|---------|
| `AVANZAR` | `w` (0x77) | go straight |
| `IZQUIERDA` | `a` (0x61) | line is on the left |
| `DERECHA` | `d` (0x64) | line is on the right |
| `DETENER` | `x` (0x78) | stop |

One byte per command, no header, no checksum, no delimiter. The link is
`socket.AF_BLUETOOTH` + `SOCK_STREAM` + `BTPROTO_RFCOMM`, channel 1, to
`mac_bluetooth` (default `f8:43:ef:13:05:37`, el mBot del equipo). `pyserial` was **removed** from
`pyproject.toml`; the robot link now has **zero** third-party dependencies.

**Unverified assumption:** exactly one byte with no trailing newline, which fits a
receiver doing `recv(1)`. `Robot.py` is not in this repository, so this could not
be checked against the source. If the receiver expects a line terminator, the fix is
one constant (`SUFIJO` in `src/transporte/spp.py`). Tracked as open question P3.

---

## 13. Documentation and Academic Materials

Mapping between originals and transcriptions (both sets are tracked; the markdown set is what agents should read — the binaries are the archival originals):

| Original (binary) | Transcription | Notes |
|---|---|---|
| `documents/documents/Reto-1.docx` | `documents/markdawn/Reto-1.md` | Challenge statement. Content verified identical. The `.md` references `media/image1.jpeg` (the track photo) but **no `media/` folder exists in the repo** |
| `documents/documents/Rubrica-Reto-1.xlsx` | `documents/markdawn/Rubrica-Reto-1.md` | 12-criteria rubric; identical content |
| `documents/documents/FundamentosVisionArtificial.pdf` | `documents/markdawn/FundamentosVisionArtificial.md` | 25-page slide deck; **most PDF pages are images** (OCR-only). Sections: fundamentals, filters, Canny, morphology, geometric-figure detection |
| `documents/documents/18-K-MEANS-Basico.pptx` | `documents/markdawn/18-K-MEANS-Basico.md` | K-Means class deck (theory + worked example) |

Notes:
- The markdown transcriptions were produced by conversion/OCR; expect small artefacts (garbled OCR fragments inside "picture text" blocks, the missing `media/` reference). When precision matters (exact restriction wording), cross-check against the binaries.
- `documents/` = 16 MB total. These are the **functional source of truth** for the challenge — treat them as read-only reference, not as scratch space.
- Folder name `markdawn` is misspelled ("markdown"). It is referenced by tooling/docs; do not rename silently.

---

## 14. Jupyter Notebooks (`documents/ipynb/`)

All four are **class materials authored for Google Colab** (embedded outputs and base64 images explain their 2.9–6.9 MB sizes). They are demonstrations, **not** project code — never import from them, never assume their dependencies exist locally.

| Notebook | Content | Key APIs taught | Caveats |
|---|---|---|---|
| `1_Fundamentación.ipynb` | Image = matrix; BGR; builds the Colombian flag with numpy and displays it | `numpy`, `cv2.cvtColor`, `matplotlib` | Colab display style |
| `2_Espacios_de_Color.ipynb` | RGB vs BGR, HSV theory (H 0–179, S/V 0–255), CIELab (L\*, a\*, b\*); conversions; loads a photo from Unsplash via `urllib` | `cv2.cvtColor(..., COLOR_BGR2HSV / COLOR_BGR2LAB)`, `cv2.imdecode` | Needed for color segmentation (line/signs) — most reusable concepts for the challenge |
| `3_OperacionesMatemáticas.ipynb` | Image subtraction theory, `absdiff` + threshold to detect differences; AND with binary masks | `cv2.absdiff`, `cv2.threshold`, `cv2.bitwise_and` | Masking concepts needed for ROI work |
| `4_Kmeans_Imagenes.ipynb` | K-Means image segmentation, K=3, sklearn | `sklearn.cluster.KMeans`, `cv2` | **Last stored execution is a failure**: `ModuleNotFoundError: No module named 'google.colab'` — it was run outside Colab. Also uses `google.colab.files.upload` (Colab-only) |

---

## 15. Configuration

- **`pyproject.toml`** (the only build/config file, verbatim, dependencies + pytest section):
  ```toml
  [project]
  name = "optipilot"
  version = "0.1.0"
  requires-python = ">=3.14"
  dependencies = ["numpy>=2.4", "opencv-python-headless>=4.13"]

  [dependency-groups]
  dev = ["pytest>=8"]

  [tool.pytest.ini_options]
  pythonpath = ["."]
  testpaths = ["tests"]
  markers = ["footage: ...", "perf: ..."]
  ```
- **`config/vision.json`**: the runtime configuration consumed by `configuracion.py` — both ROIs, the HSV ranges for line/red/green, morphology kernel, area minimum, `n_confirmacion`/`k_tolerancia`/`x_rearme`, `t_parada_s`, the latency budget, the shape filters (`vertices_objetivo`, `tolerancia_vertices`, `aspecto_min`/`aspecto_max`), and the control block: `x_objetivo`, `frac_anticipacion`, `frac_pico`, `umbral_confianza`, `zona_muerta`, `histerecis`, `n_gracia_busqueda`, `mac_bluetooth`, `timeout_transporte_s`. Loaded and validated on every run; a malformed value raises `ConfiguracionInvalidaError`. V5 validates the MAC format `XX:XX:XX:XX:XX:XX`; V6 validates the transport timeout.
- **`openspec/config.yaml`**: `schema: spec-driven`; `githubCopilot.cloudAgent: true`. Everything else (context, rules, operations) is **commented-out examples only** — the project has not filled in its OpenSpec context yet. This is the natural place to declare project context for OpenSpec workflows (a change, if done).
- **`.gitignore`**: Toptal "python" template. Ignores `.venv`, `.env`, `__pycache__/`, `.ipynb_checkpoints`, `.ruff_cache/`, `pyrightconfig.json`, coverage artefacts, etc. `.idea/` is **not** ignored (the line is commented) and IDE files are deliberately tracked, except `.idea/workspace.xml` which is excluded by `.idea/.gitignore`.
- **No `.env`.** The only environment variable the project reads is `OPTIPILOT_VIDEO_DIR`, and only in the `footage`-marked test (T027); there is no dotenv machinery. If a future stage needs env vars for the product itself, that is a new decision — document it. `uv.lock` **does** exist and is committed, so the environment is reproducible with `uv sync`.

---

## 16. Development Environment

- Windows 11 machine; the repo lives at `D:\Universidad de Caldas\Noveno semestre\Vision Artificial En Tiempo Real\OptiPilot` (it was formerly under OneDrive; that path no longer exists, and the IDE SDK path in `.idea/misc.xml` is stale as a result). The practice footage was never committed; it has since been re-obtained locally under `videos/` but stays untracked — see §27.14.
- The venv was created with **uv 0.12.15** using a uv-managed CPython 3.14.7 (see `pyvenv.cfg`). There is **no `pip` module inside `.venv`** — install extra packages with `uv pip install <pkg> --python .venv/Scripts/python.exe` (or recreate managed by uv). `uv.lock` is checked in, so the environment is reproducible with `uv sync`.
- **Resolved gap:** `import cv2` now works — `opencv-python-headless` is declared in `pyproject.toml` and installed. The class notebooks can run locally, except notebook 4's Colab-only `google.colab.files.upload` call (§14).
- PyCharm is the IDE (`.idea/`): project SDK points at `.venv`; module type derives from `pyproject.toml`.

### 16.1 `roi_linea` recalibrated against real footage (2026-09-28)

`roi_linea.y` moved from `0.55` to `0.10`. Measured on 460 sampled frames across all 9 videos (`videos/*/*.mp4`, 478×850):

| | `y=0.55` (antes) | `y=0.10` (ahora) |
|---|---|---|
| Occupancy of the ROI by the mask | 54.7 % median | **13.3 %** median |
| Widest horizontal run | 334 px | **71 px** |
| Frames with >60 % occupancy | 107 / 460 | **1 / 460** |

Why: the camera looks **down** at the track, so the guide band is contiguous in the **upper** half (`y` ≈ 100–450, 50–60 px wide, centre `x` ≈ 200–290) and narrows with distance. The lower half (`y` > 550) is near floor in shadow — fragments, not a band. The old ROI selected the shadow, which is why the mask was 235 px wide on average.

Changed together (config + code default + tests must stay in sync):
- `config/vision.json` → `roi_linea.y = 0.10`
- `src/vision/configuracion.py` → `ROI_LINEA_POR_DEFECTO` (the file mirrors the code default; keep them equal)
- `tests/fixtures/generador_sintetico.py` → `dibujar_linea_vertical` now draws inside the band `BANDA_LINEA_INICIO=0.10`..`BANDA_LINEA_FIN=0.55` instead of the bottom half
- `tests/unit/test_configuracion.py`, `tests/integration/test_rendimiento.py` → updated expected values

`roi_senales` was **not** changed. Suite after the change: `167 passed, 5 skipped`; `-m perf`: `14 passed`.

**Still open:** mask *thickness*. The measured band is ~50–70 px but the contract's reference is a ~3 px centre line, so SC-010 IoU is still not reachable (§27.12).

---

## 17. Development Commands (only verified ones)

| Purpose | Command | Source of truth |
|---|---|---|
| Sync the environment from the manifest | `uv sync` | `pyproject.toml` |
| Full test suite | `uv run pytest -q` | verified: **382 passed, 5 skipped** |
| Unit tests only | `uv run pytest tests/unit -q` | verified |
| Integration tests only | `uv run pytest tests/integration -q` | verified |
| Run with real footage (opt-in) | `OPTIPILOT_VIDEO_DIR=<dir> uv run pytest -m footage` | `tests/integration/test_footage_linea.py` |
| Benchmark suite (opt-in) | `uv run pytest -m perf` | `tests/integration/test_rendimiento.py` |
| Run the validation CLI | `uv run python -m src.main --fuente <ruta>` | `src/main.py` |
| Run against the real robot link | `uv run python -m src.main --fuente <ruta> --transporte spp` | `src/main.py` (default is `simulado`; no hardware needed) |
| Write annotated frames | `uv run python -m src.main --fuente <ruta> --diagnostico` | `src/main.py` |
| Verify OpenSpec CLI | `openspec --version` | `.github/agents/openspec.agent.md` |
| Install OpenSpec CLI (if missing) | `npm install -g @fission-ai/openspec` | `.github/workflows/copilot-setup-steps.yml` |
| List changes | `openspec list --json` | generated workflows |
| Any OpenSpec workflow step | `openspec status --change <name> --json`, `openspec instructions <artifact> --change <name> --json`, `openspec validate …`, `openspec archive …` | `.github/agents/openspec.agent.md` |
| Python version check | `.venv/Scripts/python.exe --version` | verified → 3.14.7 |

**There is no build step and no lint/format command.** Do not invent them; if you add tooling, document it here and in `pyproject.toml` (via a change).

---

## 18. Testing

- **428 tests pass** (342 unit + 86 integration) plus 12 opt-in skips. Command: `uv run pytest -q`.
- Layout: `tests/unit/` (12 files, pure logic — no image fixtures), `tests/integration/` (7 test files + `_escenarios.py` helper that replays the production loop `PipelineVision → MaquinaEstados`).
- Shared synthetic frame generator: `tests/fixtures/generador_sintetico.py` (background, vertical line, octagons, gaussian noise). Fixtures were written to draw 640×480 landscape frames, matching the documented target resolution — the real footage (478×850 portrait, absent in this copy; §27.14) would exercise **different geometries**.
- Two custom markers in `pyproject.toml`:
  - `footage` — opt-in real-video validation. Requires `OPTIPILOT_VIDEO_DIR`; **skips cleanly** when unset or when the corpus has no `anotacion_linea.json` (T027). The line-IoU path has therefore been exercised against a synthetic annotated corpus, not yet against real annotation.
  - `perf` — latency benchmark, non-blocking by default.
- Notable production bug found by T026 and fixed: `Referencia.cargar` raised `ConfiguracionInvalidaError` with a single argument while the constructor requires `(campo, motivo)`.

---

## 19. Code Quality

- Nothing configured: no ruff/black/flake8/pylint/mypy/pyright/isort/pre-commit config files or `[tool.*]` sections.
- `.gitignore` mentions `.ruff_cache/` and `pyrightconfig.json` — **template leftovers, not evidence of tooling**.
- `.idea/inspectionProfiles/Project_Default.xml` enables a PyUnresolvedReferences warning ignore for `azure.*` — IDE-side only, irrelevant to the project; do not treat as project configuration.

---

## 20. GitHub Actions and Copilot Integration

Only one workflow exists — `.github/workflows/copilot-setup-steps.yml`, **generated by OpenSpec for GitHub Copilot's coding agent** (not a product CI):

- **Triggers:** `workflow_dispatch`; `push`/`pull_request` limited to changes to the workflow file itself.
- **Job:** must be named `copilot-setup-steps` (Copilot requirement); `ubuntu-latest`, 10-minute timeout, `contents: read`.
- **Steps:** checkout → `npm install -g @fission-ai/openspec` → `openspec --version`.

Companion files: `.github/agents/openspec.agent.md` (Copilot agent persona for OpenSpec; documents the agent-compatible CLI commands incl. `--json` conventions) and `.github/prompts/opsx-*.prompt.md` (the 6 slash-style prompts). `openspec/config.yaml` sets `githubCopilot.cloudAgent: true` to enable this integration.

---

## 21. Spec Kit (the tool that actually carries the work) and OpenSpec (initialized, unused)

**Two spec-driven tools coexist here; do not confuse them.**

### 21.1 Spec Kit — where `specs/001-cv-sign-detection/` lives

- **What it is here:** the workflow that produced the delivered work. Installed in `.specify/` (21 tracked files) and first brought in by `92030fb docs(spec-kit): add sdd spec-it`; the constitution was ratified in `a9c04d6` (`.specify/memory/constitution.md`).
- **Where the work is:** `specs/001-cv-sign-detection/` (`spec.md`, `plan.md`, `research.md`, `data-model.md`, `tasks.md`, `quickstart.md`, `contracts/`, `checklists/`). This is **Spec Kit**, not OpenSpec.
- **Its workflow has 7 phases and no archive step:** `specify → review-spec → plan → review-plan → tasks → implement` (`.specify/workflows/speckit/workflow.yml`). In Spec Kit, features live permanently under `specs/NNN-name/`; there is nothing to "archive". **`openspec archive 001-cv-sign-detection` fails with `Unknown item`** — verified, the change does not exist in OpenSpec.
- **State:** `tasks.md` shows **31/31 `[X]`** (T031 was added during T024–T031; note it uses lowercase `[x]`, unlike the other 30). `checklists/plan-tecnico.md` is **39/40**, with CHK035 open (the line mask has no consumer — Reto objectives 3–4).

### 21.2 OpenSpec — configured but never used

- **What it is here:** an initialized-but-idle change-management scaffold. The only commit that ever touched `openspec/` is `5ab3a2a` (the first), which only ran `openspec init`.
- **State:** `openspec/config.yaml` → `schema: spec-driven`. `openspec/changes/` contains only `archive/.gitkeep`; `openspec/specs/` only `.gitkeep`. **Active changes: none. Specs: none.** `openspec list --json` returns `{"changes":[]}`.
- **CLI:** `openspec` 1.13.1 available on this machine; all generated files stamp `generatedBy: "1.13.1"`.
- **Its archive command does not apply to this project's work:** it archives things under `openspec/changes/`, which is empty. Do not run it expecting it to touch `specs/`.
- **Workflow commands** (generated for each tool target): `opsx-propose` (create a change + all planning artifacts in one step — planning only, never code), `opsx-apply` (implement tasks; loop until done/blocked; *Experimental*), `opsx-update` (revise existing artifacts, keep them coherent; never edits code; *Experimental*), `opsx-sync` (sync delta specs → main specs without archiving), `opsx-archive` (archive a completed change; *Experimental*), `opsx-explore` (thinking mode: read/investigate; capturing decisions as artifacts is allowed, implementing is not).
- **How agents must interact:** use the `openspec` CLI (prefer `--json`) rather than hand-crafting files; check `openspec list --json` / `openspec status --change <name> --json` before acting; treat `openspec/config.yaml` (context/rules sections, currently empty) as the place where project conventions for artifacts would be declared; never let a command create an `openspec/` root as a side effect (`openspec init` only if the user asks).
- **Decisions pending:** whether to adopt OpenSpec for the next cycle (control de trayectoria) or delete the idle scaffold. Not decided — do not assume.

---

## 22. AI-Agent Configuration Files (the four trees)

The repo ships four synchronized trees of OpenSpec-generated instruction files, one per tool. **Content map (verified by MD5):**

| Tree | Files | Relationship |
|---|---|---|
| `.agents/` (`skills/` + `workflows/`) | 6 skills + 6 workflows + `.openspec-target` | Skills & workflows **identical** to `.github/` copies; target marker: `antigravity` |
| `.github/` (`skills/`, `prompts/`, `agents/`) | 6 skills + 6 prompts (+ Copilot agent + workflow) | Prompts ⇔ `.agents/workflows` byte-identical; adds `agents/openspec.agent.md` + `copilot-setup-steps.yml` |
| `.opencode/` (`skills/`, `commands/`) | 6 skills + 6 commands | Skills identical to `.agents/`; commands differ by exactly one line (`**Provided arguments**: $ARGUMENTS`) |
| `.claude/` (`skills/`, `commands/opsx/`) | 6 skills + 6 commands | **Different variant**: references use colon syntax (`/opsx:explore` etc.) and commands carry extra YAML frontmatter (`name`, `allowed-tools`, `category`, `tags`) |

**Interpretation rules:**
- All four trees are **generated artefacts from the same OpenSpec version** — they are per-tool adaptations, not four independent sources. Differences above are intentional translations, not drift errors.
- **Do not hand-edit them** to "fix" wording or sync content: regenerate via the OpenSpec CLI (`openspec update` refreshes generated files) so all trees move together. Manual edits are how these trees desynchronize.
- The commands/skills all follow the same contract: read-only exploration is safe; planning artifacts are written through OpenSpec; implementation happens only in the apply workflow; every workflow re-checks the project root before writing.

---

## 23. Critical Files

| Class | File(s) | Why / when to review |
|---|---|---|
| **CRITICAL** | `documents/markdawn/Reto-1.md` (+ `.docx` original) | The functional spec. Review before ANY behavioral decision (line detection, signals, control, deliverables) |
| **CRITICAL** | `documents/markdawn/Rubrica-Reto-1.md` (+ `.xlsx`) | How the work is graded; drives explainability and distinctiveness requirements |
| **CRITICAL** | `documents/markdawn/FundamentosVisionArtificial.md` (+ PDF) | The allowed technique toolbox with worked examples (Canny, morphology, contours, polygons) |
| **CRITICAL** | `documents/markdawn/18-K-MEANS-Basico.md` (+ PPTX) and `documents/ipynb/*` | K-Means and the color/ops notebooks; review before implementing segmentation stages |
| **IMPORTANT** | `pyproject.toml` | Single source of declared deps/Python version and pytest markers |
| **IMPORTANT** | `config/vision.json` | Runtime parameters (ROIs, HSV ranges, morphology, confirmation, stop time, shape filters) |
| **IMPORTANT** | `specs/001-cv-sign-detection/**` | Spec Kit feature (31/31 tasks): design, tasks, contracts, checklist, quickstart — the live record of Fases 1–7 |
| **IMPORTANT** | `openspec/config.yaml` | Workflow schema + Copilot integration; future home of project context/rules |
| **IMPORTANT** | `openspec/changes/**` | Once work starts: the live plan of every change |
| **IMPORTANT** | `.gitignore` | Defines what counts as repo vs local (`.venv`, `.env`, caches) |
| **IMPORTANT** | `.github/workflows/copilot-setup-steps.yml` | How cloud agents bootstrap the OpenSpec CLI |
| **CONTEXTUAL** | `.agents/**`, `.claude/**`, `.opencode/**`, `.github/{skills,prompts,agents}/**` | Generated workflow instructions per tool — read the one for your host tool, never edit by hand |
| **CONTEXTUAL** | `.idea/**` | IDE state; safe to ignore for logic work |
| **CONTEXTUAL** | `src/__init__.py`, `src/models/__init__.py`, `src/services/__init__.py` | Empty markers; only meaningful if a future change gives those packages a role |

---

## 24. Change Impact Areas

Given the current state (pipeline implemented, actuator boundary open), the real impact map is about *where change lands*:

- Touching **`src/vision/`** → you are changing the deployed behavior that the 428 tests measure; any edit must map to an allowed technique (§10), stay explainable (§4 criteria 5 & 9), and keep `tests/unit/` + `tests/integration/` green. Changing `roi_linea`, `rango_hsv_linea` or the shape filters alters SC-010 and SC-001/002/003 simultaneously.
- Touching **`src/vision/configuracion.py`** or **`config/vision.json`** → every test that builds `ParametrosConfiguracion` is affected; validation happens at load time and a malformed value raises.
- Adding a **dependency** → update `pyproject.toml [project].dependencies`; the env is uv-managed and `uv.lock` is versioned, so run `uv sync` after the change; a new dep must be a classical-CV library, never a learned model (§11). Note the robot link needs **no** third-party dependency today (standard-library `socket`).
- Touching **`documents/**`** → you are editing the academic source of truth (originals + transcriptions). Prefer appending corrections; never silently rewrite.
- Touching **agent trees** → regenerate, don't hand-edit (§22); remember all 4 trees move together.
- Touching **`openspec/config.yaml`** or the schema → affects every opsx workflow; treat as a change itself.
- Touching **`.gitignore`/`.idea`** → only affects repo hygiene and IDE users; low risk, but `.idea/` is tracked and `workspace.xml` deliberately isn't.

---

## 25. Rules for AI Agents

**Before changing anything**

1. Read §3, §4, §10, §11 of this file plus `Reto-1.md` and the rúbrica whenever the work could affect robot behavior.
2. Establish the current state with evidence (`git status`, `openspec list --json`, read the actual files) and classify what you find as *implemented / partial / documented-only / planned / undetermined*. Never promote documentation to "implemented".
3. If the work is non-trivial, create an OpenSpec change first (`opsx-propose` flow) — this project's convention is planning before building; implement only through the apply workflow once tasks exist.
4. Verify technique compliance against the allowed list (§10) *before* designing the solution, not after.
5. Where the challenge depends on specifics the repo doesn't fix (PARE duration, track geometry), surface the gap to the human; do not assume values.

**While working**

6. Keep changes scoped to the agreed change/task; do not refactor unrelated files or "fix" cosmetic things (e.g., the `markdawn` typo) without explicit agreement.
7. New dependencies go into `pyproject.toml`; install into `.venv` via uv; never commit `.venv`, `.env`, or generated caches.
8. Keep code stage-explainable and traceable: comments/docstrings that name which allowed technique a step implements directly serve the rubric.
9. Do not run `openspec init` or hand-create `openspec/` files; use the CLI; prefer `--json` outputs.
10. When exploring (opsx-explore mode), stay read-only unless capturing OpenSpec artifacts was explicitly requested.

**After working**

11. Keep plan and reality aligned: for Spec Kit work, check off `tasks.md` and keep `specs/NNN-name/` coherent; for OpenSpec work (if adopted), `openspec validate` then sync/archive — but note `openspec archive` does **not** apply to `specs/` (see §21.1).
12. Re-run the §0 verification commands; report honestly what exists vs what doesn't (state beats optimism here — graders and teammates read this code).
13. If you found a documentation/code conflict, record it (in the change, or as an update to §27 of this file) instead of silently resolving it.

---

## 26. Things Agents Must Not Do

- **Never introduce forbidden techniques:** neural networks, deep learning, pretrained models, YOLO/SSD/Faster R-CNN-style detectors, Haar cascades, external AI services, or libraries that auto-detect the line/signals without team-implemented logic. This is a grading criterion, not a style preference.
- Do not claim or document functionality that does not exist; do not describe the target pipeline (§8) as implemented beyond the validation CLI.
- Do not treat `src/models/` or `src/services/` as implemented architecture; they are empty.
- Do not treat `documents/**` or the notebooks as product code; do not import from notebooks; do not move them.
- Do not delete or rewrite academic materials without explicit justification and user approval.
- Do not hand-edit generated agent files in `.agents/`, `.claude/`, `.opencode/`, `.github/{skills,prompts,agents}` — regenerate them instead.
- Do not invent commands, dependencies, environment variables, hardware interfaces, endpoints, or databases. If something is unknown (e.g., how the robot moves), say it is unknown and where it would be decided.
- Do not commit secrets, tokens, or `.env` files; none exist today and none should be added.
- Do not modify `.venv` contents by hand or commit the virtualenv.
- Do not create an `openspec/` root as a side effect of running commands; do not bypass the opsx workflow for product work.
- Do not "fix" the `markdawn` folder name silently for aesthetics — it is known and recorded here (§27.7).

---

## 27. Known Inconsistencies and Gaps

Recorded during the audit; each item is factual with evidence:

1. **Documentation vs code:** Reto 1 describes a complete real-time autonomous system; the codebase is a scaffold with a sample script. The gap is total, not partial. **RESOLVED by Fases 3–7 and feature 002**: the pipeline, FSM, metrics, CLI, trajectory control, compositor, transport queue and 428 tests now exist; what remains is validation on the real robot and the poster.
2. **Empty packages with architectural names:** `src/models/`, `src/services/` exist but contain nothing; the names imply an architecture that has not been designed anywhere. **STILL TRUE** — the real code lives in `src/vision/`; the two folders remain 0-byte markers.
3. **Environment vs materials:** the class notebooks require `cv2` (+ `sklearn` in nb4); `.venv` has `sklearn` but **not** `cv2`, and `pyproject.toml` declares no dependencies — the local environment cannot run the materials, and is not reproducible from the repo. **PARTLY RESOLVED**: `opencv-python-headless` is now declared and installed, so the notebooks run; and `uv.lock` is committed, so the environment is reproducible with `uv sync`.
4. **Stored notebook failure:** `4_Kmeans_Imagenes.ipynb`'s last execution crashed with `ModuleNotFoundError: No module named 'google.colab'` (Colab-only import) — the notebook was last run in the wrong environment. **STILL TRUE in the file** (historical artifact, not a project blocker).
5. **Broken asset reference:** `documents/markdawn/Reto-1.md` references `media/image1.jpeg` (track photo) but no `media/` directory exists in the repo. **STILL TRUE**.
6. **Undefined stop duration:** PARE = "el tiempo establecido por el docente"; no value is fixed in any document of the repo. **STILL TRUE** — `t_parada_s: 3.0` is a provisional default, not a teacher value.
7. **Generated trees differ across tools:** `.claude/` variants use `/opsx:<name>` colon syntax + extra frontmatter, `.opencode/` adds a `$ARGUMENTS` line; the other two are byte-identical. Intentional per-tool adaptation — but it means "the same file" is not literally the same everywhere.
8. **Template artefacts in `.gitignore`:** `.ruff_cache/` and `pyrightconfig.json` are mentioned but neither tool is configured; don't assume tooling from the ignore file.
9. **`.idea/` tracked against template advice:** 7 IDE files are committed while the template suggests ignoring `.idea/`; `workspace.xml` is untracked. If this is not intentional, decide explicitly (a change).
10. **No README/name definition:** "OptiPilot" appears only in `pyproject.toml`, `.idea/` files, and paths; the repo contains no description of the project beyond the academic documents.
11. **The practice footage contains no detectable PARE/SIGA signs.** Re-measured locally on all 9 real videos (2026-09-28, 687 frames sampled 1/4, `segmentacion` + `candidatos` used directly, not the CLI summary). Every red/green blob fails the shape filter for a geometric reason, and no `approxPolyDP` epsilon fixes it:
    - **Red blobs** (642): median aspect **2.47**, median circularity **0.293** (an octagon is ~0.8-0.9), median solidity 0.72. They are elongated strips, not polygons.
    - **Green blobs** (1391): median aspect 1.29, median circularity **0.590**, solidity 0.916 — round-ish but not octagonal.
    - **Epsilon sweep** (share of blobs with 7-9 vertices): red 14.0% @0.005, 49.7% @0.02, 9.2% @0.03; green 3.7% @0.005, 37.2% @0.02, 9.6% @0.03. No epsilon produces a reliable 8-vertex population, so `EPSILON_APROX=0.03` is **not** the lever.
    - **Correction of an earlier finding:** the previous T027 note claimed 304 of 305 shape-passing contours lay *outside* `roi_senales`. Re-measured, the extracted contours' centres lie *inside* the current ROI (y≈49-501); they are discarded for **vertex count** (67.6% have 4 vertices), not for being excluded by the ROI. The conclusion "0 confirmations" is unchanged, but the cause is different and the ROI was not the reason.
    - The videos are line-following footage (`rutaIdeal`, `desarrilamiento`); **they do not appear to contain the octagonal signs at all**. 0 confirmations is the correct result, not a tuning failure. Any future sign-detection tuning needs footage that actually shows PARE/SIGA.
12. **Line mask is not IoU-ready:** `rango_hsv_linea` (`v_max: 110`) lights up ~55-99 % of the line ROI on real footage, and the contract's reference is a ~3 px centre line. The theoretical IoU ceiling is `3/W`, so a mask wider than 5 px **cannot** reach SC-010's 0.60 threshold. Measured 0.125 against a synthetic 3 px reference. Any future SC-010 work must first decide the annotation thickness vs. predicted width. **Resolved for geometry on 2026-09-28:** `roi_linea` was recalibrated from `y=0.55` to `y=0.10` (see §16.1); occupancy of the ROI dropped from a 54.7 % median (334 px runs) to 13.3 % (71 px runs). Thickness remains open.
13. **Fixture geometry differs from footage:** synthetic frames are 640×480 landscape; the real videos are 478×850 portrait. Integration tests therefore do not exercise the geometry they will be judged on.
14. **The practice footage is present but untracked:** the 9 videos live in `videos/desarrilamiento/` (5) and `videos/rutaIdeal/` (4), **not** in `documents/videos/`; they were re-obtained locally on 2026-09-28 and are deliberately **not versioned** — `.gitignore:180` ignores `videos/` (verified with `git check-ignore`). They are 478×850 portrait, 2730 frames total. Anyone cloning the repo will not have them; re-verify §27.11–27.13 locally before repeating any claim about "the 9 real videos".
15. **Transport protocol superseded, uncommitted (2026-09-28).** The professor's `Robot.py` fixed the actual link: one ASCII byte per command (`w`/`a`/`d`/`x`) over `socket.AF_BLUETOOTH` + `BTPROTO_RFCOMM`, not the team's earlier 4-byte frame with an XOR checksum over `pyserial`/`COM`. `pyserial` was removed from `pyproject.toml` and `uv.lock`, so the robot link now has **zero** third-party dependencies. `src/transporte/spp.py` and `src/vision/compositor.py` are **new and untracked**; the 002 spec was rewritten to match (see `research.md` Decisión 7, where the old design is preserved as SUPERSEDED). `Robot.py` itself is **not in the repo**, so the framing assumption (one byte, no newline) is unverified — open question P3.
16. **`componer` signature was wrong in the contract (found while writing T024).** `contracts/api-control.md` §3 declared `componer(decision, movimiento)`, which cannot build `DecisionCompuesta` because that dataclass also requires `posicion` and `permitido`. The real signature takes three arguments; the contract was corrected on 2026-09-28.
17. **`CausaComando.VETO_FSM` is a reserved value (found while writing T024).** It describes a decision of the *compositor*, so the trajectory controller must never emit it; `DecisionCompuesta` enforces this by rejecting `VETO_FSM` paired with any command other than `DETENER`. Tests must exclude it when enumerating "causes the control can propose". Consequence for the poster/metrics: the two stop reasons stay distinguishable — `PERDIDA_SIN_MEMORIA`/`GRACIA_AGOTADA`/`FALLO_SEGURO` (control) vs `VETO_FSM` (PARE).
18. **`ColaTransporte` / `TransporteSimulado` — NOW IMPLEMENTED (2026-09-28, second pass).** `src/transporte/{cola,simulado}.py` exist with 22 unit tests; the CLI injects the transport via `--transporte {simulado,spp}` and drains in a background thread. SC-005 (the loop never blocks) is now demonstrated in code: an AST test asserts `src/main.py::_correr` calls `encolar` and never `drenar`, and that no `src/vision/` module imports the transport.
19. **Feature 001 docs drifted from the recalibrated ROI (recorded, not fixed).** `specs/001-cv-sign-detection/data-model.md` still documents `roi_linea.y = 0.55`, obsolete since the recalibration to `0.10` (commit `7f0990c`, §16.1). 001 is frozen; the conflict is recorded here by Principle VI rather than editing 001. Also note the 001 checklist `plan-tecnico.md` CHK035 ("line mask has no consumer") was **closed by feature 002** on 2026-09-28: `src/vision/posicion_linea.py` consumes `mascara_linea`.
20. **AGENTS.md itself carried a wrong module name (corrected 2026-09-28).** Earlier passes listed `src/vision/estimador_linea.py`; the module on disk is **`src/vision/posicion_linea.py`** (class `EstimadorLinea`). Found while doing T043/T044. Lesson already in the file's own §29: verify names against disk.
21. **T040's reference numbers did not reproduce (recorded, not hidden).** The task text cited "~15–20 px in `rutaIdeal` vs ~52 px in `desarrilamiento`" for `velocidad_error_px`. Measured on the 9 real videos with the current `config/vision.json`, neither the frame-to-frame `|Δx|` (~2.5 vs ~1.7 px) nor the lateral error magnitude `|x − objetivo|` (~37 vs ~48 mean, p95 ~82 vs ~149) matches those values. The **direction** of discrimination holds for the error magnitude (desarrilamiento larger), and that is what the footage test now verifies; the literal "velocity" metric does **not** discriminate because in `desarrilamiento` the line is frequently lost (invalid position), which removes consecutive valid pairs. The exact reference definition is not recoverable from the repo, so it is recorded here rather than tuned to. Any future claim of "15–20 vs 52 px" must first restate the exact definition used.

---

## 28. Known Limitations / Undetermined Items

- No robot/hardware documentation: actuator interface, camera access (OpenCV `VideoCapture` index, ROS, serial, etc.) — all undetermined; do not assume. The transport link is now known at the byte level (RFCOMM, `w`/`a`/`d`/`x`) but the mBot's real MAC and whether it expects a line terminator are **not** confirmed.
- No specification of the track, sign placement/size, lighting conditions — only the external practice-videos link.
- PARE stop duration and "intentos" (attempts) count are teacher-defined and absent here.
- The annotated reference corpus (SC-010) does not exist, so SC-001/002/003/010 are **not evaluable**; T027 skips cleanly rather than reporting a number.
- The camera mounting/orientation on the real robot is unknown, and the practice footage is portrait/downward-looking, which does not match the ROI geometry in `config/vision.json`.
- Environment: repo now on `D:` (was OneDrive); `.venv` is large (234 MB) and git-ignored.
- No product CI, no lint/format tooling, no `README`/`LICENSE`/`CONTRIBUTING`.

---

## 29. Source of Truth

| Question | Authoritative source | Never substitute with |
|---|---|---|
| What must the robot do (behavior, signals, deliverables, competition rules) | `documents/markdawn/Reto-1.md` (≡ `.docx`) | anything else in the repo |
| How work is judged | `documents/markdawn/Rubrica-Reto-1.md` (≡ `.xlsx`) | intuition |
| Allowed/forbidden techniques | `Reto-1.md` lists (§10–§11) | course deck examples, internet patterns |
| Technique theory/usage as taught | `Fundamentos…md/.pdf`, `18-K-MEANS…md/.pptx`, notebooks | external tutorials (allowed as study aid, not as authority) |
| Repo behavior (what actually exists) | code + config + `git` + `openspec list` | documentation of intentions |
| Agent/workflow process | `openspec/config.yaml`, generated opsx files, the `openspec` CLI's own output | this file, where they disagree |
| Environment facts | `.venv/pyvenv.cfg`, site-packages, `python --version` | README claims (there is none) |

Conflict resolution order for **behavioral facts**: code/config > tests (none yet) > functional documents > notebooks > comments > history. For **requirements and constraints**: official challenge documents outrank everything, including code — code that violates Reto 1 is simply non-compliant.

---

## 30. Pre-Change Checklist

Before modifying anything, verify:

- [ ] I understood the objective of the change and which §5 state it moves (documented → implemented, etc.).
- [ ] I read `Reto-1.md` and `Rubrica-Reto-1.md` if the change can affect robot behavior, deliverables, or scoring.
- [ ] I checked the allowed-techniques list (§10) and confirmed the change introduces **zero** forbidden techniques (§11).
- [ ] I reviewed the relevant class material (`Fundamentos…`, `18-K-MEANS…`, matching notebook) when the change implements a CV stage.
- [ ] I confirmed the current state from evidence (files, `git`, `openspec list`) — not from memory or this document alone.
- [ ] The work fits an OpenSpec change (or I confirmed with the user why it doesn't need one), and I know where the change's artifacts live.
- [ ] I know which files I will touch and none of them are: academic originals without justification, generated agent files (hand-edit), vacated/empty placeholder semantics I plan to change silently.
- [ ] New dependencies (if any) will be declared in `pyproject.toml` and installed via uv; no secrets involved.
- [ ] I know how I will validate the result (today: `uv run pytest -q`, plus the CLI on real footage; the `footage` and `perf` markers cover the rest).
- [ ] Impact checked: does this change the story told in the poster/rubric criteria (explainability, differentiation, results)? If yes, note it.

---

## Glossary

| Term | Meaning in this project |
|---|---|
| **Reto 1** | The graded challenge: line-following robot + PARE/SIGA signals, classical CV only |
| **PARE / SIGA** | Stop sign (red octagon) / go sign (green octagon) |
| **Descarrilamiento** | The robot losing the line |
| **Rúbrica** | Official 12-criteria evaluation sheet |
| **opsx-*** | OpenSpec workflow commands (`propose`, `apply`, `archive`, `explore`, `sync`, `update`) |
| **BGR / HSV / CIELab** | Color spaces used (OpenCV loads BGR; conversions are an allowed technique) |
| **approxPolyDP / boundingRect** | OpenCV contour tools taught for shape analysis (octagon = 8 vertices) |

---

*End of AGENTS.md — keep it factual; when the project state changes materially, update this file in the same change that changes the state.*
