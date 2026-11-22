FROM python:3.11.18-slim-trixie@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535 AS dependencies

WORKDIR /build
COPY docs/requirements.txt docs/constraints.txt ./docs/
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip wheel --no-cache-dir --only-binary=:all: \
        --wheel-dir /wheels -c docs/constraints.txt -r docs/requirements.txt

FROM python:3.11.18-slim-trixie@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535 AS runtime

# install runtime libraries for WeasyPrint and image handling without headers
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-xlib-2.0-0 \
    libffi8 \
    libjpeg62-turbo \
    libpng16-16t64 \
    libharfbuzz-subset0 \
    fontconfig \
    shared-mime-info \
    fonts-dejavu-core \
    fonts-liberation \
    fonts-noto \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY docs/requirements.txt docs/constraints.txt ./docs/
# keep downloaded wheels and package installers out of the final filesystem
RUN --mount=type=bind,from=dependencies,source=/wheels,target=/wheels \
    python -m pip install --no-cache-dir --no-index --find-links=/wheels -c docs/constraints.txt -r docs/requirements.txt \
    && python -m pip uninstall --yes setuptools wheel pip \
    && python -c 'import pathlib, shutil, sysconfig; shutil.rmtree(pathlib.Path(sysconfig.get_path("stdlib")) / "ensurepip" / "_bundled")'

COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .

COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh \
    && groupadd --gid 10001 perga \
    && useradd --uid 10001 --gid perga --no-create-home perga \
    && install -d -o perga -g perga /app/data/attachments
ENV PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
ENTRYPOINT ["/app/docker-entrypoint.sh"]
