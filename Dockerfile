FROM python:3.14-slim

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# XDG directories inside the container (volumes mount here)
ENV XDG_DATA_HOME=/data \
    XDG_CONFIG_HOME=/config \
    FINGUARD_HOST=0.0.0.0 \
    FINGUARD_PORT=8765

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project metadata first for better layer caching
COPY pyproject.toml ./
COPY README.md ./

# Copy source code
COPY src/ src/

# Install the project and its dependencies
RUN uv pip install --system .

EXPOSE ${FINGUARD_PORT}

# Run the web UI, binding to 0.0.0.0 so it's reachable outside the container
CMD ["sh", "-c", "finguard-ui --port $FINGUARD_PORT"]
