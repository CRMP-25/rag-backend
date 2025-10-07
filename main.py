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
        query = body.get("query") or body.get("prompt") or ""
        user_context = body.get("context", "")

        print("📩 Query received:\n", query)
        print(f"📊 Context length: {len(user_context)} characters")

       

        # Log context preview for debugging
        if user_context:
            context_preview = user_context[:200] + "..." if len(user_context) > 200 else user_context
            print(f"📄 Context preview: {context_preview}")
        
        response = get_rag_response(query, user_context)
        print(f"✅ Response generated: {len(response)} characters")
        
        return {"result": response}
        
    except Exception as e:
        print("❌ Request failed:", str(e))
        import traceback
        traceback.print_exc()
        return {"result": "Internal error occurred while processing your request."}

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