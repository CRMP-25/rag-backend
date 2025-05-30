from rag_engine import get_rag_response

def handler(event):
    prompt = event.get("input", {}).get("prompt", "")
    print("🔍 Prompt received:", prompt)

    result = get_rag_response(prompt)
    return {
        "output": result
    }
