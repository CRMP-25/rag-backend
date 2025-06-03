#!/bin/bash

echo "🚀 Bootstrapping app..."

# (Optional) Pull model only if not already present
if ! ollama list | grep -q llama3; then
    echo "🔄 Pulling LLaMA3 model..."
    ollama pull llama3
fi

# (Optional) Build vector store if missing
if [ ! -d "vector_store" ] || [ -z "$(ls -A vector_store)" ]; then
    echo "🧠 No vector DB found. Creating..."
    python3 load_documents.py
else
    echo "✅ Vector DB already exists."
fi

# ✅ Start FastAPI
echo "🚀 Launching FastAPI..."
nohup uvicorn main:app --host 0.0.0.0 --port 7860 &

