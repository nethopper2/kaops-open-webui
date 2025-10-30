#!/bin/bash
set -e

echo "🎨 Starting Frontend Development Server with Hot Reload"
echo "========================================================"
echo ""

# Function to install dependencies
install_deps() {
    echo "📦 Installing/updating npm dependencies..."
    npm install
    echo "✅ Dependencies installed successfully"
}

# Initial install check
if [ ! -d "node_modules" ] || [ "package.json" -nt "node_modules" ]; then
    install_deps
fi

# Start npm dev in background
npm run dev &
NPM_PID=$!

# Watch for package.json changes
echo "👀 Watching for package.json changes..."
while inotifywait -e modify,create,delete /app/package.json 2>/dev/null; do
    echo "📝 package.json changed, reinstalling dependencies..."
    install_deps
    echo "🔄 Restarting dev server..."
    kill $NPM_PID 2>/dev/null || true
    npm run dev &
    NPM_PID=$!
done &

# Wait for npm dev process
wait $NPM_PID

