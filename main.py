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
async def generate_insight(payload: dict):
    query = payload.get("query", "")
    context = payload.get("context", {})

    try:
        rag_result = get_rag_response(query, context)

        # Format based on type
        if rag_result["type"] == "tasks":
            tasks = rag_result["data"]
            if not tasks:
                text = "No tasks found for this query."
            else:
                lines = [f"- {t['task_text']} (Due: {t.get('due_date', 'N/A')})"
                         for t in tasks]
                text = f"Here are the tasks I found:\n" + "\n".join(lines)

        elif rag_result["type"] == "kanban":
            tasks = rag_result["data"]
            if not tasks:
                text = "No Kanban tasks found."
            else:
                lines = []
                for t in tasks:
                    att_str = ""
                    if t.get("attachments"):
                        files = [a["file_name"] for a in t["attachments"]]
                        att_str = f" | Attachments: {', '.join(files)}"
                    lines.append(f"- {t['task_text']} (Status: {t['status']}, Priority: {t.get('priority','N/A')}){att_str}")
                text = "Kanban tasks:\n" + "\n".join(lines)

        elif rag_result["type"] == "messages":
            msgs = rag_result["data"]
            if not msgs:
                text = "No messages found."
            else:
                lines = [f"[{m['created_at']}] {m['message']}" for m in msgs]
                text = "Recent messages:\n" + "\n".join(lines)

        else:  # fallback to general
            text = rag_result["data"]

        return {"result": text, "raw": rag_result}

    except Exception as e:
        return {"error": str(e)}



@app.post("/interpret")
async def interpret(request: Request):
    print("📩 /interpret endpoint hit")
    try:
        body = await request.json()
        query = body.get("query", "")
        hints = body.get("hints", {})  # {"current_user_name": "...", "team_member_names": ["...","..."]}
        
        print(f"🔍 Query to interpret: {query}")
        print(f"💡 Hints provided: {hints}")
        
        result = interpret_query(query, hints)
        print(f"✅ Interpretation result: {result}")
        
        return {"result": result}
        
    except Exception as e:
        print("❌ Interpret failed:", str(e))
        import traceback
        traceback.print_exc()
        return {"result": {"action": "general_question", "target_user": {"type": "me"},
                           "time": {"natural": "", "start": None, "end": None},
                           "filters": {"priority": None, "status": None}}}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "message": "RAG engine is running"}

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Task Management AI Assistant API",
        "version": "2.0.0",
        "features": [
            "Task analysis and recommendations",
            "Message query support", 
            "Team communication insights",
            "Priority and deadline management"
        ],
        "endpoints": {
            "/generate-insight": "POST - Generate AI insights from tasks and messages",
            "/interpret": "POST - Interpret user queries and extract intent",
            "/health": "GET - Health check"
        }
    }

if __name__ == "__main__":
    # Handle command line execution (backward compatibility)
    body = json.load(sys.stdin)
    prompt = body.get("input", {}).get("prompt", "")
    context = body.get("input", {}).get("context", "")
    result = get_rag_response(prompt, context)
    print(json.dumps({"output": result}))