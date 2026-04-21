# ---- Builder ----
FROM python:3.11-slim AS builder

WORKDIR /build

# setuptools-scm needs .git to detect version, but .git is in .dockerignore.
# Provide a fallback version so the wheel build succeeds without .git.
ENV SETUPTOOLS_SCM_PRETEND_VERSION=0.1.0

COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir build \
    && python -m build --wheel --outdir /build/dist

# ---- Runtime ----
FROM python:3.11-slim

# Security: run as non-root (OpenShift assigns arbitrary UID anyway)
RUN groupadd -r app && useradd -r -g app -d /opt/app-root -s /sbin/nologin app

WORKDIR /opt/app-root

# Install the wheel (pulls all runtime deps), then remove pip/setuptools to save ~40-50MB
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl \
    && rm -f /tmp/*.whl \
    && pip uninstall -y pip setuptools 2>/dev/null; true

# Copy static assets only. Config is mounted at runtime via ConfigMap (see Section 5.3).
COPY frontend/ /opt/app-root/frontend/

# Create writable data and config dirs
RUN mkdir -p /opt/app-root/data /opt/app-root/config && chown -R app:app /opt/app-root

USER app

# Environment defaults for container mode
ENV RELEASE_PLANNER_HOST=0.0.0.0 \
    RELEASE_PLANNER_PORT=9000 \
    RELEASE_PLANNER_FRONTEND_DIR=/opt/app-root/frontend \
    RELEASE_PLANNER_LOG_FORMAT=json \
    CONFIG_DIR=/opt/app-root/config \
    DATA_DIR=/opt/app-root/data

EXPOSE 9000

ENTRYPOINT ["python", "-m", "release_planner", "serve"]
