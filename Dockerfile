FROM python:3.11-slim

# Install system dependencies for Pillow and OpenCV
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 photolookup

# Set working directory
WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY server/ ./server/

# Create data directory with proper permissions
RUN mkdir -p /data && chown photolookup:photolookup /data

# Switch to non-root user
USER photolookup

# Set data directory environment variable
ENV PHOTOLOOKUP_DATA_DIR=/data

# Expose port
EXPOSE 14322

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:14322/api/health')" || exit 1

# Run server
CMD ["sh", "-c", "uvicorn server.main:app --host 0.0.0.0 --port ${PORT:-14322}"]
