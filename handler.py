from rag_engine import get_rag_response
import subprocess
import time

# Optional: start Ollama here
def start_ollama():
    print("🚀 Starting Ollama...")
    subprocess.Popen(["ollama", "serve"])
    time.sleep(6)

start_ollama()

def handler(event):
    prompt = event.get("input", {}).get("prompt", "")
    print("📥 Prompt received:", prompt)
    result = get_rag_response(prompt)
    return {
        "output": result
    }
