from fastapi import FastAPI, Request
from rag_engine import get_rag_response
from fastapi.middleware.cors import CORSMiddleware

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
    body = await request.json()
    prompt = body.get("prompt", "")
    print("📩 Prompt received:\n", prompt)
    response = get_rag_response(prompt)
    return {"result": response}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=False)


