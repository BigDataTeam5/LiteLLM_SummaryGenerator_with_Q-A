# Use an official Python image
FROM --platform=linux/amd64 python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies including Redis
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    redis-server \
    build-essential \
    wget \
    supervisor \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy only the necessary files & folders (EXCLUDING frontend/)
COPY . /app/
RUN rm -rf /app/frontend 
RUN rm -rf /app/.git

# COPY .env /app/.env
# RUN chmod 600 /app/.env


# Upgrade pip, setuptools, and wheel
RUN pip install --upgrade pip setuptools wheel

# Install dependencies
WORKDIR /app/api
RUN pip install --no-cache-dir --upgrade --prefer-binary -r requirements.txt

# Configure supervisor to run both Redis, FastAPI, and the worker
RUN mkdir -p /var/log/supervisor
COPY api/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Set environment variables
ENV PORT=8080
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1 
ENV WORKERS=2
ENV TIMEOUT=180

HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Command to start supervisor which will manage all processes
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
