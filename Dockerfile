# Stage 1: Build TypeScript Frontend
FROM node:18-alpine AS frontend-build

WORKDIR /app/frontend

# Copy package files
COPY frontend/package*.json ./
RUN npm ci

# Copy frontend source
COPY frontend/ ./

# Build frontend
RUN npm run build

# Stage 2: Python Backend with FFmpeg
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including FFmpeg
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    ffmpeg \
    libsm6 \
    libxext6 \
    libfontconfig1 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy language model
RUN python -m spacy download en_core_web_trf

# Copy backend code
COPY app/ ./app/

# Copy built frontend from previous stage
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Copy FFmpeg binaries (as backup to system FFmpeg)
COPY ffmpeg-8.0-essentials_build/ ./ffmpeg-8.0-essentials_build/

# Create uploads directory
RUN mkdir -p uploads

# Set environment variables
ENV PYTHONPATH=/app
ENV FFMPEG_PATH=/usr/bin/ffmpeg

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/docs || exit 1

# Start command
ENV DEBUG=False
ENV LOG_LEVEL=INFO
ENV FFMPEG_PATH=/usr/bin/ffmpeg
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]