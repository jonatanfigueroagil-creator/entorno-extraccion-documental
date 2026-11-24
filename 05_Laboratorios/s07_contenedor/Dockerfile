# Imagen del pipeline del curso (S07, DEMO del docente). Se construye desde la raíz de la copia del curso:
#   docker build -f 05_Laboratorios/s07_contenedor/Dockerfile -t mi-pipeline:s07 --build-arg VERSION=<git describe> .
# Base fijada por digest: Debian 13 (trixie) con Python 3.12.
FROM python:3.12-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

# Datos públicos de la construcción (nunca secretos: ARG y ENV quedan dentro de la imagen)
ARG VERSION=sin-version
ARG REVISION=desconocida
LABEL org.opencontainers.image.title="mi_pipeline" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}"

# Eventos JSON sin búfer (aparecen al instante en docker logs), sin archivos .pyc y la versión para el registro (no hay Git en la imagen)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TESSERACT_CMD=/usr/bin/tesseract \
    MI_PIPELINE_VERSION=${VERSION}

# Tesseract de Debian con español: el mismo spa.traineddata (tessdata_fast) que instala el curso en Windows
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa tesseract-ocr-osd \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Primero las dependencias: si solo cambia el código, esta capa se reutiliza
COPY 05_Laboratorios/s07_contenedor/requirements-contenedor.txt .
RUN pip install -r requirements-contenedor.txt
COPY 04_pipeline_sbs/ ./04_pipeline_sbs/
RUN pip install --no-deps ./04_pipeline_sbs && rm -rf ./04_pipeline_sbs
COPY mi_pipeline/ ./mi_pipeline/

# Mínimo privilegio: un usuario sin privilegios, con UID y GID explícitos
RUN groupadd --gid 1000 pipeline \
 && useradd --uid 1000 --gid 1000 --no-log-init --create-home pipeline
USER 1000:1000

# Forma exec: el proceso de Python es el PID 1 y recibe las señales de parada
ENTRYPOINT ["python", "-m", "mi_pipeline"]
CMD ["--help"]
