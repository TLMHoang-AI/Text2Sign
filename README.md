# Text2Sign

**Text2Sign** is an end-to-end Vietnamese Text-to-Sign Language system that transforms Vietnamese sentences into continuous 3D avatar animations.

Rather than treating sign language as a simple word-to-video lookup problem, the project combines **Vietnamese language processing**, **sign-level dictionary resolution**, **human motion representations**, **motion composition**, **3D retargeting**, and **interactive web visualization** in one modular pipeline.

<p align="center">
  <strong>Vietnamese Text → Sign Tokens → Sign Motion → 3D Avatar Animation</strong>
</p>

---

## Demo

The following examples show generated avatar animations from the team's Text2Sign prototype pipeline. The corresponding sample sign videos are now included in the repository so the demo inputs remain traceable alongside the implementation.

### Example 1 — Cầu Long Biên

<figure>
  <video src="https://github.com/user-attachments/assets/15d8c85d-6f60-43a8-800a-8a6891e9259a" muted controls="controls" style="max-width: 100%;">
  </video>
  <figcaption align="center"><i>“Hoàng hôn ở cầu Long Biên rất đẹp”</i></figcaption>
</figure>

**Sample video:** [`data/dictionaries/caulongbien.mp4`](data/dictionaries/caulongbien.mp4)

### Example 2 — Chú của bạn

<figure>
  <video src="https://github.com/user-attachments/assets/32ff701b-5eed-4e8e-8f60-fc5d4fb2ee43" muted controls="controls" style="max-width: 100%;">
  </video>
  <figcaption align="center"><i>“Chú của bạn đã 40 tuổi”</i></figcaption>
</figure>

**Sample video:** [`data/dictionaries/chuacuaban.mp4`](data/dictionaries/chuacuaban.mp4)

These two files are small public examples from the dictionary/video side of the pipeline. They are not the complete sign-video or precomputed motion library used by the full system.

---

## What Text2Sign Does

At inference time, the user provides a Vietnamese sentence. The system first converts that sentence into sign-level units, resolves those units to motion clips, combines the corresponding motion sequences, retargets the result to a 3D avatar, and finally renders the animation in the browser.

```text
Vietnamese sentence
        │
        ▼
Custom Vietnamese tokenizer
        │
        ▼
Canonical sign tokens
        │
        ▼
Sign dictionary resolver
        │
        ▼
Sign clip IDs
        │
        ▼
Precomputed SMPL-X motion assets
        │
        ▼
SMPL-X → AMASS conversion
        │
        ▼
Motion concatenation + smoothing
        │
        ▼
Blender / Rokoko retargeting
        │
        ▼
Animated FBX avatar
        │
        ▼
Three.js web viewer
```

The online translation path uses **precomputed sign-motion assets**, so [SMPLer-X (Cai et al., 2023)](https://proceedings.neurips.cc/paper_files/paper/2023/hash/2614947a25d7c435bcd56c51958ddcb1-Abstract-Datasets_and_Benchmarks.html) does not need to run for every text request.

---

## Why This Pipeline

Text-to-sign generation is not only a natural-language problem and not only an animation problem. A usable system needs several layers to work together:

- Vietnamese text must be segmented into meaningful sign-level units.
- Dictionary variants and multi-word expressions must map to a canonical representation.
- Proper names and out-of-dictionary names need a fallback such as finger spelling.
- Individual sign motions must be converted into a common representation and joined into a continuous sequence.
- Motion transitions need smoothing to reduce abrupt discontinuities.
- The generated motion must be retargeted onto an avatar that can be displayed interactively.

Text2Sign is designed around these boundaries so that the language, motion, retargeting, backend, and visualization layers can evolve independently.

---

## Core Components

### Vietnamese Sign-Aware Tokenization

The language front-end uses a custom `VnTokenizer` built specifically for sign-language dictionary matching rather than generic Vietnamese word segmentation.

It includes:

- Trie-based longest-match phrase search
- Multiple dictionary priority levels
- Canonical phrase normalization
- Selective case-sensitive matching
- Vietnamese classifier stripping
- Parenthetical and synonym handling
- Domain-specific aliases
- POS-assisted proper-noun detection
- Finger spelling with Vietnamese diacritic normalization

A proper name that does not exist as a complete dictionary sign can therefore be decomposed into finger-spelling tokens instead of being silently discarded.

### Sign Resolution

Canonical tokens are resolved against `dictionary_data.csv` to obtain the preferred `Dxxxx` / `Wxxxx` motion clip IDs.

The translator runs in strict mode by default: unresolved tokens are reported explicitly rather than replaced with unrelated random clips.

```text
Vietnamese text
      ↓
VnTokenizer
      ↓
canonical signs
      ↓
SignResolver
      ↓
Dxxxx / Wxxxx clip IDs
```

### Motion Representation and Composition

Each sign clip corresponds to a precomputed SMPL-X motion sequence. The backend converts these sequences to an AMASS-style representation before joining them into a longer animation.

The motion stage handles:

- SMPL-X → AMASS conversion
- Sign-by-sign sequence assembly
- Motion concatenation
- Transition smoothing
- Pose stabilization
- Final sequence preparation for retargeting

This motion-based approach allows the final avatar animation to be generated independently from the original source videos.

### 3D Avatar Retargeting

The composed motion is reconstructed in Blender and retargeted to the current X-Bot FBX avatar using the Blender/Rokoko retargeting pipeline.

```text
AMASS motion
     ↓
SMPL-X source skeleton
     ↓
Blender retargeting
     ↓
X-Bot rig
     ↓
Animated FBX
```

The resulting FBX is then served to the frontend.

### Interactive Web Viewer

The web application uses Three.js and `FBXLoader` to display generated animations directly in the browser.

Current viewer functionality includes:

- Interactive 3D camera controls
- FBX animation playback
- Timeline controls
- Skeleton visualization
- Subtitle synchronization
- User authentication
- Translation history

---

## Two Complementary Pipelines

Text2Sign separates **motion-asset creation** from **online text translation**.

### Offline Motion-Asset Generation

Sign-language videos can be processed with [**SMPLer-X** (Cai et al., 2023)](https://proceedings.neurips.cc/paper_files/paper/2023/hash/2614947a25d7c435bcd56c51958ddcb1-Abstract-Datasets_and_Benchmarks.html) to estimate expressive human pose and shape and create reusable SMPL-X motion assets.

```text
Sign video
   ↓
SMPLer-X
   ↓
SMPL-X motion parameters
   ↓
Per-sign motion library
```

This stage is performed ahead of time and requires the corresponding SMPLer-X model weights and GPU environment.

### Online Text-to-Sign Generation

```text
Vietnamese text
   ↓
Sign-aware NLP
   ↓
Sign clip lookup
   ↓
Existing motion assets
   ↓
Motion composition
   ↓
Avatar retargeting
   ↓
Web visualization
```

Separating the two stages keeps online generation significantly lighter than rerunning human-pose estimation for every request.

---

## System Architecture

```text
                    ┌──────────────────────────┐
                    │      Web Frontend        │
                    │     Three.js Viewer      │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │      FastAPI Backend     │
                    └────────────┬─────────────┘
                                 │
                 ┌───────────────┴────────────────┐
                 │                                │
                 ▼                                ▼
        ┌───────────────────┐           ┌───────────────────┐
        │    Translator     │           │   Celery / Redis  │
        │                   │           │                   │
        │  VnTokenizer      │           │ Background Jobs   │
        │  SignResolver     │           └─────────┬─────────┘
        └─────────┬─────────┘                     │
                  │                               │
                  ▼                               ▼
           Sign Clip IDs                 Motion Processing
                  │                               │
                  └───────────────┬───────────────┘
                                  ▼
                       ┌─────────────────────┐
                       │ SMPL-X → AMASS      │
                       └──────────┬──────────┘
                                  ▼
                       ┌─────────────────────┐
                       │ Merge + Smoothing   │
                       └──────────┬──────────┘
                                  ▼
                       ┌─────────────────────┐
                       │ Blender Retargeting │
                       └──────────┬──────────┘
                                  ▼
                       ┌─────────────────────┐
                       │   Animated FBX      │
                       └─────────────────────┘
```

PostgreSQL stores user/request history, while Prometheus and Grafana can optionally be enabled for monitoring.

---

## Repository Layout

```text
Text2Sign/
├── apps/
│   ├── backend/               # FastAPI, Celery, AMASS and retarget pipeline
│   └── frontend/              # Three.js web viewer
│
├── text2sign/
│   └── nlp/                   # Vietnamese sign-aware tokenizer
│
├── services/
│   ├── translator/            # Token → clip-ID translation service
│   └── smplerx/               # Offline motion-asset generation service
│
├── data/
│   └── dictionaries/
│       ├── dictionary_data.csv   # Sign dictionary metadata
│       ├── caulongbien.mp4       # Public demo sign video
│       └── chuacuaban.mp4        # Public demo sign video
│
├── runtime/
│   ├── smplerx/               # Precomputed sign motions
│   ├── amass/                 # Converted / merged motion
│   └── fbx/                   # Generated animations
│
├── models/                    # Local/private model assets
├── infra/                     # Prometheus / Grafana
├── experiments/               # Earlier prototypes and experiments
├── scripts/                   # Utility and validation scripts
└── docker-compose.yml
```

---

## Technology Stack

| Area | Technologies |
|---|---|
| Vietnamese NLP | Python, pandas, underthesea, Trie matching |
| Human Motion | SMPL-X, SMPLer-X, AMASS, NumPy, SciPy |
| 3D / Retargeting | Blender, Rokoko Studio Live, FBX |
| Backend | FastAPI, Celery, Redis, PostgreSQL, SQLAlchemy |
| Frontend | JavaScript, Three.js, FBXLoader, Nginx |
| Infrastructure | Docker, Docker Compose, Prometheus, Grafana |

---

## Public Repository and Private Assets

The source code is public, while several runtime assets are intentionally kept outside the repository.

Two small sign-video examples used in the README demo are included under `data/dictionaries/`. The complete video/motion collection is still kept outside the public repository.

Not distributed through Git:

- SMPL-X body model files
- SMPLer-X pretrained weights
- Full sign-video and precomputed sign-motion libraries
- Other private or licensed model assets

The application expects authorized users to provide these assets locally. This separation keeps the repository focused on the implementation while avoiding redistribution of large, private, or separately licensed model files.

---

## Running the Project

The repository includes Docker-based orchestration for the translator, backend, worker, database, Redis, frontend, and optional monitoring services.

For a configured development machine with the required private assets available, the main stack can be launched with:

```bash
cp .env.example .env
python scripts/preflight.py
docker compose up --build
```

The preflight script verifies the external assets required by the motion pipeline before startup.

> This repository intentionally does not bundle private model weights or the complete motion library, so a fresh clone alone is not sufficient to reproduce the full animation pipeline without those assets.

---

## Current Direction

The current system establishes a complete architecture from Vietnamese text to browser-rendered avatar animation. Ongoing work is focused on improving the quality of the generated signing rather than only expanding the software stack.

Key research and engineering directions include:

- Vietnamese text → sign-language grammar transformation
- Better out-of-vocabulary handling
- More natural sign co-articulation
- Learned or adaptive motion transitions
- Facial-expression generation
- Improved upper-body dynamics
- Lower-latency animation generation
- Support for additional avatar rigs

---

## References

Text2Sign uses **SMPLer-X** in the offline motion-asset generation stage:

- Cai, Z., Yin, W., Cong, W., Zhang, H., Ren, Y., Liu, Z., & Loy, C. C. (2023). **SMPLer-X: Scaling Up Expressive Human Pose and Shape Estimation.** *Advances in Neural Information Processing Systems (NeurIPS 2023), 36*, 30799–30825. [Paper](https://proceedings.neurips.cc/paper_files/paper/2023/hash/2614947a25d7c435bcd56c51958ddcb1-Abstract-Datasets_and_Benchmarks.html)

<details>
<summary>BibTeX</summary>

```bibtex
@inproceedings{NEURIPS2023_2614947a,
  author = {Cai, Zhongang and Yin, Wanqi and Cong, Wei and Zhang, Hongwen and Ren, Yiming and Liu, Ziwei and Loy, Chen Change},
  booktitle = {Advances in Neural Information Processing Systems},
  editor = {A. Oh and T. Neumann and A. Globerson and K. Saenko and M. Hardt and S. Levine},
  pages = {30799--30825},
  publisher = {Curran Associates, Inc.},
  title = {SMPLer-X: Scaling Up Expressive Human Pose and Shape Estimation},
  url = {https://proceedings.neurips.cc/paper_files/paper/2023/hash/2614947a25d7c435bcd56c51958ddcb1-Abstract-Datasets_and_Benchmarks.html},
  volume = {36},
  year = {2023}
}
```

</details>

---

## License

Project license information will be added later.

External models, datasets, Blender add-ons, and pretrained components may be subject to their own licenses and distribution terms.
