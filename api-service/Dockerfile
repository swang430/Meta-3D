FROM python:3.11-slim

WORKDIR /app

# System deps. postgresql-client is kept around because some operations
# (manual psql poking, future health-check scripts) want it on PATH.
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code + everything the entrypoint needs to run alembic
# migrations and the bootstrap CLI on container start.
#
# These COPYs are intentionally broad. The build context is filtered by
# .dockerignore — notably ``scripts/dev-fixtures/`` is excluded so the
# topology-template registry stays empty in commercial images (see
# app/api/switch_topology.py:_TEMPLATES_DIR). Edit .dockerignore, not the
# COPYs, when you need to add a new exclusion.
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini
COPY scripts/ ./scripts/

# Entrypoint: alembic upgrade head + bootstrap, then uvicorn.
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Persistent data dirs. ⚠️ 部署时**必须**挂持久卷 —— compose 里那个 api 服务
# (曾经提供这两条 bind mount) 已于 2026-08-05 整体拆除。不挂就落在容器可写层,
# 换镜像/重建容器时校准数据与证书全丢。挂法见 README 的 "Docker Deployment"。
RUN mkdir -p /app/calibration_data /app/certificates

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
