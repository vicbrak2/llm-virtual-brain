FROM python:3.12-slim

WORKDIR /app

# Dependencias primero (mejor cache de capas)
COPY pyproject.toml setup.py README.md ./
COPY brain/ brain/
RUN pip install --no-cache-dir ".[server]"

# UI y perfiles base (en runtime se pueden montar como volúmenes)
COPY ui/ ui/
COPY profiles/ profiles/

ENV PYTHONUNBUFFERED=1 \
    PORT=8901

EXPOSE 8901

CMD ["python", "-m", "brain.server", "--profiles", "profiles", "--data", "data", "--host", "0.0.0.0", "--port", "8901"]
