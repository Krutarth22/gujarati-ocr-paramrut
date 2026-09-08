#!/bin/bash

# Gujarati PDF Processor - Stop Script

set -e

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "🛑 Stopping Gujarati PDF Processor..."
echo ""

# Stop Frontend
if [ -f "logs/frontend.pid" ]; then
    FRONTEND_PID=$(cat logs/frontend.pid)
    echo "Stopping Frontend (PID: $FRONTEND_PID)..."
    kill $FRONTEND_PID 2>/dev/null || echo "Frontend already stopped"
    rm logs/frontend.pid
fi

# Stop Backend
if [ -f "logs/backend.pid" ]; then
    BACKEND_PID=$(cat logs/backend.pid)
    echo "Stopping Backend (PID: $BACKEND_PID)..."
    kill $BACKEND_PID 2>/dev/null || echo "Backend already stopped"
    rm logs/backend.pid
fi

# Stop Celery
echo "Stopping Celery Worker..."
pkill -f "celery -A worker" || echo "Celery not running"

# Stop Redis
echo "Stopping Redis..."
redis-cli shutdown 2>/dev/null || echo "Redis already stopped"

echo ""
echo "✅ All services stopped!"
