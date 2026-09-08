#!/bin/bash

# Gujarati PDF Processor - Quick Start Script

set -e

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "🚀 Starting Gujarati PDF Processor..."
echo ""

# Create log directory
mkdir -p logs

# Start Redis
echo "1️⃣  Starting Redis..."
if ! pgrep redis-server > /dev/null; then
    redis-server --daemonize yes --logfile "$PROJECT_DIR/logs/redis.log"
    echo "   Redis started"
else
    echo "   Redis already running"
fi
sleep 1

# Start Celery Worker
echo "2️⃣  Starting Celery Worker..."
# Use Python from venv if available, otherwise system python
if [ -d ".venv" ]; then
    PYTHON_CMD=".venv/bin/python"
    CELERY_CMD=".venv/bin/celery"
else
    PYTHON_CMD="python3"
    CELERY_CMD="celery"
fi

nohup $CELERY_CMD -A worker worker --loglevel=info > "$PROJECT_DIR/logs/celery.log" 2>&1 &
CELERY_PID=$!
echo "   Celery started (PID: $CELERY_PID)"
sleep 2

# Start Backend API
echo "3️⃣  Starting Backend API..."
nohup $PYTHON_CMD -m uvicorn app:app --host 0.0.0.0 --port 8000 > "$PROJECT_DIR/logs/backend.log" 2>&1 &
BACKEND_PID=$!
echo "   Backend started (PID: $BACKEND_PID)"
sleep 2

# Start Frontend
echo "4️⃣  Starting Frontend..."
cd "$PROJECT_DIR/frontend"
nohup npm run dev > "$PROJECT_DIR/logs/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "   Frontend started (PID: $FRONTEND_PID)"
sleep 3

echo ""
echo "✅ All services started!"
echo ""
echo "📱 Open App: http://localhost:5173"
echo "📊 Backend:  http://localhost:8000/docs"
echo ""
echo "📝 Logs are in: $PROJECT_DIR/logs/"
echo "   - tail -f logs/celery.log"
echo "   - tail -f logs/backend.log"
echo ""
echo "To stop: ./stop_app.sh"
echo ""

# Save PIDs
echo "$BACKEND_PID" > "$PROJECT_DIR/logs/backend.pid"
echo "$FRONTEND_PID" > "$PROJECT_DIR/logs/frontend.pid"
