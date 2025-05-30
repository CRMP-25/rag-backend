import sys
import json
import subprocess
import time
from rag_engine import get_rag_response

def start_ollama():
    print("🚀 Starting Ollama in background...")
    subprocess.Popen(["ollama", "serve"])
    time.sleep(5)  # Give Ollama time to boot

if __name__ == "__main__":
    try:
        start_ollama()  # ✅ Ensure Ollama is running before anything else

        body = json.load(sys.stdin)
        prompt = body.get("input", {}).get("prompt", "")
        print("🔍 Prompt received:", prompt)

        result = get_rag_response(prompt)
        print(json.dumps({"output": result}))

    except Exception as e:
        print(json.dumps({"output": f"❌ Internal error: {str(e)}"}))


# from fastapi import FastAPI, Request
# from rag_engine import get_rag_response
# from fastapi.middleware.cors import CORSMiddleware
# import sys, json

# app = FastAPI()

# # Enable CORS for frontend
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# @app.post("/generate-insight")
# async def generate_insight(request: Request):
#     print("📩 /generate-insight endpoint hit")
#     try:
#         body = await request.json()
#         prompt = body.get("prompt", "")
#         print("📩 Prompt received:\n", prompt)
#         response = get_rag_response(prompt)
#         return {"result": response}
#     except Exception as e:
#         print("❌ Request failed:", str(e))
#         return {"result": "Internal error"}



# if __name__ == "__main__":
#     body = json.load(sys.stdin)
#     prompt = body.get("input", {}).get("prompt", "")
#     result = get_rag_response(prompt)
#     print(json.dumps({"output": result}))





