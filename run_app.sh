#!/bin/bash
set -euo pipefail

# -- Cleanup on exit (kill background jobs) --
cleanup() {
  echo
  echo "Stopping background processes..."
  if [[ -n "${BACKEND_PID-}" ]]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  exit 0
}
trap cleanup INT TERM EXIT

echo "Initializing conda for non-interactive shell..."

# Try common conda init methods
if [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
  source "$HOME/anaconda3/etc/profile.d/conda.sh"
elif [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
  source "$HOME/miniconda3/etc/profile.d/conda.sh"
elif command -v conda >/dev/null 2>&1; then
  # This will set up conda in non-interactive shells
  eval "$(conda shell.bash hook)"
else
  echo "Error: conda not found. Install conda or update the script to point to your conda installation."
  exit 1
fi

# Activate environment
echo "Activating conda environment 'ai-env'..."
conda deactivate || true
conda activate ai-env

# Start backend in background
echo "Starting backend..."
(
  cd backend || { echo "Error: backend/app not found. Check path."; exit 1; }
  # run uvicorn (runs until killed)
  uvicorn api_app:app --host 0.0.0.0 --port 6514
) &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# Give backend a short moment to start (optional)
sleep 0.5

# Start frontend in foreground (so logs are visible)
echo "Starting frontend..."
cd frontend || { echo "Error: frontend folder not found. Check path."; exit 1; }
npm run dev -- --port 6513

# When frontend exits, cleanup trap will run and stop backend
