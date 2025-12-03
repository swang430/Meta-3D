#!/bin/bash
# Initialize database with instruments and probes

echo "🚀 Initializing Database..."

cd api-service

if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found in api-service/.venv"
    exit 1
fi

echo "📦 Initializing Instruments..."
.venv/bin/python scripts/init_instruments.py

echo "📡 Initializing Probes..."
.venv/bin/python scripts/init_probes.py

echo "✅ Database initialization complete!"
