# Dockerfile para Hugging Face Spaces (SDK: Docker)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencias
COPY requirements.txt ./ 
RUN pip install --no-cache-dir -r requirements.txt

# Código
COPY . .

# Spaces inyecta PORT; exponemos un puerto por defecto para local
EXPOSE 7860

# Ejecuta FastAPI en 0.0.0.0 y el puerto que provee Spaces
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-7860}"]