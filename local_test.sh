#!/bin/bash

# Function to cleanup background processes
cleanup() {
    echo "Cleaning up processes..."
    lsof -ti:3000 | xargs kill -9 2>/dev/null || true
    lsof -ti:8080 | xargs kill -9 2>/dev/null || true
    pkill -f "uvicorn" 2>/dev/null || true
    pkill -f "node.*react-scripts" 2>/dev/null || true
    sleep 2  # Give processes time to clean up
}

# Function to check if a port is available
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null ; then
        echo "Port $port is already in use"
        return 1
    fi
    return 0
}

# Trap cleanup function
trap cleanup EXIT INT TERM

# Kill any existing processes on required ports
echo "Cleaning up existing processes..."
cleanup

# Check if required ports are available
if ! check_port 3000 || ! check_port 8080; then
    echo "Required ports are not available. Please check if other processes are using ports 3000 or 8080"
    exit 1
fi

# Step 1: Build the React app
echo "Building frontend..."
cd frontend || exit 1
npm install || {
    echo "Failed to install frontend dependencies"
    exit 1
}
npm run build || {
    echo "Failed to build frontend"
    exit 1
}
cd .. || exit 1

# Step 2: Set up and test backend
echo "Setting up backend..."
pip3 install -r requirements.txt || {
    echo "Failed to install Python dependencies"
    exit 1
}

# Install backend package in development mode
echo "Installing backend package in development mode..."
cd backend || exit 1
pip3 install -e . || {
    echo "Failed to install backend package"
    exit 1
}
cd .. || exit 1

echo "==============================================="
echo "Running backend tests with coverage report..."
echo "==============================================="
cd backend || exit 1
python3 -m pytest --cov=app --cov-report term-missing tests/ -v || {
    echo "Tests failed"
    exit 1
}
cd .. || exit 1
echo "==============================================="
echo "Test coverage report complete"
echo "==============================================="

echo "Starting backend server..."
python3 server.py &
backend_pid=$!

# Wait for backend to start
echo "Waiting for backend to start..."
sleep 5

# Check if backend is still running
if ! kill -0 $backend_pid 2>/dev/null; then
    echo "Backend failed to start"
    cleanup
    exit 1
fi

# Step 3: Start the frontend
echo "Starting frontend development server..."
cd frontend || exit 1
PORT=3000 npm start || {
    echo "Failed to start frontend"
    cleanup
    exit 1
}

# Keep running
wait
