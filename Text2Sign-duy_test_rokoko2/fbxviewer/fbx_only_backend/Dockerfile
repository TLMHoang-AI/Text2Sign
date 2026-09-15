FROM python:3.10-slim

# Install system dependencies for Blender headless
RUN apt-get update && apt-get install -y \
    wget \
    xz-utils \
    libgl1 \
    libxi6 \
    libxrender1 \
    libxkbcommon0 \
    libsm6 \
    libxext6 \
    libx11-6 \
    libxxf86vm1 \
    libxfixes3 \
    && rm -rf /var/lib/apt/lists/*

# Download and install Blender 4.2.8 Linux x64 (LTS)
# Using a reliable mirror or official download link
WORKDIR /usr/local
RUN wget -q https://download.blender.org/release/Blender4.2/blender-4.2.8-linux-x64.tar.xz \
    && tar -xf blender-4.2.8-linux-x64.tar.xz \
    && rm blender-4.2.8-linux-x64.tar.xz \
    && mv blender-4.2.8-linux-x64 blender

ENV BLENDER_BIN=/usr/local/blender/blender

# Set up working directory for the app
WORKDIR /app

# Install Rokoko Studio Live Blender Addon
# We copy the zip file directly and let Blender install it
COPY rokoko-studio-live-blender-1-4-3.zip /tmp/rokoko.zip
RUN echo "import bpy; bpy.ops.preferences.addon_install(filepath='/tmp/rokoko.zip'); bpy.ops.preferences.addon_enable(module='rokoko-studio-live-blender-1-4-3'); bpy.ops.wm.save_userpref()" > /tmp/install_addon.py \
    && ${BLENDER_BIN} -b -P /tmp/install_addon.py \
    && rm /tmp/rokoko.zip /tmp/install_addon.py

# Install Python requirements
COPY requirements_api.txt .
RUN pip install --no-cache-dir -r requirements_api.txt

# Copy the rest of the backend codebase
COPY . .

# Copy external data into image
COPY dictionary_data.csv /dictionary_data.csv


# Expose backend API port
EXPOSE 8000

# Run the FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
