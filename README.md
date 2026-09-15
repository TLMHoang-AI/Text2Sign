# Text2Sign

End-to-end Vietnamese Text-to-Sign Language pipeline that converts Vietnamese text into a 3D sign-language avatar animation.

Text2Sign combines Vietnamese language processing, sign-dictionary resolution, SMPL-X motion assets, AMASS conversion, Blender-based retargeting, asynchronous backend processing, and browser-based 3D visualization in one modular system.

## Overview

The online translation pipeline is:

```text
Vietnamese Text
      │
      ▼
Vietnamese NLP / Tokenization
      │
      ▼
Canonical Sign Tokens
      │
      ▼
Sign Dictionary Resolution
      │
      ▼
Sign Clip IDs (Dxxxx / Wxxxx)
      │
      ▼
Precomputed SMPL-X Motion Assets
      │
      ▼
SMPL-X → AMASS Conversion
      │
      ▼
Motion Concatenation + Smoothing
      │
      ▼
Blender / Rokoko Retargeting
      │
      ▼
Animated FBX Avatar
      │
      ▼
Three.js Web Viewer
```

The project also contains an optional offline asset-generation path:

```text
Sign Video
   │
   ▼
SMPLer-X
   │
   ▼
SMPL-X Motion Parameters
   │
   ▼
runtime/smplerx/<clip_id>/
```

The online system normally consumes these precomputed sign-motion assets instead of running SMPLer-X for every text request.

## Key Features

- Custom Vietnamese tokenizer designed for sign-language dictionary matching
- Trie-based longest-match phrase extraction
- Canonical sign normalization and dictionary alias handling
- Case-sensitive matching for selected vocabulary
- Vietnamese classifier removal and parenthetical synonym handling
- POS-assisted proper-noun recognition
- Finger spelling for proper names and unresolved names
- Canonical sign token → motion clip ID resolution
- SMPL-X → AMASS motion conversion
- Multi-sign motion concatenation and transition smoothing
- Blender-based retargeting to an FBX avatar
- Browser-based Three.js FBX animation viewer
- Asynchronous processing with FastAPI, Celery, and Redis
- PostgreSQL-backed user and request history
- Docker Compose orchestration
- Optional Prometheus and Grafana monitoring

## System Architecture

```text
                           ┌──────────────────────┐
                           │      Frontend        │
                           │   Three.js Viewer    │
                           └──────────┬───────────┘
                                      │
                                      ▼
                           ┌──────────────────────┐
                           │    FastAPI Backend   │
                           └──────────┬───────────┘
                                      │
                       ┌──────────────┴──────────────┐
                       │                             │
                       ▼                             ▼
              ┌──────────────────┐         ┌──────────────────┐
              │    Translator    │         │  Redis / Celery  │
              │                  │         │                  │
              │  VnTokenizer     │         │ Background Jobs  │
              │  Sign Resolver   │         └────────┬─────────┘
              └────────┬─────────┘                  │
                       │                            │
                       ▼                            ▼
                 Sign Clip IDs               Motion Pipeline
                       │                            │
                       └──────────────┬─────────────┘
                                      ▼
                           ┌──────────────────────┐
                           │ SMPL-X → AMASS       │
                           └──────────┬───────────┘
                                      ▼
                           ┌──────────────────────┐
                           │ Motion Merge         │
                           │ + Smoothing          │
                           └──────────┬───────────┘
                                      ▼
                           ┌──────────────────────┐
                           │ Blender Retargeting  │
                           └──────────┬───────────┘
                                      ▼
                           ┌──────────────────────┐
                           │ Animated FBX         │
                           └──────────┬───────────┘
                                      ▼
                              Three.js Viewer
```

## Vietnamese Text Processing

The translator contains a custom Vietnamese tokenizer built specifically for sign-language vocabulary rather than generic word segmentation.

The tokenizer performs:

- Trie-based longest-match phrase search
- Multiple dictionary priority levels
- Canonical phrase normalization
- Selective case-sensitive matching
- Vietnamese classifier stripping
- Parenthetical and synonym handling
- Domain-specific aliases
- POS-assisted proper-noun detection
- Finger spelling with Vietnamese diacritic normalization

For example, a proper name that is not represented as a full dictionary sign can be converted into individual finger-spelling tokens before clip resolution.

The translator service then resolves canonical tokens to their preferred `Dxxxx` / `Wxxxx` sign clip IDs using `dictionary_data.csv`.

## Motion Pipeline

Each resolved sign clip ID points to a precomputed SMPL-X motion sequence.

During translation, the backend:

1. Loads the requested sign-motion assets.
2. Converts SMPL-X outputs to an AMASS-style representation.
3. Concatenates multiple signs into a continuous sequence.
4. Applies transition and pose smoothing where required.
5. Retargets the resulting animation to the target avatar in Blender.
6. Exports the final animated FBX file.

This keeps the language layer independent from the 3D motion and rendering layer.

## Avatar Retargeting

The current target avatar is:

```text
apps/backend/XBOTXBOT.fbx
```

The source motion is reconstructed from SMPL-X / AMASS parameters and retargeted to the X-Bot rig in Blender. The current production retargeting path uses the Rokoko Studio Live Blender add-on.

The generated FBX is then served to the browser-based viewer.

## Web Application

The frontend uses Three.js and `FBXLoader` to display generated animations.

Current frontend capabilities include:

- Interactive 3D camera controls
- FBX animation playback
- Timeline controls
- Skeleton visualization
- Subtitle synchronization
- User authentication
- Translation history

## Repository Structure

```text
Text2Sign/
│
├── apps/
│   ├── backend/
│   │   ├── api/
│   │   ├── main.py
│   │   ├── Dockerfile
│   │   └── XBOTXBOT.fbx
│   │
│   └── frontend/
│       ├── index.html
│       ├── main.js
│       ├── style.css
│       ├── nginx.conf
│       └── Dockerfile
│
├── text2sign/
│   └── nlp/
│       └── tokenizer.py
│
├── services/
│   ├── translator/
│   │   ├── main.py
│   │   ├── resolver.py
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   │
│   └── smplerx/
│       └── ...
│
├── data/
│   └── dictionaries/
│       └── dictionary_data.csv
│
├── runtime/
│   ├── smplerx/
│   ├── amass/
│   ├── fbx/
│   └── input_videos/
│
├── models/
│   └── .gitkeep
│
├── infra/
│   ├── prometheus/
│   └── grafana/
│
├── experiments/
│   └── mediapipe_blender_prototype/
│
├── scripts/
│   └── preflight.py
│
├── docker-compose.yml
├── .env.example
└── .gitignore
```

## Runtime Services

The default Docker Compose stack contains:

| Service | Role |
|---|---|
| `frontend` | Three.js web interface |
| `backend` | FastAPI application and FBX pipeline API |
| `translator` | Vietnamese text → canonical sign tokens → clip IDs |
| `celery_worker` | Background motion-processing jobs |
| `redis` | Task queue and task state |
| `db` | PostgreSQL user/request database |

Optional profiles:

| Service | Profile | Role |
|---|---|---|
| `smplerx` | `asset-generation` | Generate SMPL-X motion assets from sign videos |
| `prometheus` | `observability` | Metrics collection |
| `grafana` | `observability` | Monitoring dashboard |
| `node_exporter` | `observability` | Host metrics |

## Private Model and Motion Assets

Some runtime assets are intentionally **not distributed through this public repository**.

This includes private/licensed model files, SMPLer-X pretrained weights, and the full precomputed motion library.

Expected local structure:

```text
models/
└── smplx/
    └── SMPLX_NEUTRAL.npz

runtime/
└── smplerx/
    ├── D0001B/
    ├── D0002/
    ├── D0003/
    └── ...
```

SMPLer-X pretrained weights should also be provided separately when using the optional asset-generation pipeline.

These files are excluded from Git intentionally. The repository contains the source code and runtime contracts, while private or licensed assets remain local to authorized users.

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/TLMHoang-AI/Text2Sign.git
cd Text2Sign
git checkout integration/unified-text2sign
```

### 2. Configure the environment

```bash
cp .env.example .env
```

Edit `.env` if custom ports or host paths are required.

### 3. Provide required private assets

Place the SMPL-X body model at:

```text
models/smplx/SMPLX_NEUTRAL.npz
```

Place the precomputed sign-motion library under:

```text
runtime/smplerx/
```

### 4. Run the preflight check

```bash
python scripts/preflight.py
```

The preflight script checks whether the required external assets are available before starting the full motion pipeline.

### 5. Start the application

```bash
docker compose up --build
```

Default local services:

```text
Frontend:    http://localhost:3000
Backend:     http://localhost:8000
Translator:  http://localhost:8001
```

## Translator API

The translator service exposes:

```http
POST /translate
```

Request:

```json
{
  "sentence": "Tôi tên là Hoàng"
}
```

The service performs:

```text
sentence
   ↓
VnTokenizer
   ↓
canonical sign tokens
   ↓
dictionary resolver
   ↓
sign clip IDs
```

Response shape:

```json
{
  "videos": ["Dxxxx", "Wxxxx"],
  "tokens": ["..."],
  "unresolved": []
}
```

In strict mode, unresolved tokens cause the translator to return an error instead of silently selecting unrelated motion clips.

## Backend Translation Pipeline

The backend receives Vietnamese text through its translation endpoint and submits the processing job asynchronously.

At runtime it:

```text
Text Request
    │
    ▼
Translator Service
    │
    ▼
Sign Clip IDs
    │
    ▼
Celery Worker
    │
    ▼
SMPL-X → AMASS
    │
    ▼
Motion Merge / Smoothing
    │
    ▼
Blender Retargeting
    │
    ▼
Generated FBX
```

The frontend polls the backend for task completion and loads the resulting animation when processing is finished.

## Asset Generation

The online pipeline normally uses precomputed motion assets.

New sign-motion assets can optionally be generated from sign-language videos using SMPLer-X:

```text
Sign Video
    │
    ▼
SMPLer-X
    │
    ▼
SMPL-X Parameters
    │
    ▼
runtime/smplerx/<clip_id>/
```

The SMPLer-X service requires an NVIDIA GPU, NVIDIA Container Toolkit, and the corresponding pretrained model files.

Example:

```bash
docker compose --profile asset-generation run --rm smplerx \
  --videos_folder /videos \
  --demo_results_root /output \
  --fps 30
```

## Monitoring

Optional monitoring services can be started with:

```bash
docker compose --profile observability up
```

Default ports:

```text
Prometheus: http://localhost:9090
Grafana:    http://localhost:3001
```

## Technology Stack

### NLP

- Python
- pandas
- underthesea
- Trie-based dictionary matching

### Motion and 3D

- SMPL-X
- SMPLer-X
- AMASS-style motion representation
- NumPy
- SciPy
- Blender
- Rokoko Studio Live
- FBX

### Backend

- FastAPI
- Celery
- Redis
- PostgreSQL
- SQLAlchemy

### Frontend

- JavaScript
- Three.js
- FBXLoader
- Nginx

### Infrastructure

- Docker
- Docker Compose
- Prometheus
- Grafana

## Project Status

The repository contains the source architecture for the complete application flow:

```text
Vietnamese Text
→ Sign Tokenization
→ Sign Clip Resolution
→ Motion Processing
→ Avatar Retargeting
→ FBX Generation
→ Web Visualization
```

Private model files and the precomputed sign-motion library are intentionally excluded from the public repository.

## Demo

The following examples show generated Text2Sign avatar animations from the team's prototype pipeline.

<figure>
  <video src="https://github.com/user-attachments/assets/15d8c85d-6f60-43a8-800a-8a6891e9259a" muted controls="controls" style="max-width: 100%;">
  </video>
  <figcaption align="center"><i>Hoàng hôn ở cầu Long Biên rất đẹp</i></figcaption>
</figure>

<br/>

<figure>
  <video src="https://github.com/user-attachments/assets/32ff701b-5eed-4e8e-8f60-fc5d4fb2ee43" muted controls="controls" style="max-width: 100%;">
  </video>
  <figcaption align="center"><i>Chú của bạn đã 40 tuổi</i></figcaption>
</figure>

## Future Work

Potential directions include:

- Vietnamese text → sign-language grammar transformation
- Improved out-of-vocabulary handling
- Better sign co-articulation and motion transitions
- Facial-expression generation
- More natural upper-body motion
- Real-time animation generation
- Additional avatar support

## License

Project license information will be added later.

External models, datasets, Blender add-ons, and pretrained components may be subject to their own licenses and distribution terms.
