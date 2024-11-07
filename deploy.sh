#!/bin/bash

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | xargs)
else
    echo "❌ .env file not found"
    exit 1
fi

# Function to check if Docker is running
check_docker() {
    if ! docker info >/dev/null 2>&1; then
        echo "❌ Docker is not running"
        exit 1
    fi
}

# Function to kill process on port 8080
kill_port_8080() {
    echo "Checking for processes on port 8080..."
    local pid=$(lsof -ti:8080)
    if [ ! -z "$pid" ]; then
        echo "Killing process on port 8080 (PID: $pid)..."
        kill -9 $pid
    fi
}

# Function to build frontend
build_frontend() {
    echo "🔨 Building frontend..."
    cd frontend || {
        echo "❌ Frontend directory not found"
        exit 1
    }
    
    echo "Installing frontend dependencies..."
    if ! npm install; then
        echo "❌ Failed to install frontend dependencies"
        cd ..
        exit 1
    fi
    
    echo "Building frontend application..."
    if ! npm run build; then
        echo "❌ Failed to build frontend"
        cd ..
        exit 1
    fi
    
    cd ..
    echo "✅ Frontend build completed successfully"
}

# Function to run backend tests with coverage
run_backend_tests() {
    echo "🧪 Setting up backend and running tests..."
    
    # Install backend dependencies
    echo "Installing backend dependencies..."
    if ! pip3 install -r requirements.txt; then
        echo "❌ Failed to install Python dependencies"
        exit 1
    fi
    
    echo "==============================================="
    echo "Running backend tests with coverage report..."
    echo "==============================================="
    cd backend || {
        echo "❌ Backend directory not found"
        exit 1
    }
    
    if ! python3 -m pytest --cov=app --cov-report term-missing tests/ -v; then
        echo "❌ Tests failed"
        cd ..
        exit 1
    fi
    
    cd ..
    echo "==============================================="
    echo "✅ Test coverage report complete"
    echo "==============================================="
}

# Function for local deployment
deploy_local() {
    echo "🚀 Starting local deployment..."
    check_docker
    
    # Run tests first
    run_backend_tests
    
    # Build frontend
    build_frontend
    
    # Kill any process on port 8080
    kill_port_8080
    
    # Check and remove existing edutrack container
    if docker ps -a --filter name=edutrack | grep -q edutrack; then
        echo "Stopping and removing existing edutrack container..."
        docker stop edutrack >/dev/null 2>&1
        docker rm edutrack >/dev/null 2>&1
    fi
    
    echo "Building Docker image..."
    if ! docker build --build-arg VERSION="${VERSION}" -t ${IMAGE_NAME}:${VERSION} .; then
        echo "❌ Local build failed"
        exit 1
    fi
    
    echo "Starting container..."
    if ! docker run -d -p 8080:8080 --name edutrack ${IMAGE_NAME}:${VERSION}; then
        echo "❌ Container startup failed"
        exit 1
    fi
    
    echo "✨ Local deployment completed!"
    echo "🌐 Application is now available at: http://localhost:8080"
}

# Function for production deployment
deploy_prod() {
    echo "🚀 Starting production deployment to GCR..."
    check_docker
    
    # Run tests first
    run_backend_tests
    
    # Build frontend
    build_frontend
    
    # Build image locally
    IMAGE_TAG="${GCR_HOSTNAME}/${PROJECT_ID}/${IMAGE_NAME}:${VERSION}"
    echo "Building image: ${IMAGE_TAG}"
    if ! docker build --build-arg VERSION="${VERSION}" -t ${IMAGE_TAG} .; then
        echo "❌ Local build failed"
        exit 1
    fi
    
    # Run security scan
    echo "Running security scan..."
    docker scout quickview 2>/dev/null || echo "⚠️ Security scan skipped"
    
    # Push to GCR
    echo "Pushing to GCR..."
    if ! docker push ${IMAGE_TAG}; then
        echo "❌ Push to GCR failed"
        exit 1
    fi
    
    # Deploy to Cloud Run
    echo "Deploying to Cloud Run..."
    if ! gcloud run deploy ${IMAGE_NAME} \
        --image ${IMAGE_TAG} \
        --platform managed \
        --region ${REGION} \
        --project ${PROJECT_ID} \
        --allow-unauthenticated; then
        echo "❌ Cloud Run deployment failed"
        exit 1
    fi
    
    echo "✨ Production deployment completed!"
    echo "🌐 Application metrics and details available at:"
    echo "https://console.cloud.google.com/run/detail/us-central1/edutrack/metrics?project=portfolio-383615"
}

# Main script logic
if [ "$1" == "--prod" ]; then
    deploy_prod
else
    deploy_local
fi
