# Text2Sign – Docker Deployment

Hướng dẫn deploy toàn bộ hệ thống bằng Docker.

---

## Yêu cầu

- Docker 20.10+
- Docker Compose v2+

Kiểm tra:

```bash
docker --version
docker compose version
```

---

## 1. Khởi chạy

```bash
cd fbxviewer
docker compose up -d
```

Chờ ~30 giây cho tất cả services khởi động xong.

## 2. Truy cập

| Service | URL | Tài khoản |
|---------|-----|-----------|
| Frontend | http://localhost:3000 | — |
| API Docs | http://localhost:8000/docs | — |
| Grafana | http://localhost:3001 | admin / admin |
| Prometheus | http://localhost:9090 | — |

## 3. Kiểm tra trạng thái

```bash
docker compose ps
```

Tất cả containers phải có trạng thái `Up`:

```
NAME                    STATUS
fbxviewer_backend       Up
fbxviewer_db           Up (healthy)
fbxviewer_grafana      Up
fbxviewer_prometheus    Up
fbxviewer_redis        Up
```

## 4. Xem logs

```bash
# Tất cả:
docker compose logs -f

# Chỉ backend:
docker compose logs -f backend

# Chỉ Redis:
docker compose logs -f redis
```

## 5. Dừng

```bash
docker compose down
```

Xóa luôn dữ liệu (database, queue):

```bash
docker compose down -v
```

---

## Cấu trúc Docker

```
fbxviewer/
├── docker-compose.yml          # Orchestration file — chạy ở đây
│
├── prometheus/
│   └── prometheus.yml          # Prometheus scrape config
│
├── grafana/
│   └── provisioning/           # Auto-provisioned dashboards & datasources
│       ├── datasources/
│       │   └── prometheus.yml  # Grafana → Prometheus datasource
│       └── dashboards/
│           ├── dashboards.yml  # Dashboard manifest
│           └── jobs-view.json  # Jobs monitoring dashboard
│
└── fbx_only_backend/           # Backend container
    ├── Dockerfile              # Container image build
    ├── Dockerfile.dockerignore
    ├── main.py                 # FastAPI entry point
    ├── pseudo_api.py           # Mock translation API
    ├── blender_server.py       # Blender TCP server (warm)
    ├── blender_retarget_auto.py # Blender retarget script
    ├── batch_convert_amass.py  # SMPL-X → AMASS converter
    ├── requirements_api.txt    # Python dependencies
    ├── dictionary_data.csv     # Video ID → word mapping
    ├── XBOTXBOT.fbx            # X-Bot skeleton model
    ├── amass_output/           # AMASS intermediate data (.npz)
    │   └── *.npz
    ├── xbot_retargeted/        # ← mount: host ↔ /app/xbot_retargeted
    │   └── *.fbx              # Final animation output
    └── api/                    # API route modules
        ├── pipeline.py         # Core: AMASS → Blender → FBX
        ├── blender_client.py   # Blender socket client
        ├── queue.py           # Redis task queue + worker
        ├── config.py          # Paths & constants
        ├── db.py              # PostgreSQL connection
        ├── auth.py            # JWT authentication
        ├── helpers.py         # Utils
        ├── tasks.py           # GET/POST/DELETE /tasks/*
        ├── translate.py       # POST /translate
        ├── convert.py         # POST /convert
        ├── fbx.py            # GET /fbx
        ├── clips.py          # GET /clips
        ├── users.py          # /users/signup, /login, /history
        └── models.py         # Pydantic + SQLAlchemy models
```

> **Lưu ý:** Thư mục `xbot_retargeted/` được **mount** giữa host và container. Các file `.fbx` xuất ra sẽ xuất hiện trên cả host lẫn container.

### Host directories (mount points cần tồn tại trên host)

Vì `docker-compose.yml` bind mount các thư mục từ host, cần đảm bảo các thư mục này tồn tại trước khi chạy:

| Host path | Container path | Mount type | Mô tả |
|-----------|---------------|-----------|--------|
| `fbx_only_backend/xbot_retargeted/` | `/app/xbot_retargeted` | bind mount | FBX animation output |
| `fbx_only_backend/amass_output/` | `/app/amass_output` | *(trong image)* | AMASS intermediate `.npz` |
| `../output_smplerx/` | `/output_smplerx` | bind mount | SMPL-X input data |
| `../models/` | `/models` | bind mount | SMPL-X model files |

### 6 containers chạy song song

| Container | Port (host) | Port nội bộ | Mô tả |
|-----------|:-----------:|:-----------:|--------|
| `fbxviewer_backend` | 8000 | 8000 | FastAPI + Task Worker |
| `fbxviewer_db` | 5433 | 5432 | PostgreSQL 15 |
| `fbxviewer_redis` | 6380 | 6379 | Redis 7 (task queue) |
| `fbxviewer_prometheus` | 9090 | 9090 | Metrics collection |
| `fbxviewer_node_exporter` | 9100 | 9100 | System metrics |
| `fbxviewer_grafana` | 3001 | 3000 | Dashboards UI |

### Luồng dữ liệu

```
Browser (:3000)
    ↓ HTTP
Backend (:8000)
    ├── Redis (:6379)         ← Task queue & cache
    ├── PostgreSQL (:5432)    ← User & history storage
    └── Blender (internal)    ← FBX rendering
         ↓
    Prometheus (:9090) ← metrics
         ↓
    Grafana (:3001)           ← Dashboards
```

---

## Cấu hình

### Translation API URL

Mặc định backend trỏ vào **Pseudo API (mock)** trên máy host:

```yaml
# docker-compose.yml — backend service
environment:
  - TRANSLATE_API_URL=http://host.docker.internal:8001/translate
```

Đổi URL này nếu dùng translation API thật:

```yaml
environment:
  - TRANSLATE_API_URL=https://your-translate-api.example.com/translate
```

Hoặc chạy pseudo API bên trong container cùng backend thay vì trên host.

### Database URL

```yaml
environment:
  - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/fbxviewer
```

### Redis

```yaml
environment:
  - REDIS_HOST=redis
  - REDIS_PORT=6379
```

---

## Khắc phục sự cố

### Backend không start

```bash
docker compose logs backend
docker compose up -d --build backend
```

### Database chưa ready

```bash
docker compose exec db pg_isready -U postgres
```

### Xóa toàn bộ và bắt đầu lại

```bash
docker compose down -v --remove-orphans
docker compose up -d
```

### Reset chỉ database

```bash
docker compose exec db psql -U postgres -c "DROP DATABASE fbxviewer;"
docker compose exec db psql -U postgres -c "CREATE DATABASE fbxviewer;"
```
