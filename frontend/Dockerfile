# Use an official Python runtime as a parent image
FROM --platform=linux/amd64 python:3.9-slim
# Set the working directory inside the container
WORKDIR /app

COPY frontend/ /app/

# Install required Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Expose Streamlit's default port
EXPOSE 8501

# Run the Streamlit app
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
