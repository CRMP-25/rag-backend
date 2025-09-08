from typing import Dict, Any
import os, time, requests, json
from langchain.prompts import PromptTemplate
from langchain_ollama import OllamaLLM

def wait_for_ollama(timeout=30):
    print("⏳ Waiting for Ollama to be ready...")
    for _ in range(timeout):
        try:
            r = requests.get("http://localhost:11434")
            if r.status_code == 200:
                print("✅ Ollama is ready.")
                return True
        except Exception:
            pass
        time.sleep(1)
    print("❌ Ollama did not start in time.")
    return False

def interpret_query(query: str, hints: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Convert a natural-language question into structured intent.
    """
    hints = hints or {}
    names = hints.get("team_member_names", [])
    me = hints.get("current_user_name", "")

    system = """You are a precise intent parser for a project assistant. 
Output STRICT JSON only. No extra text.

FIELDS:
- action: one of {"query_tasks","query_kanban","query_files","query_profile","query_messages","general_question"}.
  Choose the best fit from the user question (e.g., "kanban", "board" -> query_kanban;
  "files","attachments","docs" -> query_files; "profile","email","phone" -> query_profile;
  "messages","chats","team chat","conversation","recent messages" -> query_messages).
  For questions about "what to do today", "what tasks to complete", "priorities" -> query_tasks.

- target_user: {"type":"me"} OR {"type":"name","value":"<full name>"}.
  Prefer {"type":"me"} for "I/my/me". If multiple people/team -> {"type":"name","value":"TEAM"}.
  If unsure of a name, pick the closest match from team_member_names.

- time: { "natural": "<as said>", "start": null|YYYY-MM-DD, "end": null|YYYY-MM-DD }.
  Do NOT fabricate ISO dates unless clearly stated.

- filters:
  - priority: Normalize to "High","Medium","Low".
  - status: Normalize to "Open","In Progress","Done","Completed","Archived".
  - due_bucket: one of overdue/today/tomorrow/this_week/next_week/this_month.
  - board: "tasks"|"kanban"|"calendar"|"files"|"messages".
  - limit: integer 1..50 if user asks for "top N".
  - sort: "due_date_asc"|"due_date_desc"|"priority_desc".
Return valid JSON only."""

    user = f"""Question: {query}

current_user_name: {me}
team_member_names: {json.dumps(names, ensure_ascii=False)}

IMPORTANT:
- Fill every key. Use null for unknown values.
- If it's general knowledge, set action="general_question".
- If asking about tasks to do today/priorities/what to work on, set action="query_tasks" and due_bucket="today".
Return JSON only."""

    tmpl = PromptTemplate.from_template("{system}\n{user}")
    llm = OllamaLLM(model="llama3")
    raw = llm.invoke(tmpl.format(system=system, user=user)).strip()

    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = {
            "action": "general_question",
            "target_user": {"type": "me"},
            "time": {"natural": "", "start": None, "end": None},
            "filters": {
                "priority": None, "status": None, "due_bucket": None,
                "board": None, "limit": None, "sort": None
            }
        }
    
    f = parsed.get("filters") or {}
    parsed["filters"] = {
        "priority": f.get("priority"),
        "status": f.get("status"),
        "due_bucket": f.get("due_bucket"),
        "board": f.get("board"),
        "limit": f.get("limit"),
        "sort": f.get("sort"),
    }
    return parsed

def get_rag_response(query: str, user_context: str = ""):
    print("🚨 USING UPDATED CODE VERSION")
    print(f"\n📝 Incoming query: {query}")
    print(f"\n📊 User context length: {len(user_context)} characters")

    if not wait_for_ollama():
        return "⚠️ Ollama is not responding. Please try again later."

    os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"

    # Lazy imports to avoid startup errors
    from langchain_ollama.embeddings import OllamaEmbeddings
    from langchain_ollama import OllamaLLM
    from langchain_chroma import Chroma

    # Determine if this is a user-specific query or general question
    user_specific_keywords = [
        "my task", "i should", "what should i", "today", "priority", 
        "complete", "work on", "focus on", "due", "urgent", "overdue"
    ]
    
    is_user_specific = any(keyword in query.lower() for keyword in user_specific_keywords)
    
    print(f"🔍 Is user-specific query: {is_user_specific}")

    # Always try to get relevant documents for context
    vectordb = Chroma(
        persist_directory="vector_store",
        embedding_function=OllamaEmbeddings(model="all-minilm")
    )

    docs = vectordb.similarity_search(query, k=2)  # Reduced to 2 to prioritize user data
    
    # Build context intelligently
    context_parts = []
    
    # 1. Always prioritize user-specific data if available
    if user_context.strip():
        print("📋 Using user-specific context from Supabase")
        context_parts.append(f"USER'S CURRENT DATA:\n{user_context}")
    
    # 2. Add document context for general knowledge/guidance
    if docs:
        print(f"📚 Found {len(docs)} relevant documents")
        doc_content = []
        for i, doc in enumerate(docs):
            print(f"→ Doc {i+1}:\n{doc.page_content[:200]}...\n")
            doc_content.append(doc.page_content)
        
        if doc_content:
            context_parts.append(f"GENERAL GUIDANCE:\n" + "\n---\n".join(doc_content))
    
    # Combine contexts
    final_context = "\n\n".join(context_parts) if context_parts else ""

    # Create different prompt templates based on query type
    if is_user_specific and user_context.strip():
        prompt_template = PromptTemplate.from_template("""
You are a helpful AI project assistant. The user is asking about their specific tasks and priorities.

CRITICAL: The CONTEXT below contains the user's ACTUAL TASK DATA from their project management system. You MUST use this data to answer their question. Do NOT give generic advice about project management tools.

CONTEXT:
{context}

USER QUESTION: {query}

INSTRUCTIONS:
- Look at the ACTUAL tasks listed in the context above
- If there are OVERDUE tasks, prioritize those first
- If there are tasks DUE TODAY, mention those specifically
- Reference the actual task names and due dates shown
- Give specific recommendations based on the priority levels shown
- If no tasks are due today, suggest the most urgent upcoming items
- Be direct and actionable

Answer based ONLY on the actual task data shown in the context:
""")
    else:
        prompt_template = PromptTemplate.from_template("""
You are a helpful project assistant. Answer the user's question using the available context.

CONTEXT:
{context}

QUESTION: {query}

Answer:
""")

    print("🧠 Final context preview:\n", (final_context or "")[:500], "...\n")
    final_prompt = prompt_template.format(
        context=final_context or "(No specific context available)", 
        query=query
    )

    try:
        llm = OllamaLLM(model="llama3")
        start = time.time()
        result = llm.invoke(final_prompt)
        print("⏱️ LLM Response Time:", round(time.time() - start, 2), "seconds")
        
        # Post-process the result to ensure it's helpful
        if is_user_specific and user_context.strip():
            if "PMT Pro" in result or "chatbot" in result.lower() or "AI assistant" in result:
                # The LLM is giving generic responses, try to make it more specific
                result = f"Based on your current task data: {result}"
        
        return result
    except Exception as e:
        print("❌ LLM call failed:", str(e))
        return "⚠️ LLM failed to generate a response. Please check the backend"