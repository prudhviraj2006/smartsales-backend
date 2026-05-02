# Dockerfile for Hugging Face Spaces (Docker SDK)
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies for ML libraries
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev g++ build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application
COPY . .

# HF Spaces runs as user 1000 (non-root)
# Create writable directories for SQLite DB and file uploads
RUN mkdir -p /app/uploads /app/data \
    && chmod -R 777 /app/uploads /app/data /app

# Set environment for HF Spaces
ENV PORT=7860
ENV HOST=0.0.0.0
ENV DATABASE_URL=sqlite:///./data/smartsales.db
ENV UPLOAD_DIR=./uploads
ENV DEBUG=false

EXPOSE 7860

# Run with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
