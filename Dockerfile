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

# Forma shell (no exec array) para que ${PORT} se expanda en runtime: Railway
# inyecta su propio PORT dinámico; docker-compose local no lo define y cae al
# default 8901 fijado arriba.
CMD python -m brain.server --profiles profiles --data data --host 0.0.0.0 --port ${PORT:-8901}
