#!/bin/bash

# Function to check if docker daemon is running
check_docker() {
    if ! docker info >/dev/null 2>&1; then
        echo "❌ Docker daemon is not running. Please start Docker Desktop and try again."
        exit 1
    fi
}

# Function for local deployment
deploy_local() {
    echo "🚀 Starting local deployment..."
    
    # Check Docker daemon first
    check_docker
    
    # Run security scan (only if Docker is running)
    echo "Running security scan..."
    if ! docker scout quickview 2>/dev/null; then
        echo "⚠️ Security scan skipped - continuing with deployment"
    fi
    
    # One-line command to stop existing containers on port 8080, build, and run
    docker stop $(docker ps -q --filter "ancestor=my-image" --filter "status=running") 2>/dev/null
    docker build -t my-image .
    docker run -d -p 8080:8080 my-image
}

# Function for production deployment
deploy_prod() {
    echo "🚀 Starting production deployment to GCR..."
    
    # Check Docker daemon first
    check_docker
    
    # Run security scan (only if Docker is running)
    echo "Running security scan..."
    if ! docker scout quickview 2>/dev/null; then
        echo "⚠️ Security scan skipped - continuing with deployment"
    fi
    
    # Submit build to Cloud Build
    if ! gcloud builds submit --config cloudbuild.yaml; then
        echo "❌ Cloud Build submission failed"
        exit 1
    fi
    
    echo "✨ Production deployment completed!"
}

# Main script logic
if [ "$1" == "--prod" ]; then
    deploy_prod
else
    deploy_local
fi