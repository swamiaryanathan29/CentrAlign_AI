#!/usr/bin/env bash
# ── CentrAlign AI Worker — Start Script ──────────────────
# Starts the Agent API and ERP simulator (or cloud deployment on $PORT)

set -e
cd "$(dirname "$0")"

# 1. Cloud environment detection (Render, Railway, Fly, Heroku)
if [ -n "$PORT" ]; then
  echo "🌐 Cloud environment detected (PORT=$PORT). Starting unified server..."
  exec python3 -m uvicorn backend.main:app --host 0.0.0.0 --port "$PORT"
fi

# 2. Local environment
export PATH="$HOME/Library/Python/3.9/bin:$PATH"

echo ""
echo "╔═══════════════════════════════════════════════════╗"
echo "║       CentrAlign AI Worker — Starting Up          ║"
echo "╚═══════════════════════════════════════════════════╝"
echo ""

# Check .env
if [ ! -f .env ]; then
  echo "ℹ️  No .env file found. Creating from .env.example..."
  cp .env.example .env
fi

source .env 2>/dev/null || true

if [ -n "$OPENAI_API_KEY" ] && [ "$OPENAI_API_KEY" != "sk-your-openai-key-here" ]; then
  echo "✅ OpenAI API Key detected — LangGraph GPT-4o enabled."
else
  echo "ℹ️  No OpenAI API Key set — running with Autonomous Local Engine."
fi
echo ""

# Start ERP simulator in background
echo "🏦 Starting ERP Simulator on http://localhost:8001..."
python3 -m uvicorn backend.erp_sim.erp_app:erp_app --host 0.0.0.0 --port 8001 --log-level warning &
ERP_PID=$!

sleep 1

# Start main agent API
echo "🤖 Starting Agent API on http://localhost:8000..."
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Frontend:    http://localhost:8000"
echo "  Agent API:   http://localhost:8000/api"
echo "  ERP System:  http://localhost:8001"
echo "  API Docs:    http://localhost:8000/docs"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cleanup() {
  echo ""
  echo "Shutting down..."
  kill $ERP_PID 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
