#!/bin/bash

# SmartSales AI - Google Cloud Run Deployment Script
# 
# Prerequisites:
# 1. Install Google Cloud SDK (gcloud CLI)
# 2. Run: `gcloud auth login`
# 3. Create a GCP Project and run: `gcloud config set project YOUR_PROJECT_ID`
# 4. Enable Cloud Run & Artifact Registry APIs: 
#    `gcloud services enable run.googleapis.com artifactregistry.googleapis.com`

PROJECT_ID=$(gcloud config get-value project)
SERVICE_NAME="smartsales-api"
REGION="us-central1"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

if [ -z "$PROJECT_ID" ]; then
    echo "❌ Error: Google Cloud Project ID not set."
    echo "Please set it using: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

echo "🚀 Starting Deployment for SmartSales AI to Google Cloud Run..."
echo "📦 Project ID: $PROJECT_ID"

# 1. Build the Docker Image
echo "🔨 Building Docker image using Cloud Build..."
gcloud builds submit --tag ${IMAGE_NAME} .

# 2. Deploy to Cloud Run
echo "☁️ Deploying to Cloud Run..."
gcloud run deploy ${SERVICE_NAME} \
    --image ${IMAGE_NAME} \
    --region ${REGION} \
    --platform managed \
    --allow-unauthenticated \
    --memory 4Gi \
    --cpu 2 \
    --port 8000 \
    --set-env-vars DATABASE_URL="postgresql://postgres:Prudhvi%402006@db.xpfrvisotzmvzchyfxvb.supabase.co:5432/postgres" \
    --set-env-vars HOST="0.0.0.0"

echo "✅ Deployment Complete! Check your Google Cloud Console for the public URL."
