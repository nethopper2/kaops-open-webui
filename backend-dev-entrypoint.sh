#!/bin/bash
set -e

echo "⚙️  Starting Backend Development Server with Hot Reload"
echo "========================================================"
echo ""

# Function to install dependencies
install_deps() {
    echo "📦 Installing/updating Python dependencies..."
    pip install --no-cache-dir -r /app/backend/requirements.txt
    echo "✅ Dependencies installed successfully"
}

# Initial install check
if [ "/app/backend/requirements.txt" -nt "/tmp/.requirements_installed" ]; then
    install_deps
    touch /tmp/.requirements_installed
fi

# Start dev server in background
cd /app/backend && sh dev.sh &
DEV_PID=$!

# Watch for requirements.txt changes
echo "👀 Watching for requirements.txt changes..."
while inotifywait -e modify,create,delete /app/backend/requirements.txt 2>/dev/null; do
    echo "📝 requirements.txt changed, reinstalling dependencies..."
    install_deps
    touch /tmp/.requirements_installed
    echo "🔄 Restarting dev server..."
    kill $DEV_PID 2>/dev/null || true
    sleep 2
    cd /app/backend && sh dev.sh &
    DEV_PID=$!
done &

# Wait for dev server process
wait $DEV_PID

