FROM python:3.14-slim

# Python behavior
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# XDG directories used by the app (these are the directories we will ensure are owned by the runtime UID)
ENV XDG_DATA_HOME=/data \
    XDG_CONFIG_HOME=/config \
    FINGUARD_HOST=0.0.0.0 \
    FINGUARD_PORT=8765

WORKDIR /app

# Install minimal packages required to fetch gosu and run the app.
# We purposely avoid extra build deps here; keep the image small.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg2 dirmngr gosu; \
    rm -rf /var/lib/apt/lists/*

# If the 'gosu' Debian package isn't available for some platforms, the above will
# still try to install it; if you prefer, you can replace the 'gosu' apt install
# with a download of the binary from GitHub releases and verification steps.

# Copy uv binary (fast dependency resolver)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project metadata first for better caching
COPY pyproject.toml README.md ./

# Copy source code
COPY src/ src/

# Install dependencies
RUN uv pip install --system .

# Entrypoint: create a runtime user matching host UID/GID and drop privileges
# The entrypoint will:
#  - read PUID (user id) and PGID (group id) environment variables (defaults to 1000)
#  - create a group and user with those ids if they don't already exist
#  - ensure XDG_DATA_HOME and XDG_CONFIG_HOME exist and are owned by that uid:gid
#  - exec the container command as that user using gosu
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Expose port and set entrypoint & default command (keeps previous behavior)
EXPOSE ${FINGUARD_PORT}

# Run the entrypoint script via the shell to avoid exec format issues on some platforms
ENTRYPOINT ["sh", "/usr/local/bin/entrypoint.sh"]
CMD ["sh", "-c", "finguard-ui --port $FINGUARD_PORT"]
