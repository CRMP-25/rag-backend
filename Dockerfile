# Base image
FROM python:3.10-slim

# System dependencies
RUN apt-get update && apt-get install -y \
    curl git bash libglib2.0-0 libsm6 libxext6 libxrender-dev \
    supervisor && apt-get clean

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# Set working directory
WORKDIR /app

# Copy all project files
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Pull LLaMA3 model
RUN ollama pull llama3

# Expose FastAPI port
EXPOSE 8080

# Supervisor log path and config
RUN mkdir -p /var/log/supervisor
COPY supervisord.conf /app/rag-backend/supervisord.conf

# Start both Ollama + FastAPI via supervisord
CMD ["supervisord", "-c", "/app/rag-backend/supervisord.conf"]
