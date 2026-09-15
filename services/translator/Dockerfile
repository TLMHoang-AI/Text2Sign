FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY services/translator/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY text2sign /app/text2sign
COPY services /app/services
COPY data/dictionaries /data/dictionaries

ENV PYTHONPATH=/app \
    DICTIONARY_PATH=/data/dictionaries/dictionary_data.csv

EXPOSE 8001
CMD ["uvicorn", "services.translator.main:app", "--host", "0.0.0.0", "--port", "8001"]
