#!/bin/bash

echo "🚀 Bootstrapping app..."

# ✅ Ensure dependencies are installed (safe to rerun)
pip3 install --no-cache-dir langchain-community langchain-core chromadb docx2txt langchain-ollama uvicorn

# ✅ Pull model if not already present
if ! ollama list | grep -q llama3; then
    echo "🔄 Pulling LLaMA3 model..."
    ollama pull llama3
fi

# ✅ Build vector DB if missing
if [ ! -d "vector_store" ] || [ -z "$(ls -A vector_store)" ]; then
    echo "🧠 No vector DB found. Creating..."
    python3 load_documents.py
else
    echo "✅ Vector DB already exists."
fi

# ✅ Start FastAPI
echo "🚀 Launching FastAPI..."
exec uvicorn main:app --host 0.0.0.0 --port 7860
