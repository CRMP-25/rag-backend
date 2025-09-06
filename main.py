from fastapi import FastAPI, Request
from rag_engine import get_rag_response, interpret_query
from fastapi.middleware.cors import CORSMiddleware
import sys, json



app = FastAPI()

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/generate-insight")
async def generate_insight(request: Request):
    print("📩 /generate-insight endpoint hit")
    try:
        body = await request.json()
        prompt = body.get("prompt", "")
        user_context = body.get("context", "")  # ✅ new line

        print("📩 Prompt received:\n", prompt)
        response = get_rag_response(prompt, user_context)  # ✅ updated call
        return {"result": response}
    except Exception as e:
        print("❌ Request failed:", str(e))
        return {"result": "Internal error"}
    

@app.post("/interpret")
async def interpret(request: Request):
    try:
        body = await request.json()
        query = body.get("query", "")
        hints = body.get("hints", {})  # {"current_user_name": "...", "team_member_names": ["...","..."]}
        result = interpret_query(query, hints)
        return {"result": result}
    except Exception as e:
        print("❌ Interpret failed:", str(e))
        return {"result": {"action": "general_question", "target_user": {"type": "me"},
                           "time": {"natural": "", "start": None, "end": None},
                           "filters": {"priority": None, "status": None}}}


if __name__ == "__main__":
    body = json.load(sys.stdin)
    prompt = body.get("input", {}).get("prompt", "")
    result = get_rag_response(prompt)
    print(json.dumps({"output": result}))
