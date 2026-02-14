# Token Intelligence Service Dockerfile

FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements_token.txt requirements_common.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements_common.txt && \
    pip install --no-cache-dir -r requirements_token.txt

# Copy common_ai library
COPY common_ai/ /app/common_ai/

# Copy token intelligence service
COPY token_intel_service/ /app/token_intel_service/

# Set working directory to service
WORKDIR /app/token_intel_service

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:80/health')"

# Run application
CMD ["uvicorn", "token_intel_app:app", "--host", "0.0.0.0", "--port", "80"]
