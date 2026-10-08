#!/usr/bin/env bash
# ── CentrAlign AI Worker — Start Script ──────────────────
# Starts both the ERP simulator (port 8001) and the Agent API (port 8000)

set -e
cd "$(dirname "$0")"

export PATH="$HOME/Library/Python/3.9/bin:$PATH"

echo ""
echo "╔═══════════════════════════════════════════════════╗"
echo "║       CentrAlign AI Worker — Starting Up          ║"
echo "╚═══════════════════════════════════════════════════╝"
echo ""

# Check .env
if [ ! -f .env ]; then
  echo "⚠️  No .env file found. Creating from example..."
  cp .env.example .env
  echo "📝 Please edit .env and add your OPENAI_API_KEY, then re-run this script."
  echo ""
fi

source .env 2>/dev/null || true

if [ -z "$OPENAI_API_KEY" ] || [ "$OPENAI_API_KEY" = "sk-your-openai-key-here" ]; then
  echo "❌ OPENAI_API_KEY not set in .env file."
  echo "   Edit .env and add: OPENAI_API_KEY=sk-..."
  exit 1
fi

echo "✅ API key found."
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
