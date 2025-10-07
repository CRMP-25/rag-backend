#!/bin/bash

echo "🚀 Bootstrapping app..."

# ✅ Install all dependencies from requirements.txt (safe to rerun)
/usr/local/bin/python3.10 -m pip install --no-cache-dir -r requirements.txt

# --- Supabase environment (backend-only) ---
export SUPABASE_URL="https://ufkpylvvpbtqnlwhqnrq.supabase.co"
# Use service role on the BACKEND only (never in browser code)
export SUPABASE_SERVICE_ROLE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVma3B5bHZ2cGJ0cW5sd2hxbnJxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDQxOTA0MzcsImV4cCI6MjA1OTc2NjQzN30.ZAcrgZFr1o_roBEfYao6aOOq_HSkBPiHfoYRjVrGkZ8"

# (Optional) If anything expects it:
# export SUPABASE_ANON_KEY="YOUR_ANON_KEY"

# Quick sanity check (won't print secrets)
python - <<'PY'
import os
print("SUPABASE_URL set:", bool(os.getenv("SUPABASE_URL")))
print("SERVICE_ROLE set:", bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY")))
PY


# ✅ Pull model if not already present
if ! ollama list | grep -q llama3; then
    echo "🔄 Pulling LLaMA3 model..."
    ollama pull llama3
fi

# ✅ Pull embedding model if not already present
if ! ollama list | grep -q all-minilm; then
    echo "🔄 Pulling all-minilm embeddings..."
    ollama pull all-minilm
fi

# ✅ Build vector DB if missing
if [ ! -d "vector_store" ] || [ -z "$(ls -A vector_store)" ]; then
    echo "🧠 No vector DB found. Creating..."
    /usr/local/bin/python3.10 load_documents.py
else
    echo "✅ Vector DB already exists."
fi

# ✅ Start FastAPI using Python 3.10's uvicorn
echo "🚀 Launching FastAPI..."
nohup /usr/local/bin/python3.10 -m uvicorn main:app --host 0.0.0.0 --port 7860 &


# #!/bin/bash

# echo "🚀 Bootstrapping app..."

# # ✅ Ensure dependencies are installed (safe to rerun)
# # This uses the pip tied to Python 3.10
# /usr/local/bin/python3.10 -m pip install --no-cache-dir langchain-community langchain-core chromadb docx2txt langchain-ollama uvicorn

# # ✅ Pull model if not already present
# if ! ollama list | grep -q llama3; then
#     echo "🔄 Pulling LLaMA3 model..."
#     ollama pull llama3
# fi

# # ✅ Build vector DB if missing
# if [ ! -d "vector_store" ] || [ -z "$(ls -A vector_store)" ]; then
#     echo "🧠 No vector DB found. Creating..."
#     /usr/local/bin/python3.10 load_documents.py
# else
#     echo "✅ Vector DB already exists."
# fi

# # ✅ Start FastAPI using Python 3.10's uvicorn
# echo "🚀 Launching FastAPI..."
# nohup /usr/local/bin/python3.10 -m uvicorn main:app --host 0.0.0.0 --port 7860 &
