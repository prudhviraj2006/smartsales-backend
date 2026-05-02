@echo off
echo Starting Deployment for SmartSales AI to Google Cloud Run...

:: Get the active project ID
FOR /F "tokens=*" %%g IN ('gcloud config get-value project') do (SET PROJECT_ID=%%g)

if "%PROJECT_ID%"=="" (
    echo Error: Google Cloud Project ID not set. Please run: gcloud config set project YOUR_PROJECT_ID
    exit /b 1
)

set SERVICE_NAME=smartsales-api
set REGION=us-central1
set IMAGE_NAME=gcr.io/%PROJECT_ID%/%SERVICE_NAME%

echo Building Docker image using Cloud Build...
call gcloud builds submit --tag %IMAGE_NAME% .

echo Deploying to Cloud Run...
call gcloud run deploy %SERVICE_NAME% ^
    --image %IMAGE_NAME% ^
    --region %REGION% ^
    --platform managed ^
    --allow-unauthenticated ^
    --memory 4Gi ^
    --cpu 2 ^
    --port 8000 ^
    --set-env-vars DATABASE_URL="postgresql://postgres:Prudhvi%%402006@db.xpfrvisotzmvzchyfxvb.supabase.co:5432/postgres" ^
    --set-env-vars HOST="0.0.0.0"

echo Deployment Complete! Check your Google Cloud Console for the public URL.
