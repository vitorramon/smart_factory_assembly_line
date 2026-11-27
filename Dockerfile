# Imagem única para o servidor da linha e para o simulador (o comando escolhe o papel).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends g++ && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy SFAL_ROOT=/app SFAL_DATA_DIR=/data PATH="/app/software/.venv/bin:$PATH"
WORKDIR /app

# dependências primeiro (camada em cache enquanto o lockfile não muda)
COPY software/pyproject.toml software/uv.lock software/
RUN cd software && uv sync --frozen --no-dev --no-install-project

# núcleo do firmware -> biblioteca usada pelo simulador (o mesmo código gravado no ESP32)
COPY firmware/lib firmware/lib
COPY firmware/sim/capi.cpp firmware/sim/build.sh firmware/sim/
RUN ./firmware/sim/build.sh

COPY software software
RUN cd software && uv sync --frozen --no-dev
COPY config config
COPY models models

EXPOSE 8000
CMD ["sfal", "server"]
