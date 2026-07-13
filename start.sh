#!/bin/bash
# start.sh — starts Ghost Driver backend + frontend in the background
# Usage: bash start.sh

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "🔴  Stopping old processes on ports 4000 and 5173..."
lsof -ti:4000 | xargs kill -9 2>/dev/null
lsof -ti:5173 | xargs kill -9 2>/dev/null
sleep 1

echo "🚀  Starting backend on port 4000..."
cd "$ROOT/backend"
node src/server.js > "$ROOT/backend/server.log" 2>&1 &
BACKEND_PID=$!
echo "   Backend PID: $BACKEND_PID"

sleep 1

# Verify backend is up
if curl -sf http://localhost:4000/api/health > /dev/null 2>&1; then
  echo "   ✅ Backend is healthy"
else
  echo "   ⚠️  Backend may still be starting (check backend/server.log)"
fi

echo ""
echo "🚀  Starting frontend on port 5173..."
cd "$ROOT/frontend"
npm run dev > "$ROOT/frontend/dev.log" 2>&1 &
FRONTEND_PID=$!
echo "   Frontend PID: $FRONTEND_PID"

sleep 2

echo ""
echo "✅  Ghost Driver is running!"
echo "   Dashboard:       http://localhost:5173"
echo "   Vehicle Sim:     http://localhost:5173/vehicle-sim.html"
echo "   Backend Health:  http://localhost:4000/api/health"
echo ""
echo "   Backend log:  $ROOT/backend/server.log"
echo "   Frontend log: $ROOT/frontend/dev.log"
echo ""
echo "   To stop: lsof -ti:4000 | xargs kill && lsof -ti:5173 | xargs kill"

# Keep script running so PIDs stay alive
wait $BACKEND_PID
