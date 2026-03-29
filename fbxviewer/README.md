# FBX Animation Viewer

> Web viewer + pipeline backend cho Text2Sign. Nhận text → sinh ảnh pose → retarget FBX → xem 3D trực tiếp trên trình duyệt.

---

## 🗺️ Kiến trúc tổng quan

```
[Browser :3000]  ←→  [Backend :8000]  ←→  [Redis :6379]
                          ↕                      ↕
                  [Blender (warm server)]  [Worker (queue)]
                          ↕
                  [Pseudo API :8001]
```

| Service | Port | Vai trò |
|---|---|---|
| **Frontend** | `3000` | Giao diện web viewer (HTML/JS, serve bằng http-server) |
| **Backend** (FastAPI) | `8000` | Nhận request, đẩy task vào Redis queue |
| **Redis** | `6379` | Task queue trung gian, lưu trạng thái task |
| **Pseudo API** | `8001` | Mock translation API (trả về video ID giả) |
| **Blender Server** | `9999` (internal TCP) | Luôn warm, nhận lệnh retarget qua socket |

---

## 🚀 Khởi động từng service

### 0. Yêu cầu trước
- Python env `ml2` với conda (đã có sẵn)
- Blender đã cài và biến môi trường `BLENDER_BIN` được set

```bash
export BLENDER_BIN=/opt/blender-4.2.8/blender   # thay bằng đường dẫn thật
```

### 1. Redis (phải chạy trước tất cả)

```bash
# Chạy một lần rồi tự chạy ngầm
sudo systemctl start redis
# Hoặc nếu dùng systemctl không được:
redis-server --daemonize yes

# Kiểm tra Redis đang sống:
redis-cli ping   # → PONG
```

### 2. Backend (FastAPI + Task Worker)

```bash
conda activate ml2
cd fbxviewer/fbx_only_backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

Worker task queue được khởi động **tự động** cùng FastAPI (trong `lifespan`).
Blender warm server cũng được bật ngầm tự động khi FastAPI start.

API docs: http://localhost:8000/docs

### 3. Pseudo Translation API

Cần chạy **riêng song song** với Backend (terminal khác):

```bash
conda activate ml2
cd fbxviewer/fbx_only_backend
python pseudo_api.py
```

Chạy ở: http://localhost:8001

### 4. Frontend

```bash
cd fbxviewer
# Dùng bất kỳ http server nào, VD:
npx http-server . -p 3000
# Hoặc:
python3 -m http.server 3000
```

Mở trình duyệt: **http://localhost:3000**

> ⚠️ **Không mở `index.html` trực tiếp** bằng `file://` — browser sẽ chặn CORS.

---

## 📋 Thứ tự khởi động (copy-paste)

Mở **4 terminal** riêng, chạy theo thứ tự:

```bash
# Terminal 1 — Redis
sudo systemctl start redis

# Terminal 2 — Backend
conda activate ml2 && cd fbxviewer/fbx_only_backend && uvicorn main:app --host 0.0.0.0 --port 8000

# Terminal 3 — Pseudo API
conda activate ml2 && cd fbxviewer/fbx_only_backend && python pseudo_api.py

# Terminal 4 — Frontend
cd fbxviewer && npx http-server . -p 3000
```

---

## 🔌 API Endpoints chính

| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/` | Health check |
| `GET` | `/clips` | List các folder trong `output_smplerx/` |
| `POST` | `/translate` | Submit câu văn bản → trả `task_id` ngay |
| `POST` | `/convert` | Submit convert thủ công → trả `task_id` ngay |
| `GET` | `/tasks` | List tất cả task đang có trong Redis |
| `GET` | `/tasks/{id}` | Poll kết quả của 1 task |
| `DELETE` | `/tasks/{id}` | Xóa task khỏi Redis |
| `GET` | `/fbx` | List file `.fbx` đã xuất |
| `GET` | `/fbx/{filename}` | Download file FBX |

### Luồng hoạt động điển hình

```
1. Frontend POST /translate {"sentence": "xin chào"}
2. Backend trả về {"task_id": "abc-123", "status": "pending"}
3. Frontend poll GET /tasks/abc-123 mỗi 2 giây
4. Khi status = "done" → lấy result.output_files[] để load FBX viewer
```

---

## 📁 Cấu trúc thư mục

```
fbxviewer/
├── index.html          ← Frontend chính
├── main.js             ← JS logic (Three.js viewer + polling)
├── style.css           ← Giao diện
├── pseudo_api.py       ← Mock translation API (port 8001)
└── fbx_only_backend/
    ├── main.py                 ← FastAPI app entry point (port 8000)
    ├── pseudo_api.py           ← Runner cho pseudo API
    ├── requirements_api.txt    ← Python deps (fastapi, uvicorn, redis, ...)
    ├── blender_server.py       ← Blender TCP socket server (port 9999 internal)
    ├── blender_retarget_auto.py← Script retarget chạy trong Blender
    ├── batch_convert_amass.py  ← Convert SMPL-X → AMASS
    └── api/
        ├── queue.py            ← Redis task queue + worker
        ├── tasks.py            ← Endpoints /tasks/*
        ├── convert.py          ← Endpoint /convert
        ├── translate.py        ← Endpoint /translate
        ├── pipeline.py         ← Pipeline logic (AMASS → Blender → FBX)
        ├── blender_client.py   ← Client kết nối Blender server
        ├── models.py           ← Pydantic request models
        ├── config.py           ← Paths, constants
        └── helpers.py          ← Utilities
```

---

## 🎮 Điều khiển 3D Viewer

| Action | Cách dùng |
|---|---|
| Xoay nhân vật | Drag chuột trái |
| Zoom | Scroll chuột |
| Pan | Drag chuột phải |
| Play / Pause | Nút ▶ hoặc phím `Space` |
| Reset camera | Nút "Reset" hoặc phím `R` |
| Auto-rotate 360° | Toggle "Auto Rotate" ở sidebar |
