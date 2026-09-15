# Reuse the team's known-good backend runtime image. It already contains
# Blender 4.2.x and Rokoko Studio Live 1.4.3, which are required by the
# retargeting script. Our source code is copied on top so this repository is
# the canonical application source.
FROM aduy2408/text2sign_backend:latest

WORKDIR /app

COPY apps/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY apps/backend/ /app/
COPY data/dictionaries/dictionary_data.csv /data/dictionaries/dictionary_data.csv

ENV TEXT2SIGN_DATA_ROOT=/data/dictionaries \
    SMPLERX_OUTPUT_DIR=/runtime/smplerx \
    AMASS_OUTPUT_DIR=/runtime/amass \
    FBX_OUTPUT_DIR=/runtime/fbx \
    SMPLX_MODEL_PATH=/models/smplx/SMPLX_NEUTRAL.npz \
    XBOT_FBX_PATH=/app/XBOTXBOT.fbx

RUN mkdir -p /runtime/smplerx /runtime/amass /runtime/fbx /models/smplx

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
