#!/bin/bash

# Kill any existing processes
echo "Killing existing processes..."
pkill -f "node"
pkill -f "uvicorn"

# Navigate to frontend directory and install dependencies
echo "Setting up frontend..."
cd frontend
npm install

# Build frontend
echo "Building frontend..."
npm run build

# Start frontend in background
echo "Starting frontend..."
npm start &

# Wait for frontend to start
sleep 5

# Navigate to backend directory
cd ../backend

# Install Python dependencies
echo "Installing backend dependencies..."
pip install -r requirements.txt

# Start backend
echo "Starting backend..."
uvicorn main:app --reload --port 8000
