from typing import Dict, Any
import os, time, requests, json, re
from datetime import datetime, timedelta
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

def parse_task_context(user_context: str) -> Dict[str, Any]:
    """Parse the user context to extract structured task information"""
    
    parsed_data = {
        "overdue_tasks": [],
        "today_tasks": [],
        "upcoming_tasks": [],
        "total_tasks": 0,
        "has_urgent_items": False
    }
    
    if not user_context.strip():
        return parsed_data
    
    # Extract today's date from context
    today_match = re.search(r"📅 TODAY'S DATE: (\d{1,2}/\d{1,2}/\d{4})", user_context)
    if today_match:
        today_str = today_match.group(1)
        try:
            today = datetime.strptime(today_str, "%m/%d/%Y").date()
        except:
            today = datetime.now().date()
    else:
        today = datetime.now().date()
    
    # Parse task sections
    lines = user_context.split('\n')
    current_section = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Identify sections
        if "YOUR ACTIVE TASKS:" in line:
            current_section = "active"
        elif "YOUR KANBAN TASKS:" in line:
            current_section = "kanban"
        elif "YOUR SUBTASKS:" in line:
            current_section = "subtasks"
        elif line.startswith("•"):
            # Parse task line
            task_info = parse_task_line(line, today)
            if task_info:
                parsed_data["total_tasks"] += 1
                
                if task_info["urgency"] == "OVERDUE":
                    parsed_data["overdue_tasks"].append(task_info)
                    parsed_data["has_urgent_items"] = True
                elif task_info["urgency"] == "DUE TODAY":
                    parsed_data["today_tasks"].append(task_info)
                    parsed_data["has_urgent_items"] = True
                else:
                    parsed_data["upcoming_tasks"].append(task_info)
    
    return parsed_data

def parse_task_line(line: str, today_date) -> Dict[str, Any]:
    """Parse individual task line to extract task information"""
    
    # Pattern: • [URGENCY] Task Name (Priority: X, Due: Y)
    pattern = r"•\s*\[([^\]]+)\]\s*([^(]+)\s*\(Priority:\s*([^,]+),\s*(?:Status:\s*([^,]+),\s*)?Due:\s*([^)]+)\)"
    
    match = re.search(pattern, line)
    if not match:
        # Fallback parsing
        return {
            "task_name": line.replace("•", "").strip(),
            "urgency": "Unknown",
            "priority": "Normal",
            "status": "Pending",
            "due_date": "No date"
        }
    
    urgency = match.group(1).strip()
    task_name = match.group(2).strip()
    priority = match.group(3).strip()
    status = match.group(4).strip() if match.group(4) else "Pending"
    due_date = match.group(5).strip()
    
    return {
        "task_name": task_name,
        "urgency": urgency,
        "priority": priority,
        "status": status,
        "due_date": due_date
    }

def interpret_query(query: str, hints: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Enhanced query interpretation with better user name resolution"""
    hints = hints or {}
    names = hints.get("team_member_names", [])
    me = hints.get("current_user_name", "")

    # Enhanced user detection
    query_lower = query.lower()
    target_user = {"type": "me"}
    
    # Check for specific user names in query
    for name in names:
        if name.lower() in query_lower:
            target_user = {"type": "name", "value": name}
            break
    
    # Check for common name patterns
    name_patterns = [
        r'\b(\w+)\s+task',
        r'(\w+)\'s\s+task',
        r'for\s+(\w+)',
        r'about\s+(\w+)'
    ]
    
    for pattern in name_patterns:
        match = re.search(pattern, query_lower)
        if match:
            potential_name = match.group(1).title()
            # Find closest match in team names
            for name in names:
                if potential_name.lower() in name.lower() or name.lower().startswith(potential_name.lower()):
                    target_user = {"type": "name", "value": name}
                    break

    # Determine action based on query content
    action = "general_question"
    if any(word in query_lower for word in ["task", "complete", "work on", "priority", "due"]):
        action = "query_tasks"
    elif any(word in query_lower for word in ["kanban", "board", "column"]):
        action = "query_kanban"
    elif any(word in query_lower for word in ["message", "chat", "conversation"]):
        action = "query_messages"
    
    # Time and priority detection
    due_bucket = None
    if "today" in query_lower:
        due_bucket = "today"
    elif "overdue" in query_lower:
        due_bucket = "overdue"
    elif "tomorrow" in query_lower:
        due_bucket = "tomorrow"
    
    return {
        "action": action,
        "target_user": target_user,
        "time": {
            "natural": query,
            "start": None,
            "end": None
        },
        "filters": {
            "priority": None,
            "status": None,
            "due_bucket": due_bucket,
            "board": None,
            "limit": None,
            "sort": "due_date_asc"
        }
    }

def get_rag_response(query: str, user_context: str = ""):
    """Enhanced RAG response with better task analysis"""
    print("🚨 USING ENHANCED RAG ENGINE")
    print(f"\n🔍 Incoming query: {query}")
    print(f"\n📊 User context length: {len(user_context)} characters")

    if not wait_for_ollama():
        return "⚠️ Ollama is not responding. Please try again later."

    os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"

    # Parse the user context to understand task structure
    task_data = parse_task_context(user_context)
    
    print(f"📋 Parsed task data: {task_data['total_tasks']} total tasks")
    print(f"🚨 Overdue: {len(task_data['overdue_tasks'])}")
    print(f"📅 Due today: {len(task_data['today_tasks'])}")
    
    # Determine query type
    query_lower = query.lower()
    is_today_query = "today" in query_lower
    is_priority_query = any(word in query_lower for word in ["priority", "important", "urgent", "should"])
    
    # Build specific response based on task data
    if user_context.strip() and (is_today_query or is_priority_query):
        return generate_task_specific_response(query, task_data)
    
    # Fallback to document-based response
    return generate_document_response(query, user_context)

def generate_task_specific_response(query: str, task_data: Dict[str, Any]) -> str:
    """Generate response based on actual task data"""
    
    response_parts = []
    
    # Handle overdue tasks first
    if task_data["overdue_tasks"]:
        response_parts.append("🚨 **URGENT - Overdue Tasks:**")
        for task in task_data["overdue_tasks"][:3]:  # Show top 3
            response_parts.append(f"• **{task['task_name']}** (Priority: {task['priority']}, Due: {task['due_date']})")
        response_parts.append("")
    
    # Handle today's tasks
    if task_data["today_tasks"]:
        response_parts.append("📅 **Tasks Due Today:**")
        for task in task_data["today_tasks"]:
            response_parts.append(f"• **{task['task_name']}** (Priority: {task['priority']})")
        response_parts.append("")
    
    # Recommendations
    response_parts.append("🎯 **My Recommendation:**")
    
    if task_data["overdue_tasks"]:
        high_priority_overdue = [t for t in task_data["overdue_tasks"] if t["priority"] == "High"]
        if high_priority_overdue:
            response_parts.append(f"1. **Start immediately with**: {high_priority_overdue[0]['task_name']}")
        else:
            response_parts.append(f"1. **Handle overdue first**: {task_data['overdue_tasks'][0]['task_name']}")
    
    if task_data["today_tasks"]:
        response_parts.append(f"2. **Complete today's deadline**: {task_data['today_tasks'][0]['task_name']}")
    
    if task_data["upcoming_tasks"]:
        high_priority_upcoming = [t for t in task_data["upcoming_tasks"] if t["priority"] == "High"]
        if high_priority_upcoming:
            response_parts.append(f"3. **Prepare for upcoming high-priority**: {high_priority_upcoming[0]['task_name']}")
    
    # If no tasks for today
    if not task_data["today_tasks"] and not task_data["overdue_tasks"]:
        if task_data["upcoming_tasks"]:
            next_task = task_data["upcoming_tasks"][0]
            response_parts = [
                "✅ No tasks due today!",
                "",
                f"🔜 **Next upcoming task**: {next_task['task_name']} (Due: {next_task['due_date']}, Priority: {next_task['priority']})",
                "",
                "💡 **Suggestion**: Use this free time to get ahead on your upcoming tasks or tackle any backlog items."
            ]
        else:
            response_parts = [
                "🎉 Great news! You have no pending tasks.",
                "",
                "💡 **Suggestion**: This is a perfect time to plan ahead, review your goals, or take on new initiatives."
            ]
    
    return "\n".join(response_parts)

def generate_document_response(query: str, user_context: str) -> str:
    """Fallback to document-based response"""
    
    # Lazy imports to avoid startup errors
    from langchain_ollama.embeddings import OllamaEmbeddings
    from langchain_ollama import OllamaLLM
    from langchain_chroma import Chroma

    try:
        vectordb = Chroma(
            persist_directory="vector_store",
            embedding_function=OllamaEmbeddings(model="all-minilm")
        )
        docs = vectordb.similarity_search(query, k=2)
        doc_content = "\n---\n".join([doc.page_content for doc in docs]) if docs else ""
    except Exception as e:
        print(f"⚠️ Document search failed: {e}")
        doc_content = ""

    # Enhanced prompt template
    prompt_template = PromptTemplate.from_template("""
You are a professional project management assistant. Answer the user's question directly and actionably.

USER DATA:
{user_context}

KNOWLEDGE BASE:
{doc_content}

QUESTION: {query}

INSTRUCTIONS:
- If the user has specific task data, reference their actual tasks by name
- Be direct and avoid generic advice
- Focus on actionable recommendations
- If no specific data is available, acknowledge this clearly

Response:
""")

    try:
        llm = OllamaLLM(model="llama3")
        final_prompt = prompt_template.format(
            user_context=user_context or "No specific task data available",
            doc_content=doc_content or "No additional documentation available",
            query=query
        )
        
        result = llm.invoke(final_prompt)
        return result.strip()
        
    except Exception as e:
        print(f"❌ LLM call failed: {e}")
        return "⚠️ Unable to generate response. Please try again later."