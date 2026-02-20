#!/bin/bash
# Start Wan2GP Proxy Server using Wan2GP's Python environment

WAN2GP_PATH="${WAN2GP_PATH:-/data/StabilityMatrix/Packages/Wan2GP}"
PROXY_PORT="${WAN2GP_PROXY_PORT:-7861}"
PROXY_HOST="${WAN2GP_PROXY_HOST:-127.0.0.1}"

echo "============================================"
echo "Starting Wan2GP Proxy Server"
echo "============================================"
echo "Wan2GP Path: $WAN2GP_PATH"
echo "Server: http://$PROXY_HOST:$PROXY_PORT"
echo ""

# Use Wan2GP's Python venv
PYTHON_BIN="$WAN2GP_PATH/venv/bin/python"

if [ ! -f "$PYTHON_BIN" ]; then
    echo "Error: Wan2GP Python not found at $PYTHON_BIN"
    exit 1
fi

# Install Flask in Wan2GP's venv if not present
echo "Checking Flask installation..."
if ! "$PYTHON_BIN" -c "import flask" 2>/dev/null; then
    echo "Installing Flask in Wan2GP environment..."
    "$PYTHON_BIN" -m pip install flask flask-cors -q
fi

# Export environment
export WAN2GP_PATH
export WAN2GP_PROXY_PORT=$PROXY_PORT
export WAN2GP_PROXY_HOST=$PROXY_HOST

# Change to proxy directory
cd "$(dirname "$0")"

# Start the proxy
echo "Starting proxy server..."
echo ""
"$PYTHON_BIN" wan2gp_proxy.py
