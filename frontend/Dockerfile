# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Copy only the frontend (app.py and requirements.txt)
COPY frontend/app.py /app/app.py
COPY frontend/requirements.txt /app/requirements.txt

# Install required Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Expose Streamlit's default port
EXPOSE 8080

# Run the Streamlit app
CMD ["streamlit", "run", "app.py", "--server.port=8080", "--server.address=0.0.0.0"]
