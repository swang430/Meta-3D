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
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini
COPY scripts/ ./scripts/

# Entrypoint: alembic upgrade head + bootstrap, then uvicorn.
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Persistent data dirs (bind-mounted via docker-compose).
RUN mkdir -p /app/calibration_data /app/certificates

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
