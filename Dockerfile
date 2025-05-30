FROM python:3.10-slim

RUN apt-get update && apt-get install -y curl git bash && apt-get clean

RUN curl -fsSL https://ollama.com/install.sh | sh

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r requirements.txt
