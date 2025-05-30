import sys
import json
import subprocess
import time
from rag_engine import get_rag_response

def start_ollama():
    print("🚀 Starting Ollama in background...")
    subprocess.Popen(["ollama", "serve"])
    time.sleep(5)

if __name__ == "__main__":
    try:
        start_ollama()

        # Read input safely
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            raise ValueError("⛔ No input received on stdin.")

        print("📥 Raw Input Received:", raw_input)
        body = json.loads(raw_input)

        prompt = body.get("input", {}).get("prompt", "")
        print("🔍 Prompt:", prompt)

        result = get_rag_response(prompt)
        print(json.dumps({"output": result}))

    except Exception as e:
        print(json.dumps({"output": f"❌ Internal error: {str(e)}"}))
