FROM nginx:1.31.9-trixie@sha256:84f7876d21d154885f99554d7ae325d8c2213f9169726ea7ab60642f2573a787

ARG ZLIB_MIN_VERSION=1:1.3.dfsg+really1.3.1-1+deb13u1

# patch zlib while
RUN apt-get update \
    && apt-get install -y --no-install-recommends --only-upgrade zlib1g \
    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' zlib1g)" ge "$ZLIB_MIN_VERSION" \
    && rm -rf /var/lib/apt/lists/*
