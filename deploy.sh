#!/bin/bash

# Configuration
PROJECT_ID="portfolio-383615"
IMAGE_NAME="edutrack"
REGION="us-central1"
GCR_HOSTNAME="gcr.io"

# Function to check if Docker is running
check_docker() {
    if ! docker info >/dev/null 2>&1; then
        echo "❌ Docker is not running"
        exit 1
    fi
}

# Function for local deployment
deploy_local() {
    echo "🚀 Starting local deployment..."
    check_docker
    docker stop $(docker ps -q --filter "ancestor=my-image" --filter "status=running") 2>/dev/null
    docker build -t my-image .
    docker run -d -p 8080:8080 my-image
}

# Function for production deployment
deploy_prod() {
    echo "🚀 Starting production deployment to GCR..."
    check_docker
    
    # Build image locally
    IMAGE_TAG="${GCR_HOSTNAME}/${PROJECT_ID}/${IMAGE_NAME}:latest"
    echo "Building image: ${IMAGE_TAG}"
    if ! docker build -t ${IMAGE_TAG} .; then
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
    }
    
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
}

# Main script logic
if [ "$1" == "--prod" ]; then
    deploy_prod
else
    deploy_local
fi