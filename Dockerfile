# ✅ Base image
FROM python:3.10-slim

# ✅ System dependencies (no need for Ollama or supervisor reinstallation)
RUN apt-get update && apt-get install -y \
    git bash libglib2.0-0 libsm6 libxext6 libxrender-dev \
    python3-pip supervisor && apt-get clean

# ✅ Set working directory
WORKDIR /app

# ✅ Copy all project files
COPY . /app

# ✅ Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# ✅ Expose FastAPI port
EXPOSE 7860

# ✅ Supervisor log path and config
RUN mkdir -p /var/log/supervisor
COPY supervisord.conf /app/supervisord.conf

# ✅ Copy start.sh and make it executable
COPY start.sh /start.sh
RUN chmod +x /start.sh

# ✅ Run the startup script
CMD ["/start.sh"]



# # ✅ Base image
# FROM python:3.10-slim

# # ✅ System dependencies (no need for Ollama or supervisor reinstallation)
# RUN apt-get update && apt-get install -y \
#     git bash libglib2.0-0 libsm6 libxext6 libxrender-dev \
#     python3-pip supervisor && apt-get clean

# # ✅ Set working directory
# WORKDIR /app

# # ✅ Copy all project files
# COPY . /app

# # ✅ Install Python dependencies
# RUN pip install --no-cache-dir -r requirements.txt

# # ✅ Expose FastAPI port
# EXPOSE 7860

# # ✅ Supervisor log path and config
# RUN mkdir -p /var/log/supervisor
# COPY supervisord.conf /app/supervisord.conf

# # ✅ Start only FastAPI using supervisord (ollama is already running outside container)
# CMD ["supervisord", "-c", "/app/supervisord.conf"]

# # ✅ Copy start.sh
# COPY start.sh /start.sh
# RUN chmod +x /start.sh

# # ✅ Run the script
# CMD ["/start.sh"]



# # Base image
# FROM python:3.10-slim

# # System dependencies
# RUN apt-get update && apt-get install -y \
#     curl git bash libglib2.0-0 libsm6 libxext6 libxrender-dev \
#     python3-pip supervisor && apt-get clean

# # Install Ollama
# RUN curl -fsSL https://ollama.com/install.sh | sh

# # Set working directory
# WORKDIR /app

# # Copy all project files
# COPY . /app

# # Install Python dependencies
# RUN pip install --no-cache-dir -r requirements.txt

# # Expose FastAPI port
# EXPOSE 7860

# # Supervisor log path and config
# RUN mkdir -p /var/log/supervisor
# COPY supervisord.conf /app/supervisord.conf

# # Start both Ollama + FastAPI via supervisord
# CMD ["supervisord", "-c", "/app/supervisord.conf"]
