# ✅ Base image
FROM python:3.10-slim

# ✅ Install system dependencies
RUN apt-get update && apt-get install -y \
    curl git bash libglib2.0-0 libsm6 libxext6 libxrender-dev \
    build-essential python3-pip supervisor sqlite3 && apt-get clean

# ✅ Set working directory
WORKDIR /app

# ✅ Copy your app files
COPY . /app

# ✅ Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# ✅ Make shell script executable
RUN chmod +x /start.sh

# ✅ Expose FastAPI port
EXPOSE 7860

# ✅ Default entry
CMD ["/start.sh"]
