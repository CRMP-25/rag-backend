from typing import Dict, Any, List
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

def parse_user_context(user_context: str) -> Dict[str, Any]:
    """Enhanced context parsing for both tasks and messages"""
    
    parsed_data = {
        # Task data
        "tasks": {
            "overdue": [],
            "today": [],
            "upcoming": [],
            "total_count": 0
        },
        # Message data
        "messages": {
            "today": [],
            "yesterday": [],
            "this_week": [],
            "total_count": 0,
            "by_sender": {}
        },
        "team_members": []
    }
    
    if not user_context.strip():
        return parsed_data
    
    lines = user_context.split('\n')
    current_section = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Section identification
        if "YOUR ACTIVE TASKS:" in line or "YOUR KANBAN TASKS:" in line:
            current_section = "tasks"
            continue
        elif "TEAM MESSAGES:" in line:
            current_section = "messages"
            continue
        elif "TEAM MEMBERS:" in line:
            members_text = line.replace("👥 TEAM MEMBERS:", "").strip()
            parsed_data["team_members"] = [name.strip() for name in members_text.split(",") if name.strip()]
            continue
            
        # Parse content based on section
        if line.startswith("•") or line.startswith("→"):
            if current_section == "tasks":
                task_info = parse_task_line(line)
                if task_info:
                    parsed_data["tasks"]["total_count"] += 1
                    if task_info["urgency"] == "OVERDUE":
                        parsed_data["tasks"]["overdue"].append(task_info)
                    elif task_info["urgency"] == "DUE TODAY":
                        parsed_data["tasks"]["today"].append(task_info)
                    else:
                        parsed_data["tasks"]["upcoming"].append(task_info)
                        
            elif current_section == "messages":
                msg_info = parse_message_line(line)
                if msg_info:
                    parsed_data["messages"]["total_count"] += 1
                    
                    # Categorize by recency
                    if msg_info["recency"] == "today":
                        parsed_data["messages"]["today"].append(msg_info)
                    elif msg_info["recency"] == "yesterday":
                        parsed_data["messages"]["yesterday"].append(msg_info)
                    else:
                        parsed_data["messages"]["this_week"].append(msg_info)
                    
                    # Group by sender
                    sender = msg_info["sender_name"]
                    if sender not in parsed_data["messages"]["by_sender"]:
                        parsed_data["messages"]["by_sender"][sender] = []
                    parsed_data["messages"]["by_sender"][sender].append(msg_info)
    
    return parsed_data

def parse_task_line(line: str) -> Dict[str, Any]:
    """Parse task line to extract task information"""
    
    # Pattern: • [URGENCY] Task Name (Priority: X, Due: Y)
    pattern = r"[•→]\s*\[([^\]]+)\]\s*([^(]+)\s*\([^)]*Priority:\s*([^,)]+)[^)]*Due:\s*([^)]+)[^)]*\)"
    
    match = re.search(pattern, line)
    if not match:
        # Fallback pattern for simpler format
        simple_pattern = r"[•→]\s*([^(]+)"
        simple_match = re.search(simple_pattern, line)
        if simple_match:
            return {
                "task_name": simple_match.group(1).strip(),
                "urgency": "Unknown",
                "priority": "Medium",
                "due_date": "No date"
            }
        return None
    
    urgency = match.group(1).strip()
    task_name = match.group(2).strip()
    priority = match.group(3).strip()
    due_date = match.group(4).strip()
    
    return {
        "task_name": task_name,
        "urgency": urgency,
        "priority": priority,
        "due_date": due_date
    }

def parse_message_line(line: str) -> Dict[str, Any]:
    """Parse message line to extract message information"""
    
    # Multiple patterns for different message formats
    patterns = [
        r"From\s+([^(]+?)\s*\((\d+)\s*messages?\).*?Latest\s*\(([^)]+)\):\s*(.+)",
        r"From\s+([^:]+):\s*([^(]+)\s*\(([^)]+)\)",
        r"[•→]\s*From\s+([^:]+):\s*(.+)",
        r"[•→]\s*([^:]+?):\s*(.+)"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, line, re.IGNORECASE)
        if match:
            if len(match.groups()) >= 4:  # Complex pattern
                sender_name = match.group(1).strip()
                message_count = int(match.group(2)) if match.group(2).isdigit() else 1
                timestamp_str = match.group(3).strip()
                message_content = match.group(4).strip()
            else:  # Simple pattern
                sender_name = match.group(1).strip()
                message_content = match.group(2).strip() if len(match.groups()) >= 2 else ""
                timestamp_str = match.group(3).strip() if len(match.groups()) >= 3 else "recent"
                message_count = 1
            
            # Determine recency based on context clues
            recency = "this_week"  # default
            if "TODAY:" in line or "today" in timestamp_str.lower():
                recency = "today"
            elif "YESTERDAY:" in line or "yesterday" in timestamp_str.lower():
                recency = "yesterday"
            
            return {
                "sender_name": sender_name,
                "message_content": message_content,
                "timestamp_str": timestamp_str,
                "recency": recency,
                "message_count": message_count
            }
    
    return None

def classify_query_type(query: str, team_members: List[str] = None) -> str:
    """Enhanced query classification"""
    
    query_lower = query.lower()
    team_members = team_members or []
    
    # Message indicators
    message_keywords = [
        "message", "messages", "chat", "said", "told", "replied", 
        "conversation", "spoke", "mentioned", "contacted", "reached out",
        "sent", "received", "hear from", "got any", "any word from",
        "text", "texted", "communicate", "communication", "msg", "msgs"
    ]
    
    # Task indicators  
    task_keywords = [
        "task", "tasks", "work", "complete", "finish", "priority", 
        "due", "deadline", "project", "assignment", "todo", "do today",
        "overdue", "schedule", "kanban", "start", "begin", "working on",
        "should", "what should i", "complete today", "work on today"
    ]
    
    # Check for team member mentions
    mentions_team_member = False
    for member in team_members:
        member_lower = member.lower()
        first_name = member.split()[0].lower()
        if (member_lower in query_lower or 
            first_name in query_lower or
            f"from {first_name}" in query_lower):
            mentions_team_member = True
            break
    
    # Strong message patterns
    message_patterns = [
        r"did.*get.*message", r"any.*message.*from", r"message.*from.*today",
        r"hear.*from", r"said.*anything", r"contact.*me", r"anyone.*message",
        r"team.*message", r"word.*from", r"got.*any.*message"
    ]
    
    # Strong task patterns
    task_patterns = [
        r"what.*should.*do", r"what.*should.*complete", r"what.*should.*work",
        r"complete.*today", r"work.*today", r"task.*today", r"priority.*today",
        r"what.*task", r"which.*task", r"next.*task"
    ]
    
    # Check strong patterns first
    for pattern in message_patterns:
        if re.search(pattern, query_lower):
            return "message_query"
    
    for pattern in task_patterns:
        if re.search(pattern, query_lower):
            return "task_query"
    
    # If mentions team member + message keywords
    if mentions_team_member and any(kw in query_lower for kw in message_keywords):
        return "message_query"
    
    # Count keyword scores
    message_score = sum(1 for kw in message_keywords if kw in query_lower)
    task_score = sum(1 for kw in task_keywords if kw in query_lower)
    
    if message_score > task_score and message_score > 0:
        return "message_query"
    elif task_score >= message_score and task_score > 0:
        return "task_query"
    else:
        return "general_query"

def get_rag_response(query: str, user_context: str = ""):
    """Main RAG response function with enhanced task/message handling"""
    
    print(f"🔥 ENHANCED RAG ENGINE - Processing query: {query}")
    print(f"📊 Context length: {len(user_context)} characters")

    if not wait_for_ollama():
        return "⚠️ AI backend is temporarily unavailable. Please try again in a moment."

    # Parse the context
    parsed_data = parse_user_context(user_context)
    
    print(f"📋 Parsed tasks: {parsed_data['tasks']['total_count']}")
    print(f"💬 Parsed messages: {parsed_data['messages']['total_count']}")
    
    # Classify the query
    query_type = classify_query_type(query, parsed_data['team_members'])
    print(f"🎯 Query classified as: {query_type}")
    
    # Generate response based on query type
    if query_type == "message_query":
        return generate_message_response(query, parsed_data)
    elif query_type == "task_query":
        return generate_task_response(query, parsed_data)
    else:
        return generate_general_response(query, parsed_data, user_context)

def generate_task_response(query: str, parsed_data: Dict[str, Any]) -> str:
    """Generate response specifically for task queries"""
    
    print("🎯 Generating TASK response")
    
    tasks = parsed_data["tasks"]
    
    # Handle different task scenarios
    if tasks["overdue"]:
        return handle_overdue_tasks(tasks["overdue"], query)
    elif tasks["today"]:
        return handle_today_tasks(tasks["today"], query)
    elif tasks["upcoming"]:
        return handle_upcoming_tasks(tasks["upcoming"], query)
    else:
        return handle_no_tasks(query)

def handle_overdue_tasks(overdue_tasks: List[Dict], query: str) -> str:
    """Handle overdue task scenarios"""
    
    count = len(overdue_tasks)
    response_parts = [
        f"🚨 **URGENT: You have {count} overdue task{'s' if count > 1 else ''}!**",
        "",
        "**❌ Do NOT start new work today until these are resolved:**"
    ]
    
    for i, task in enumerate(overdue_tasks[:3], 1):
        response_parts.append(f"{i}. **{task['task_name']}** (Due: {task['due_date']}, Priority: {task['priority']})")
    
    if count > 3:
        response_parts.append(f"...and {count - 3} more overdue tasks")
    
    response_parts.extend([
        "",
        "**💡 Immediate Action Required:**",
        f"Start with: **{overdue_tasks[0]['task_name']}**",
        "",
        "Clear your schedule and focus on catching up!"
    ])
    
    return "\n".join(response_parts)

def handle_today_tasks(today_tasks: List[Dict], query: str) -> str:
    """Handle tasks due today"""
    
    count = len(today_tasks)
    response_parts = [
        f"📅 **You have {count} task{'s' if count > 1 else ''} due TODAY:**",
        ""
    ]
    
    for i, task in enumerate(today_tasks, 1):
        response_parts.append(f"{i}. **{task['task_name']}** (Priority: {task['priority']})")
    
    response_parts.extend([
        "",
        "**💡 Recommendation:** Start with the highest priority task and work systematically through the list."
    ])
    
    return "\n".join(response_parts)

def handle_upcoming_tasks(upcoming_tasks: List[Dict], query: str) -> str:
    """Handle upcoming tasks"""
    
    count = len(upcoming_tasks)
    response_parts = [
        "✅ **Great news! No tasks due today.**",
        f"📈 You have {count} upcoming task{'s' if count > 1 else ''}:",
        ""
    ]
    
    for i, task in enumerate(upcoming_tasks[:5], 1):
        response_parts.append(f"{i}. **{task['task_name']}** (Due: {task['due_date']}, Priority: {task['priority']})")
    
    if count > 5:
        response_parts.append(f"...and {count - 5} more tasks")
    
    response_parts.extend([
        "",
        "**💡 Perfect time to:** Get ahead on upcoming work or focus on professional development!"
    ])
    
    return "\n".join(response_parts)

def handle_no_tasks(query: str) -> str:
    """Handle when no tasks are found"""
    
    return """🎉 **Excellent! No pending tasks found.**

You're completely caught up! This is perfect timing to:
• Plan ahead for upcoming projects  
• Focus on professional development
• Take a well-deserved break
• Review and organize your workflow

Keep up the outstanding work!"""

def generate_message_response(query: str, parsed_data: Dict[str, Any]) -> str:
    """Generate response specifically for message queries"""
    
    print("💬 Generating MESSAGE response")
    
    messages = parsed_data["messages"]
    query_lower = query.lower()
    
    # Extract person name from query
    mentioned_person = None
    for member in parsed_data["team_members"]:
        member_lower = member.lower()
        first_name = member.split()[0].lower()
        if member_lower in query_lower or first_name in query_lower:
            mentioned_person = member
            break
    
    print(f"👤 Looking for messages from: {mentioned_person}")
    
    # Handle different message query types
    if mentioned_person:
        return handle_person_specific_messages(messages, mentioned_person, query)
    elif "today" in query_lower:
        return handle_today_messages(messages, query)
    elif "yesterday" in query_lower:
        return handle_yesterday_messages(messages, query)
    else:
        return handle_general_messages(messages, query)

def handle_person_specific_messages(messages: Dict, person: str, query: str) -> str:
    """Handle messages from specific person"""
    
    person_messages = []
    for sender, msg_list in messages["by_sender"].items():
        if person.lower() in sender.lower():
            person_messages.extend(msg_list)
    
    if person_messages:
        response_parts = [f"✅ **Yes, you received messages from {person}:**", ""]
        
        today_msgs = [m for m in person_messages if m["recency"] == "today"]
        if today_msgs:
            response_parts.append("**Today:**")
            for msg in today_msgs[:3]:
                response_parts.append(f"• {msg['timestamp_str']}: {msg['message_content']}")
        
        yesterday_msgs = [m for m in person_messages if m["recency"] == "yesterday"]  
        if yesterday_msgs:
            response_parts.append("**Yesterday:**")
            for msg in yesterday_msgs[:2]:
                response_parts.append(f"• {msg['timestamp_str']}: {msg['message_content']}")
                
        return "\n".join(response_parts)
    else:
        return f"❌ **No recent messages from {person}.**\n\nTry checking the spelling or look at your full message history."

def handle_today_messages(messages: Dict, query: str) -> str:
    """Handle today's messages query"""
    
    today_msgs = messages["today"]
    
    if today_msgs:
        count = len(today_msgs)
        response_parts = [f"📧 **You received {count} message{'s' if count > 1 else ''} today:**", ""]
        
        for msg in today_msgs[:5]:
            response_parts.append(f"• **{msg['sender_name']}** ({msg['timestamp_str']}): {msg['message_content']}")
            
        return "\n".join(response_parts)
    else:
        return "❌ **No messages received today.**\n\n🔭 Your inbox is empty for today."

def handle_yesterday_messages(messages: Dict, query: str) -> str:
    """Handle yesterday's messages query"""
    
    yesterday_msgs = messages["yesterday"]
    
    if yesterday_msgs:
        count = len(yesterday_msgs)
        response_parts = [f"📧 **You received {count} message{'s' if count > 1 else ''} yesterday:**", ""]
        
        for msg in yesterday_msgs[:5]:
            response_parts.append(f"• **{msg['sender_name']}** ({msg['timestamp_str']}): {msg['message_content']}")
            
        return "\n".join(response_parts)
    else:
        return "❌ **No messages received yesterday.**"

def handle_general_messages(messages: Dict, query: str) -> str:
    """Handle general message queries"""
    
    total = messages["total_count"]
    
    if total == 0:
        return "❌ **No recent messages found.**\n\nCheck your message settings or try refreshing."
    
    response_parts = [f"📧 **Message Summary ({total} total messages):**", ""]
    
    if messages["today"]:
        response_parts.append(f"**Today:** {len(messages['today'])} messages")
    if messages["yesterday"]:
        response_parts.append(f"**Yesterday:** {len(messages['yesterday'])} messages")
    if messages["this_week"]:
        response_parts.append(f"**This week:** {len(messages['this_week'])} messages")
    
    # Top senders
    if messages["by_sender"]:
        response_parts.append("\n**Most active contacts:**")
        sorted_senders = sorted(messages["by_sender"].items(), 
                              key=lambda x: len(x[1]), reverse=True)[:3]
        for sender, msg_list in sorted_senders:
            response_parts.append(f"• {sender}: {len(msg_list)} messages")
    
    return "\n".join(response_parts)

def generate_general_response(query: str, parsed_data: Dict[str, Any], context: str) -> str:
    """Generate response for general queries using LLM"""
    
    print("🤖 Generating GENERAL response with LLM")
    
    os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
    
    prompt_template = PromptTemplate.from_template("""
You are a professional project management assistant.

CONTEXT:
{context}

USER QUESTION: "{query}"

Based on the context provided, give a helpful and specific response. If the context contains task information, focus on tasks. If it contains message information, focus on messages. Be direct and actionable.

Response:
""")

    try:
        llm = OllamaLLM(model="llama3")
        final_prompt = prompt_template.format(
            context=context[:2000],  # Limit context size
            query=query
        )
        
        result = llm.invoke(final_prompt)
        return result.strip()
        
    except Exception as e:
        print(f"❌ LLM call failed: {e}")
        return "⚠️ Unable to process your request right now. Please try again in a moment."

# Keep the existing interpret_query function
def interpret_query(query: str, hints: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Query interpretation function"""
    hints = hints or {}
    names = hints.get("team_member_names", [])
    
    query_lower = query.lower()
    target_user = {"type": "me"}
    
    # Check for specific user names
    for name in names:
        if name.lower() in query_lower:
            target_user = {"type": "name", "value": name}
            break
    
    # Determine action
    action = "general_question"
    if any(word in query_lower for word in ["message", "messages", "chat", "said", "told"]):
        action = "query_messages"
    elif any(word in query_lower for word in ["task", "complete", "work on", "priority", "due"]):
        action = "query_tasks"
    
    return {
        "action": action,
        "target_user": target_user,
        "time": {"natural": query, "start": None, "end": None},
        "filters": {
            "priority": None,
            "status": None,
            "due_bucket": "today" if "today" in query_lower else None,
            "board": None,
            "limit": None,
            "sort": "due_date_asc"
        }
    }