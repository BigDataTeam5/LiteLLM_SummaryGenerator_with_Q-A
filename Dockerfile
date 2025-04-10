FROM python:3.9-slim

WORKDIR /app

# Install Redis and other dependencies
RUN apt-get update && apt-get install -y redis-server curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY . /app/
RUN rm -rf /app/frontend /app/.git

# Install Python dependencies
WORKDIR /app/api
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variables
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Create a simple startup script
RUN echo '#!/bin/bash\n\
redis-server --daemonize yes\n\
cd /app\n\
python -m api.main\n' > /app/start.sh

RUN chmod +x /app/start.sh

# Expose the port
EXPOSE 8080

# Start the application
CMD ["/app/start.sh"]