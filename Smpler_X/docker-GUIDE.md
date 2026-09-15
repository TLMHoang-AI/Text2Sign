# SMPLer-X Docker Guide

This guide explains how to build and run the SMPLer-X inference pipeline using Docker and Docker Compose. This ensures you don't have to deal with complex Python environments, CUDA compatibility, or missing packages on your host machine.

## 1. Prerequisites
- Docker
- Docker Compose v2 (e.g., `docker compose ...`)
- NVIDIA GPU with drivers installed
- NVIDIA Container Toolkit (to allow Docker to access your GPU)

## 2. Prepare the Folders
You need to have the following folders ready on your host machine to mount into the container:

### a) `pretrained_models/`
This folder must be placed inside the `SMPLer-X` directory (i.e. `./pretrained_models`). It contains the large model weights which are not baked into the Docker image because of their size.
- Pretrained weights like `smpler_x_h32.pth.tar`
- Mmdet detector weights inside `pretrained_models/mmdet/`

### b) Videos Folder
The folder containing your input videos (`.mp4`, `.avi`, etc). This folder will be mounted into the container as `/videos`.

### c) Output Folder
The folder where the inference results (the `.npz` files) will be saved. This folder will be mounted into the container as `/output`.

## 3. Build the Image
Before running the container, you need to build the Docker image once to install all dependencies. 
Open a terminal in the `SMPLer-X` folder and run:

```bash
docker compose build
```
*(Lưu ý: Quá trình build có thế mất một chút thời gian).*

## 4. Run the Container
There are a few ways to run the container depending on the model you want to use and where your files are located. You can pass environment variables in front of the `docker compose run` command to configure the mounts.

### 4.1. Quick Start (Default Model: `smpler_x_h32`)
To run using the default high-resolution model (`smpler_x_h32`) on a videos folder `~/my_videos` and output to `~/smplerx_results`:

```bash
VIDEOS_FOLDER=~/my_videos OUTPUT_DIR=~/smplerx_results \
docker compose run --rm smplerx --videos_folder /videos --demo_results_root /output --fps 30
```

### 4.2. Using a Specific Model (e.g., `smpler_x_s32` for speed)
To use a smaller, faster model (e.g. `smpler_x_s32`), you need to set the `PRETRAINED_MODEL` variable:

```bash
PRETRAINED_MODEL=smpler_x_s32 VIDEOS_FOLDER=~/my_videos OUTPUT_DIR=~/smplerx_results \
docker compose run --rm smplerx --videos_folder /videos --demo_results_root /output --fps 30
```

## 5. What gets mounted? (Volumes Explained)
Understanding the volume mappings in `docker-compose.yml`:

| Host Path (On your machine) | Container Path (Inside Docker) | Purpose |
|-----------------------------|--------------------------------|---------|
| `./pretrained_models` | `/workspace/SMPLer-X/pretrained_models` | Provides the heavy model `.tar` files. Mounted as read-only (`ro`). |
| `${VIDEOS_FOLDER}` | `/videos` | Your input videos. This is what `--videos_folder /videos` points to in the python command. Mounted as read-only (`ro`). |
| `${OUTPUT_DIR}` | `/output` | Where the script saves the `.npz` results. This is what `--demo_results_root /output` points to. |

## 6. Accessing the Interactive Shell
If you need to enter the container manually for debugging or running custom commands, you can override the entrypoint:

```bash
docker compose run --rm --entrypoint bash smplerx
```
This will drop you into a root bash shell inside the container at `/workspace/SMPLer-X/main`. From there, you can manually run python scripts like `python batch_inference.py ...`.
