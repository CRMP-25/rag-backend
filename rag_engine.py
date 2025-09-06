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

    Returns JSON like:
    {
      "action": "query_tasks" | "query_kanban" | "query_files" | "query_profile" | "query_messages" | "general_question",
      "target_user": {"type": "me"} | {"type": "name", "value": "Sai Prasad"},
      "time": {"natural": "yesterday", "start": null|"<YYYY-MM-DD>", "end": null|"<YYYY-MM-DD>"},
      "filters": {
        "priority": null|"High"|"Medium"|"Low",
        "status": null|"Open"|"In Progress"|"Done"|"Completed"|"Archived",
        "due_bucket": null|"overdue"|"today"|"tomorrow"|"this_week"|"next_week"|"this_month",
        "board": null|"tasks"|"kanban"|"calendar"|"files"|"messages",
        "limit": 0-50,
        "sort": null|"due_date_asc"|"due_date_desc"|"priority_desc"
      }
    }
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
    print(f"\n🔍 Incoming query: {query}")

    if not wait_for_ollama():
        return "⚠️ Ollama is not responding. Please try again later."

    os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"

    # lazy imports to avoid startup errors
    from langchain_ollama.embeddings import OllamaEmbeddings
    from langchain_ollama import OllamaLLM
    from langchain_chroma import Chroma

    vectordb = Chroma(
        persist_directory="vector_store",
        embedding_function=OllamaEmbeddings(model="all-minilm")
    )

    docs = vectordb.similarity_search(query, k=3)
    if not docs:
        print("⚠️ No documents returned from vector search.")
        # still answer from general knowledge (fallback)
        context = user_context
    else:
        for i, doc in enumerate(docs):
            print(f"→ Doc {i+1}:\n{doc.page_content[:300]}...\n")
        relevant_docs = [doc.page_content for doc in docs]
        doc_context = "\n---\n".join(relevant_docs)
        context = f"{user_context}\n\n--- DOCUMENT CONTEXT ---\n{doc_context}"

    prompt_template = PromptTemplate.from_template("""
You are a helpful project assistant. Prefer answering from the supplied CONTEXT.
If the CONTEXT clearly contains the answer, cite it naturally (e.g., “From Supabase data, ...”).
If the CONTEXT is missing or insufficient, still answer from your general knowledge
and say briefly that the exact detail wasn't found in context.

CONTEXT:
{context}

QUESTION:
{query}

Answer:
""")

    print("🧠 Combined Context Sent to LLM:\n", (context or "")[:500], "...\n")
    final_prompt = prompt_template.format(context=context or "(no context)", query=query)

    try:
        llm = OllamaLLM(model="llama3")
        start = time.time()
        result = llm.invoke(final_prompt)
        print("⏱️ LLM Response Time:", round(time.time() - start, 2), "seconds")
        return result
    except Exception as e:
        print("❌ LLM call failed:", str(e))
        return "⚠️ LLM failed to generate a response. Please check the backend"
