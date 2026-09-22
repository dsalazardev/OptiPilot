# AGENTS.md — OptiPilot

**Bootstrap and operating manual for AI agents working in this repository.**

- **Generated:** 2026-09-22 (from a full read-only inspection of the repository).
- **Basis:** commit `5ab3a2a` on `main` — identical to `origin/main` at generation time — 79 tracked files, all inspected, including binary academic materials, Jupyter notebooks, and the four AI-agent tool trees.
- **Repo path:** `C:\Users\USUARIO\OneDrive\Escritorio\ARCHIVOS\DESARROLLO\OptiPilot`
- **Remote:** https://github.com/dsalazardev/OptiPilot (branch `main`).
- **Change policy of this document:** creating `AGENTS.md` was the **only** modification allowed during the analysis. No code, dependency, configuration, or academic material was changed. Everything below is traceable to files in the repository. Where a statement is an inference from evidence it is marked **«INFERENCE»**; where something does not exist yet it is marked **«NOT IMPLEMENTED»**.
- **Language:** this document is written in English (standard for agent bootstrap files); the project's source material is in Spanish. Keep Spanish domain terms verbatim: *Reto 1, PARE, SIGA, rúbrica, descarrilamiento*.

---

## 0. Read this first

Read order for a new agent joining this project:

| # | Read | Why |
|---|------|-----|
| 1 | This file, end to end | State, constraints, rules |
| 2 | `documents/markdawn/Reto-1.md` | The functional specification of what will be built |
| 3 | `documents/markdawn/Rubrica-Reto-1.md` | How the work is evaluated (12 criteria) |
| 4 | `documents/markdawn/FundamentosVisionArtificial.md` + `documents/markdawn/18-K-MEANS-Basico.md` | The allowed technique toolbox (course material) |
| 5 | `openspec/config.yaml`, then run `openspec list --json` | Workflow configuration and current change state |
| 6 | `pyproject.toml`, `src/**` | The actual (tiny) code state |

Re-verification quick commands (run from the repo root; bash on this machine):

```bash
git rev-parse HEAD origin/main      # sync state (both must match unless work is in flight)
git status --short                  # working tree state
openspec list --json                # active OpenSpec changes (currently: none)
openspec --version                  # CLI version (1.13.1 at generation time)
git ls-files | wc -l                # tracked files (79 at generation time)
```

---

## 1. Project Overview

**OptiPilot** is the working name (appears only in `pyproject.toml` and `.idea/optipilot.iml`; there is no README) of an academic software project whose goal is the **"Reto 1" of a computer-vision course at Universidad de Caldas**: the *brain* of an autonomous line-following robot that uses a camera, classical image processing only, and must react to two traffic signs (red octagon = **PARE** / stop; green octagon = **SIGA** / go).

**Current reality (do not skip):** the repository contains **documentation, course materials, tooling configuration, and an empty Python skeleton**. There is **no application logic implemented yet** — no image processing pipeline, no line detection, no sign detection, no control, no camera interface. The only Python file with content is the unmodified PyCharm sample script `src/main.py`.

**Status snapshot**

| Area | State | Evidence |
|------|-------|----------|
| Academic materials (challenge, rubric, class decks, notebooks) | Present — source of truth | `documents/**` |
| Python project skeleton | Partial scaffold | `pyproject.toml`, `src/` (empty `__init__.py` files + sample script) |
| Implementation (CV pipeline, control, signals) | **NOT IMPLEMENTED** | nothing in `src/` beyond the sample |
| Tests | Absent | no test files or configs anywhere |
| CI/CD | Absent for the product; 1 generated Copilot-setup workflow | `.github/workflows/copilot-setup-steps.yml` |
| OpenSpec | Initialized; **zero changes, zero specs** | `openspec/`, `openspec list --json` → `"changes": []` |
| AI-agent tooling | Present — generated for 4 tool targets | `.agents/`, `.claude/`, `.opencode/`, `.github/` |
| Python environment | Partial: Python 3.14.7 uv venv; **no OpenCV installed** | `.venv/pyvenv.cfg`, `.venv/Lib/site-packages` |
| Git | Single commit `5ab3a2a` "feat(doc): add a documents of class"; in sync with `origin/main` | `git log`, `git ls-remote` |

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
- Git repository with a single commit; local `main` == `origin/main`.
- PyCharm project files (`.idea/**`, 7 tracked files).
- OpenSpec initialization (`openspec/config.yaml`, `specs/`, `changes/archive/` with `.gitkeep` files).
- OpenSpec-generated agent tooling for 4 tool targets (§22–23).
- Academic material set in `documents/**` (available, not authored by the repo owner).

**Partially implemented**
- Python project scaffold: `pyproject.toml` declares `optipilot` 0.1.0, `requires-python = ">=3.14"`, **`dependencies = []`**; `src/__init__.py`, `src/models/__init__.py`, `src/services/__init__.py` are 0-byte package markers; `src/main.py` is the untouched PyCharm sample (`print_hi('PyCharm')`).
- Local environment: `.venv` (Python 3.14.7, uv-managed) with `numpy 2.5.3`, `scipy 1.18.1`, `scikit-learn 1.9.1`, `matplotlib 3.11.2`, `pillow 12.3.0` (+ transitive deps) — but **no OpenCV (`cv2`), no Jupyter, and no `pip` module inside the venv**.

**Documented but NOT implemented** (everything about the robot behavior):
- any camera capture; line detection; ROI/segmentation logic; centroid/position math; control; signal detection; stop/go state machine; robot↔computer communication; tests; logging; poster material generation.

**Planned / configured**
- OpenSpec `spec-driven` workflow is armed (schema configured, agent tooling generated) but **no change has been created yet** (`openspec list --json` → empty).
- GitHub Copilot cloud-agent support is enabled (`openspec/config.yaml` → `githubCopilot.cloudAgent: true`) with a setup workflow.

**Undetermined**
- Robot platform/hardware, camera model, communication interface (serial? BLE? none of it is mentioned in the repo).
- PARE stop duration value; track/sign geometry; team composition; poster format requirements.
- Whether `src/models` and `src/services` are meant as architecture layers at all — the folders exist but nothing defines their role. Do **not** treat their names as proof of an architecture.

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
├── documents/                     # academic source material (16 MB)
│   ├── documents/                 #   binaries: Reto-1.docx, Rubrica-Reto-1.xlsx,
│   │                              #   18-K-MEANS-Basico.pptx, FundamentosVisionArtificial.pdf
│   ├── ipynb/                     #   4 class notebooks (Colab-style)
│   └── markdawn/                  #   markdown transcriptions (folder name is a typo of "markdown";
│                                  #   kept as-is — do not rename without an explicit decision)
├── openspec/                      # config.yaml + specs/ + changes/archive/ (both empty with .gitkeep)
├── .gitignore                     # Toptal "python" template (see §14)
├── pyproject.toml                 # the only project config (5 lines)
└── src/                           # Python package skeleton (see §11)
```

Missing on purpose/absence: no `README*`, no `LICENSE`, no `CONTRIBUTING`, no `tests/`, no `uv.lock`, no `.env*`, no product CI workflows, no `AGENTS.md` before this file.

---

## 7. Technology Stack

| Layer | What is actually used | Evidence |
|-------|----------------------|----------|
| Language | Python — declared `>=3.14` | `pyproject.toml` → `requires-python` |
| Local runtime | CPython **3.14.7**, uv-managed venv (**uv 0.12.15**) | `.venv/pyvenv.cfg`, `.venv/Scripts/python.exe --version` |
| Dependency management | Declared: none (`dependencies = []`); Installed in venv: numpy, scipy, scikit-learn, matplotlib, pillow (+ deps) | `pyproject.toml`, `.venv/Lib/site-packages` |
| **Missing for the challenge** | **OpenCV (`cv2` is imported by all class notebooks but is NOT installed)**; Jupyter (notebooks are Colab-authored) | site-packages listing |
| Notebooks (class material) | Google Colab style: `cv2`, `numpy`, `matplotlib`, `sklearn`; `google.colab` in notebook 4 | `documents/ipynb/*` |
| Agent/workflow tooling | OpenSpec CLI **1.13.1** (`npm install -g @fission-ai/openspec`); generated files stamped `generatedBy: "1.13.1"` | CLI output, skill frontmatter, `.github/workflows/copilot-setup-steps.yml` |
| IDE | PyCharm (project SDK pinned to the local `.venv`; module type `PYTHON_MODULE`, `external.system.id="pyproject.toml"`) | `.idea/` |
| VCS | Git, single branch `main`, remote GitHub `dsalazardev/OptiPilot` | `git remote -v`, `git log` |
| OS/workspace | Windows 11; repo lives inside OneDrive | paths, `.venv` size note |

No build system beyond setuptools defaults; no formatter/linter/test runner configured (see §19).

---

## 8. Architecture and Application Flow

**Actual architecture: none beyond the package skeleton.** There is no separation into input/domain/processing/services because there is no application code. `src/models/` and `src/services/` are empty package markers (`__init__.py`, 0 bytes). Do not describe an idealized architecture as if it existed.

**Actual application flow: «NOT IMPLEMENTED».** Running `python src/main.py` prints `Hi, PyCharm` — that is the entire executable behavior of the repo.

The only "flow" that exists is the one the challenge *requires* (derived from the 7 specific objectives of Reto 1 — reproduce it only as target behavior, never as current state):

```text
camera frames ──▶ [line identification / segmentation]        «NOT IMPLEMENTED»
                      │
                      ▼
              [line position relative to robot center]        «NOT IMPLEMENTED»
                      │
                      ▼
              [control actions / trajectory correction]       «NOT IMPLEMENTED»
                      │
                      ▼
   [signal detection: red octagon = PARE / green = SIGA]      «NOT IMPLEMENTED»
                      │
                      ▼
              [stop / resume behavior + recovery]             «NOT IMPLEMENTED»
```

If you implement any stage, record it as an OpenSpec change (propose → apply) so that docs and code stay separated but traceable.

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
| `src/main.py` | PyCharm sample (`print_hi`), with IDE-specific comments (Ctrl+F8, "Mayús+F10") | Placeholder — replace, don't extend |
| `src/__init__.py` | empty | package marker |
| `src/models/__init__.py` | empty | package marker; **no models exist** |
| `src/services/__init__.py` | empty | package marker; **no services exist** |

There are no imports between modules, no entry points beyond `python src/main.py`, no CLI, no config loading.

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

- **`pyproject.toml`** (the only build/config file, verbatim):
  ```toml
  [project]
  name = "optipilot"
  version = "0.1.0"
  requires-python = ">=3.14"
  dependencies = []
  ```
- **`openspec/config.yaml`**: `schema: spec-driven`; `githubCopilot.cloudAgent: true`. Everything else (context, rules, operations) is **commented-out examples only** — the project has not filled in its OpenSpec context yet. This is the natural place to declare project context for OpenSpec workflows (a change, if done).
- **`.gitignore`**: Toptal "python" template. Ignores `.venv`, `.env`, `__pycache__/`, `.ipynb_checkpoints`, `.ruff_cache/`, `pyrightconfig.json`, coverage artefacts, etc. `.idea/` is **not** ignored (the line is commented) and IDE files are deliberately tracked, except `.idea/workspace.xml` which is excluded by `.idea/.gitignore`.
- **No `.env`, no config modules, no settings files, no `uv.lock`.** No environment variables are referenced anywhere (searched `os.environ` / `os.getenv` / dotenv patterns across the repo: zero hits). If a future stage needs env vars, that is a new decision — document it.

---

## 16. Development Environment

- Windows 11 machine; the repo sits under OneDrive (`...\OneDrive\Escritorio\ARCHIVOS\DESARROLLO\OptiPilot`). Note two effects: OneDrive may sync large binaries (`.venv` is 234 MB and lives inside the synced folder — it is git-ignored but still synced by OneDrive unless excluded) and path length/encoding quirkiness applies.
- The venv was created with **uv 0.12.15** using a uv-managed CPython 3.14.7 (see `pyvenv.cfg`). There is **no `pip` module inside `.venv`** — install extra packages with `uv pip install <pkg> --python .venv/Scripts/python.exe` (or recreate managed by uv), and remember the declared-dependencies file (`pyproject.toml`) is currently empty.
- **Known gap:** `import cv2` fails in `.venv` (OpenCV not installed), so no class notebook and no future CV code can run in the local venv as-is. The notebooks historically ran on Colab (that environment had cv2/sklearn).
- PyCharm is the IDE (`.idea/`): project SDK points at `.venv`; module type derives from `pyproject.toml`.

---

## 17. Development Commands (only verified ones)

| Purpose | Command | Source of truth |
|---|---|---|
| Verify OpenSpec CLI | `openspec --version` | `.github/agents/openspec.agent.md`, `.github/workflows/copilot-setup-steps.yml` |
| Install OpenSpec CLI (if missing) | `npm install -g @fission-ai/openspec` | `.github/workflows/copilot-setup-steps.yml` |
| List changes | `openspec list --json` | generated workflows |
| Any OpenSpec workflow step | `openspec status --change <name> --json`, `openspec instructions <artifact> --change <name> --json`, `openspec validate …`, `openspec archive …` | `.github/agents/openspec.agent.md` |
| Run the (sample) entry point | `.venv/Scripts/python.exe src/main.py` | `src/main.py` |
| Python version check | `.venv/Scripts/python.exe --version` | verified → 3.14.7 |

**There are no build, test, lint, format, or run-the-robot commands in this repository.** Do not invent them; if you add tooling, document it here and in `pyproject.toml` (via a change).

---

## 18. Testing

- No tests exist: no `test/`, `tests/`, `*_test.py`, `test_*.py`, `conftest.py`, `pytest.ini`, `tox.ini`, or `[tool.pytest]` sections anywhere in the tree.
- No test framework is declared (no `dependencies`, no extras).
- The only "validation" available today is `openspec validate` for OpenSpec artifacts — unrelated to product behavior.
- **«INFERENCE»** Any future implementation of the pipeline will need real footage for evaluation; the only footage resource known is the external Drive folder referenced in `Reto-1.md`.

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

## 21. OpenSpec

- **What it is here:** the structured change-management workflow the project uses (per the owner's established practice): every non-trivial piece of work should flow *proposal → (specs/design) → tasks → implementation → archive*, and specs live in `openspec/specs/`.
- **State:** initialized. `openspec/config.yaml` → `schema: spec-driven`. `openspec/changes/` contains only `archive/.gitkeep`; `openspec/specs/` only `.gitkeep`. **Active changes: none. Specs: none.** `openspec list --json` returns a `root` object with `path` = this repo (i.e., the project is set up correctly).
- **CLI:** `openspec` 1.13.1 available on this machine; all generated files stamp `generatedBy: "1.13.1"`.
- **Workflow commands** (generated for each tool target): `opsx-propose` (create a change + all planning artifacts in one step — planning only, never code), `opsx-apply` (implement tasks; loop until done/blocked; *Experimental*), `opsx-update` (revise existing artifacts, keep them coherent; never edits code; *Experimental*), `opsx-sync` (sync delta specs → main specs without archiving), `opsx-archive` (archive a completed change; *Experimental*), `opsx-explore` (thinking mode: read/investigate; capturing decisions as artifacts is allowed, implementing is not).
- **How agents must interact:** use the `openspec` CLI (prefer `--json`) rather than hand-crafting files; check `openspec list --json` / `openspec status --change <name> --json` before acting; treat `openspec/config.yaml` (context/rules sections, currently empty) as the place where project conventions for artifacts would be declared; never let a command create an `openspec/` root as a side effect (`openspec init` only if the user asks).
- **Note:** `.agents/skills/.openspec-target` contains the single value `antigravity` — the marker OpenSpec wrote for that target tree. The other trees carry no marker file.

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
| **IMPORTANT** | `pyproject.toml` | Single source of declared deps/Python version; currently empty deps |
| **IMPORTANT** | `openspec/config.yaml` | Workflow schema + Copilot integration; future home of project context/rules |
| **IMPORTANT** | `openspec/changes/**` | Once work starts: the live plan of every change |
| **IMPORTANT** | `.gitignore` | Defines what counts as repo vs local (`.venv`, `.env`, caches) |
| **IMPORTANT** | `.github/workflows/copilot-setup-steps.yml` | How cloud agents bootstrap the OpenSpec CLI |
| **CONTEXTUAL** | `.agents/**`, `.claude/**`, `.opencode/**`, `.github/{skills,prompts,agents}/**` | Generated workflow instructions per tool — read the one for your host tool, never edit by hand |
| **CONTEXTUAL** | `.idea/**` | IDE state; safe to ignore for logic work |
| **CONTEXTUAL** | `src/__init__.py`, `src/models/__init__.py`, `src/services/__init__.py` | Empty markers; only meaningful if a future change gives those packages a role |

---

## 24. Change Impact Areas

Given the current state (no implementation), the real impact map is about *where change lands*:

- Touching **`src/`** → you are creating the first real implementation; it must map every stage to an allowed technique (§10) and stay explainable (§4 criteria 5 & 9); expect it to become the anchor for tests (none exist yet).
- Adding a **dependency** → update `pyproject.toml [project].dependencies`; note the env is uv-managed and **there is no lockfile**; consider that OpenCV is the obvious eventual addition but it is not declared or installed today.
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

11. Update the OpenSpec artifacts (check off tasks; `openspec validate`; sync/archive when appropriate) so plan and reality stay aligned.
12. Re-run the §0 verification commands; report honestly what exists vs what doesn't (state beats optimism here — graders and teammates read this code).
13. If you found a documentation/code conflict, record it (in the change, or as an update to §27 of this file) instead of silently resolving it.

---

## 26. Things Agents Must Not Do

- **Never introduce forbidden techniques:** neural networks, deep learning, pretrained models, YOLO/SSD/Faster R-CNN-style detectors, Haar cascades, external AI services, or libraries that auto-detect the line/signals without team-implemented logic. This is a grading criterion, not a style preference.
- Do not claim or document functionality that does not exist; do not describe the target pipeline (§8) as implemented.
- Do not treat `src/models/` or `src/services/` as implemented architecture; they are empty.
- Do not treat `documents/**` or the notebooks as product code; do not import from notebooks; do not move them.
- Do not delete or rewrite academic materials without explicit justification and user approval.
- Do not hand-edit generated agent files in `.agents/`, `.claude/`, `.opencode/`, `.github/{skills,prompts,agents}` — regenerate them instead.
- Do not invent commands, dependencies, environment variables, hardware interfaces, endpoints, or databases. If something is unknown (e.g., how the robot moves), say it is unknown and where it would be decided.
- Do not commit secrets, tokens, or `.env` files; none exist today and none should be added.
- Do not modify `.venv` contents by hand or commit the virtualenv.
- Do not create an `openspec/` root as a side effect of running commands; do not bypass the opsx workflow for product work.
- Do not "fix" the `markdawn` folder name or the sample `src/main.py` comments silently for aesthetics — both are known and recorded here.

---

## 27. Known Inconsistencies and Gaps

Recorded during the audit; each item is factual with evidence:

1. **Documentation vs code:** Reto 1 describes a complete real-time autonomous system; the codebase is a scaffold with a sample script. The gap is total, not partial.
2. **Empty packages with architectural names:** `src/models/`, `src/services/` exist but contain nothing; the names imply an architecture that has not been designed anywhere.
3. **Environment vs materials:** the class notebooks require `cv2` (+ `sklearn` in nb4); `.venv` has `sklearn` but **not** `cv2`, and `pyproject.toml` declares no dependencies and there is no lockfile — the local environment cannot run the materials, and is not reproducible from the repo.
4. **Stored notebook failure:** `4_Kmeans_Imagenes.ipynb`'s last execution crashed with `ModuleNotFoundError: No module named 'google.colab'` (Colab-only import) — the notebook was last run in the wrong environment.
5. **Broken asset reference:** `documents/markdawn/Reto-1.md` references `media/image1.jpeg` (track photo) but no `media/` directory exists in the repo.
6. **Undefined stop duration:** PARE = "el tiempo establecido por el docente"; no value is fixed in any document of the repo.
7. **Generated trees differ across tools:** `.claude/` variants use `/opsx:<name>` colon syntax + extra frontmatter, `.opencode/` adds a `$ARGUMENTS` line; the other two are byte-identical. Intentional per-tool adaptation — but it means "the same file" is not literally the same everywhere.
8. **Template artefacts in `.gitignore`:** `.ruff_cache/` and `pyrightconfig.json` are mentioned but neither tool is configured; don't assume tooling from the ignore file.
9. **`.idea/` tracked against template advice:** 7 IDE files are committed while the template suggests ignoring `.idea/`; `workspace.xml` is untracked. If this is not intentional, decide explicitly (a change).
10. **No README/name definition:** "OptiPilot" appears only in `pyproject.toml`, `.idea/` files, and paths; the repo contains no description of the project beyond the academic documents.

---

## 28. Known Limitations / Undetermined Items

- No implementation of any challenge capability (see §5).
- No tests, no CI for the product, no lint/format tooling.
- No `README`, `LICENSE`, `CONTRIBUTING`.
- No robot/hardware documentation: actuator interface, camera access (OpenCV `VideoCapture` index, ROS, serial, etc.) — all undetermined; do not assume.
- No specification of the track, sign placement/size, lighting conditions — only the external practice-videos link.
- PARE stop duration and "intentos" (attempts) count are teacher-defined and absent here.
- Dependencies: none declared, none locked; OpenCV (needed for the materials and the challenge) is not installed.
- Environment: OneDrive-hosted repo; `.venv` is large (234 MB) and synced by OneDrive despite being git-ignored.

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
- [ ] I know how I will validate the result (today: manual/interactive; no test infrastructure exists — state this honestly).
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
