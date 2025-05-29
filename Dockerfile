# Start from official Python image 
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy all backend code
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the correct FastAPI port (RunPod expects 8080)
EXPOSE 8080

# Run the FastAPI server on port 8080
CMD bash -c "uvicorn main:app --host 0.0.0.0 --port 8080"

