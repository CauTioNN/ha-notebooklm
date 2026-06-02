# Slim image: only Chromium (no Firefox/WebKit), built on python:slim.
# BUILD_FROM is supplied by Home Assistant from build.yaml (and by the CI builder).
ARG BUILD_FROM=python:3.12-slim-bookworm
FROM ${BUILD_FROM}

ENV DEBIAN_FRONTEND=noninteractive \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Virtual display + VNC + noVNC web client so the Google login window can be
# driven from inside Home Assistant through the add-on's ingress panel.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        xvfb \
        x11vnc \
        novnc \
        websockify \
        procps \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "notebooklm-py[browser]==0.6.0" "aiohttp>=3.9"

# Install ONLY Chromium plus the exact OS libraries it needs.
RUN playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app.py run.sh /app/
RUN chmod +x /app/run.sh

EXPOSE 8099
CMD ["/app/run.sh"]
