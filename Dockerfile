# ---------------------------
# ✅ Base image with Python
# ---------------------------
FROM python:3.10-slim

# ---------------------------
# ✅ Install required tools
# ---------------------------
RUN apt-get update && apt-get install -y \
    curl git bash libglib2.0-0 libsm6 libxext6 libxrender-dev \
    && apt-get clean

# ---------------------------
# ✅ Install Ollama (LLaMA3)
# ---------------------------
RUN curl -fsSL https://ollama.com/install.sh | sh

# ---------------------------
# ✅ Create working directory
# ---------------------------
WORKDIR /app

# ---------------------------
# ✅ Copy backend code
# ---------------------------
COPY . /app

# ---------------------------
# ✅ Install Python dependencies
# ---------------------------
RUN pip install --no-cache-dir -r requirements.txt

# ---------------------------
# ✅ Pull the LLaMA3 model before launch
# ---------------------------
RUN ollama pull llama3

# ---------------------------
# ✅ Expose the expected FastAPI port
# ---------------------------
EXPOSE 8080

# ---------------------------
# ✅ Start Ollama + FastAPI together
# ---------------------------
CMD bash -c "\
    ollama serve & \
    sleep 5 && \
    uvicorn main:app --host 0.0.0.0 --port 8080"
