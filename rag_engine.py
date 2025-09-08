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

def parse_task_context(user_context: str) -> Dict[str, Any]:
    """Parse the user context to extract ALL tasks with better categorization"""
    
    parsed_data = {
        "overdue_tasks": [],
        "today_tasks": [],
        "upcoming_tasks": [],
        "messages_today": [],
        "total_tasks": 0,
        "total_kanban": 0,
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
    
    # Parse messages section
    message_section = re.search(r"🧾 Recent Messages:(.*?)(?=\n\n|$)", user_context, re.DOTALL)
    if message_section:
        message_lines = message_section.group(1).strip().split('\n')
        for line in message_lines:
            if line.strip().startswith("•"):
                # Extract message details
                msg_match = re.search(r"From ([^:]+): (.*?) \((.*?)\)", line)
                if msg_match:
                    sender = msg_match.group(1)
                    message = msg_match.group(2)
                    timestamp = msg_match.group(3)
                    
                    # Check if message is from today
                    try:
                        msg_date = datetime.fromisoformat(timestamp).date()
                        if msg_date == today:
                            parsed_data["messages_today"].append({
                                "sender": sender,
                                "message": message,
                                "timestamp": timestamp
                            })
                    except:
                        pass
    
    # Parse ALL task sections - not limiting to first few
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
            # Parse ALL task lines
            task_info = parse_task_line(line, today)
            if task_info:
                if current_section == "kanban":
                    parsed_data["total_kanban"] += 1
                else:
                    parsed_data["total_tasks"] += 1
                
                # Categorize by urgency
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
    
    # Enhanced pattern to capture all task formats
    patterns = [
        r"•\s*\[([^\]]+)\]\s*([^(]+)\s*\(Priority:\s*([^,]+),\s*(?:Status:\s*([^,]+),\s*)?Due:\s*([^)]+)\)",
        r"•\s*\[([^\]]+)\]\s*([^(]+)\s*\(Due:\s*([^)]+)\)",
        r"•\s*([^(]+)\s*\(Due:\s*([^)]+)\)"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            groups = match.groups()
            if len(groups) >= 5:  # Full pattern
                urgency = groups[0].strip()
                task_name = groups[1].strip()
                priority = groups[2].strip()
                status = groups[3].strip() if groups[3] else "Pending"
                due_date = groups[4].strip()
            elif len(groups) == 3:  # Simplified pattern with urgency
                urgency = groups[0].strip()
                task_name = groups[1].strip()
                due_date = groups[2].strip()
                priority = "Normal"
                status = "Pending"
            else:  # Basic pattern
                task_name = groups[0].strip()
                due_date = groups[1].strip()
                urgency = calculate_urgency(due_date, today_date)
                priority = "Normal"
                status = "Pending"
            
            return {
                "task_name": task_name,
                "urgency": urgency,
                "priority": priority,
                "status": status,
                "due_date": due_date
            }
    
    # Fallback parsing
    return {
        "task_name": line.replace("•", "").strip(),
        "urgency": "Unknown",
        "priority": "Normal",
        "status": "Pending",
        "due_date": "No date"
    }

def calculate_urgency(due_date_str: str, today_date) -> str:
    """Calculate urgency based on due date"""
    try:
        due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
        diff = (due_date - today_date).days
        
        if diff < 0:
            return "OVERDUE"
        elif diff == 0:
            return "DUE TODAY"
        elif diff == 1:
            return "Due Tomorrow"
        elif diff <= 7:
            return "Due This Week"
        else:
            return "Later"
    except:
        return "Unknown"

def get_rag_response(query: str, user_context: str = ""):
    """Enhanced RAG response with comprehensive task analysis"""
    print("🚨 USING ENHANCED RAG ENGINE")
    print(f"\n🔍 Incoming query: {query}")
    print(f"\n📊 User context length: {len(user_context)} characters")

    if not wait_for_ollama():
        return "⚠️ AI backend is temporarily unavailable. Please try again in a moment."

    # Parse the user context to understand task structure
    task_data = parse_task_context(user_context)
    
    print(f"📋 Total tasks: {task_data['total_tasks']}")
    print(f"📊 Total kanban: {task_data['total_kanban']}")
    print(f"🚨 Overdue: {len(task_data['overdue_tasks'])}")
    print(f"📅 Due today: {len(task_data['today_tasks'])}")
    print(f"💬 Messages today: {len(task_data['messages_today'])}")
    
    # Check if query is about messages
    query_lower = query.lower()
    if any(word in query_lower for word in ["message", "messages", "chat", "received", "sent"]):
        return handle_message_query(task_data, query)
    
    # Generate professional response based on task analysis
    return generate_professional_response(query, task_data, user_context)

def handle_message_query(task_data: Dict[str, Any], query: str) -> str:
    """Handle queries about messages"""
    
    messages_today = task_data.get("messages_today", [])
    
    if not messages_today:
        return """📬 **No Messages Today**

You haven't received any team messages today.

**💡 While it's quiet, you could:**
• Focus on your pending tasks without interruption
• Reach out to team members if you need updates
• Check in with colleagues about ongoing projects"""
    
    # Build message summary
    response_parts = [
        f"💬 **Today's Messages** ({len(messages_today)} received)",
        ""
    ]
    
    # Group messages by sender
    sender_messages = {}
    for msg in messages_today:
        sender = msg["sender"]
        if sender not in sender_messages:
            sender_messages[sender] = []
        sender_messages[sender].append(msg)
    
    # Format messages
    for sender, msgs in sender_messages.items():
        response_parts.append(f"**From {sender}:**")
        for msg in msgs[:3]:  # Show up to 3 messages per sender
            time_str = datetime.fromisoformat(msg["timestamp"]).strftime("%I:%M %p")
            response_parts.append(f"• {msg['message']} ({time_str})")
        if len(msgs) > 3:
            response_parts.append(f"• ...and {len(msgs) - 3} more messages")
        response_parts.append("")
    
    # Add context about tasks if relevant
    if task_data["overdue_tasks"]:
        response_parts.extend([
            "⚠️ **Note:** You also have overdue tasks that need attention.",
            "Consider addressing urgent tasks after reviewing messages.",
            ""
        ])
    
    return "\n".join(response_parts)

def generate_professional_response(query: str, task_data: Dict[str, Any], context: str) -> str:
    """Generate a professional, actionable response showing ALL tasks"""
    
    query_lower = query.lower()
    is_today_query = any(word in query_lower for word in ["today", "now", "current", "should"])
    
    # Case 1: User has overdue tasks - Show ALL of them
    if task_data["overdue_tasks"]:
        return handle_all_overdue_tasks(task_data, is_today_query)
    
    # Case 2: User has tasks due today
    if task_data["today_tasks"]:
        return handle_today_tasks_response(task_data)
    
    # Case 3: No tasks for today but has upcoming tasks
    if task_data["upcoming_tasks"]:
        return handle_upcoming_tasks_response(task_data)
    
    # Case 4: No tasks at all
    if task_data["total_tasks"] == 0 and task_data["total_kanban"] == 0:
        return handle_no_tasks_response()
    
    # Fallback: Use LLM for complex queries
    return generate_llm_response(query, context)

def handle_all_overdue_tasks(task_data: Dict[str, Any], is_today_query: bool) -> str:
    """Handle response showing ALL overdue tasks"""
    
    overdue_tasks = task_data["overdue_tasks"]
    overdue_count = len(overdue_tasks)
    today_count = len(task_data["today_tasks"])
    
    response_parts = [
        f"🚨 **URGENT ATTENTION REQUIRED**",
        f"You have **{overdue_count} overdue {'task' if overdue_count == 1 else 'tasks'}** that need immediate attention.",
        ""
    ]
    
    if is_today_query:
        response_parts.extend([
            "**❌ Nothing should be worked on 'today' until overdue items are resolved.**",
            ""
        ])
    
    # Get most critical task
    critical_task = get_most_critical_task(overdue_tasks)
    
    response_parts.extend([
        "**🎯 IMMEDIATE ACTION REQUIRED:**",
        f"**Start with: {critical_task['task_name']}**",
        f"• Originally due: {critical_task['due_date']}",
        f"• Priority: {critical_task['priority']}",
        "",
        "**📋 ALL OVERDUE TASKS:**"
    ])
    
    # List ALL overdue tasks grouped by priority
    high_priority = [t for t in overdue_tasks if t.get('priority', 'Normal') == 'High']
    medium_priority = [t for t in overdue_tasks if t.get('priority', 'Normal') in ['Medium', 'Normal']]
    low_priority = [t for t in overdue_tasks if t.get('priority', 'Normal') == 'Low']
    
    if high_priority:
        response_parts.append("\n**🔴 High Priority:**")
        for task in high_priority:
            response_parts.append(f"• {task['task_name']} (Due: {task['due_date']})")
    
    if medium_priority:
        response_parts.append("\n**🟡 Medium Priority:**")
        for task in medium_priority:
            response_parts.append(f"• {task['task_name']} (Due: {task['due_date']})")
    
    if low_priority:
        response_parts.append("\n**🟢 Low Priority:**")
        for task in low_priority:
            response_parts.append(f"• {task['task_name']} (Due: {task['due_date']})")
    
    response_parts.append("")
    
    if today_count > 0:
        response_parts.extend([
            f"**⚠️ Additional Pressure:** You also have {today_count} {'task' if today_count == 1 else 'tasks'} due today.",
            "Focus on clearing overdue items first to prevent further backlog.",
            ""
        ])
    
    response_parts.extend([
        "**💡 Recovery Strategy:**",
        "1. **Triage immediately** - Identify which overdue tasks have the biggest impact",
        "2. **Communicate proactively** - Inform stakeholders about revised timelines",
        "3. **Block time** - Clear your calendar for focused catch-up work",
        "4. **Prevent recurrence** - Set up better tracking and earlier warnings"
    ])
    
    return "\n".join(response_parts)

def handle_today_tasks_response(task_data: Dict[str, Any]) -> str:
    """Handle response when user has tasks due today (no overdue)"""
    
    today_tasks = task_data["today_tasks"]
    today_count = len(today_tasks)
    
    response_parts = [
        f"📅 **TODAY'S FOCUS** ({today_count} {'task' if today_count == 1 else 'tasks'} due)",
        ""
    ]
    
    # List all today's tasks
    response_parts.append("**🎯 Tasks to complete today:**")
    
    for i, task in enumerate(today_tasks, 1):
        priority_indicator = "🔥" if task.get('priority') == "High" else "📌"
        response_parts.append(f"{i}. {priority_indicator} {task['task_name']}")
        response_parts.append(f"   • Priority: {task.get('priority', 'Normal')}")
        response_parts.append(f"   • Status: {task.get('status', 'Pending')}")
    
    response_parts.append("")
    
    # Show upcoming tasks preview
    if task_data["upcoming_tasks"]:
        upcoming_count = len(task_data["upcoming_tasks"])
        response_parts.extend([
            f"**👀 Coming up** ({upcoming_count} tasks):",
        ])
        for task in task_data["upcoming_tasks"][:3]:
            response_parts.append(f"• {task['task_name']} (Due: {task['due_date']})")
        if upcoming_count > 3:
            response_parts.append(f"• ...and {upcoming_count - 3} more")
        response_parts.append("")
    
    response_parts.extend([
        "**💡 Today's Strategy:**",
        "1. Start with high-priority items during peak focus hours",
        "2. Break complex tasks into smaller milestones",
        "3. Update task status as you progress",
        "4. Leave buffer time for unexpected issues"
    ])
    
    return "\n".join(response_parts)

def handle_upcoming_tasks_response(task_data: Dict[str, Any]) -> str:
    """Handle response when no tasks today but has upcoming tasks"""
    
    upcoming = task_data["upcoming_tasks"]
    next_task = get_most_critical_task(upcoming)
    
    response_parts = [
        "✅ **GREAT NEWS!** No tasks due today.",
        "",
        f"**📮 Next priority: {next_task['task_name']}**",
        f"• Due: {next_task['due_date']}",
        f"• Priority: {next_task.get('priority', 'Normal')}",
        "",
        f"**📋 All upcoming tasks** ({len(upcoming)} total):"
    ]
    
    # Show all upcoming tasks
    for task in upcoming[:10]:  # Show up to 10
        response_parts.append(f"• {task['task_name']} (Due: {task['due_date']}, Priority: {task.get('priority', 'Normal')})")
    
    if len(upcoming) > 10:
        response_parts.append(f"• ...and {len(upcoming) - 10} more")
    
    response_parts.extend([
        "",
        "**💡 Today's Opportunity:**",
        "1. **Get ahead** - Start work on high-priority upcoming tasks",
        "2. **Plan ahead** - Review and organize your task pipeline",
        "3. **Optimize** - Improve your workflows and processes",
        "4. **Collaborate** - Help team members with their tasks"
    ])
    
    return "\n".join(response_parts)

def handle_no_tasks_response() -> str:
    """Handle response when user has no tasks"""
    
    return """🎉 **ALL CLEAR!** You have no pending tasks or kanban items.

**💡 Productive ways to use this time:**

1. **Strategic Planning**
   • Review quarterly goals and objectives
   • Plan upcoming projects and initiatives

2. **Professional Development**
   • Learn new skills or tools
   • Attend training or webinars

3. **Team Support**
   • Offer help to team members
   • Contribute to knowledge sharing

4. **Process Improvement**
   • Document best practices
   • Identify optimization opportunities

**🌟 You're in an excellent position to be proactive!**"""

def get_most_critical_task(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Get the most critical task based on priority and due date"""
    
    if not tasks:
        return None
    
    # Sort by priority (High > Medium > Low) then by due date
    priority_order = {"High": 0, "Medium": 1, "Low": 2, "Normal": 1}
    
    sorted_tasks = sorted(tasks, key=lambda t: (
        priority_order.get(t.get("priority", "Normal"), 3),
        t.get("due_date", "9999-12-31")
    ))
    
    return sorted_tasks[0]

def generate_llm_response(query: str, context: str) -> str:
    """Fallback to LLM for complex queries"""
    
    os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
    
    prompt_template = PromptTemplate.from_template("""
You are a professional project management assistant. Based on the user's task data, provide specific, actionable recommendations.

IMPORTANT RULES:
- If user has overdue tasks, ALWAYS list ALL of them
- Be specific with task names and counts
- For message queries, check the Recent Messages section
- Provide clear priorities and next steps

USER'S CURRENT DATA:
{context}

USER QUESTION: {query}

Provide a comprehensive, specific response:
""")

    try:
        llm = OllamaLLM(model="llama3")
        final_prompt = prompt_template.format(
            context=context or "No data available",
            query=query
        )
        
        result = llm.invoke(final_prompt)
        return result.strip()
        
    except Exception as e:
        print(f"❌ LLM call failed: {e}")
        return "⚠️ Unable to analyze your data right now. Please try again."

# Keep the existing interpret_query function unchanged
def interpret_query(query: str, hints: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Enhanced query interpretation"""
    hints = hints or {}
    names = hints.get("team_member_names", [])
    
    query_lower = query.lower()
    target_user = {"type": "me"}
    
    # Check for message-related queries
    is_message_query = any(word in query_lower for word in ["message", "messages", "chat", "received"])
    
    # Determine action
    action = "query_messages" if is_message_query else "query_tasks"
    
    return {
        "action": action,
        "target_user": target_user,
        "filters": {}
    }

# from typing import Dict, Any, List
# import os, time, requests, json, re
# from datetime import datetime, timedelta
# from langchain.prompts import PromptTemplate
# from langchain_ollama import OllamaLLM

# def wait_for_ollama(timeout=30):
#     print("⏳ Waiting for Ollama to be ready...")
#     for _ in range(timeout):
#         try:
#             r = requests.get("http://localhost:11434")
#             if r.status_code == 200:
#                 print("✅ Ollama is ready.")
#                 return True
#         except Exception:
#             pass
#         time.sleep(1)
#     print("❌ Ollama did not start in time.")
#     return False

# def parse_task_context(user_context: str) -> Dict[str, Any]:
#     """Parse the user context to extract structured task information"""
    
#     parsed_data = {
#         "overdue_tasks": [],
#         "today_tasks": [],
#         "upcoming_tasks": [],
#         "total_tasks": 0,
#         "has_urgent_items": False
#     }
    
#     if not user_context.strip():
#         return parsed_data
    
#     # Extract today's date from context
#     today_match = re.search(r"📅 TODAY'S DATE: (\d{1,2}/\d{1,2}/\d{4})", user_context)
#     if today_match:
#         today_str = today_match.group(1)
#         try:
#             today = datetime.strptime(today_str, "%m/%d/%Y").date()
#         except:
#             today = datetime.now().date()
#     else:
#         today = datetime.now().date()
    
#     # Parse task sections
#     lines = user_context.split('\n')
#     current_section = None
    
#     for line in lines:
#         line = line.strip()
#         if not line:
#             continue
            
#         # Identify sections
#         if "YOUR ACTIVE TASKS:" in line:
#             current_section = "active"
#         elif "YOUR KANBAN TASKS:" in line:
#             current_section = "kanban"
#         elif "YOUR SUBTASKS:" in line:
#             current_section = "subtasks"
#         elif line.startswith("•"):
#             # Parse task line
#             task_info = parse_task_line(line, today)
#             if task_info:
#                 parsed_data["total_tasks"] += 1
                
#                 if task_info["urgency"] == "OVERDUE":
#                     parsed_data["overdue_tasks"].append(task_info)
#                     parsed_data["has_urgent_items"] = True
#                 elif task_info["urgency"] == "DUE TODAY":
#                     parsed_data["today_tasks"].append(task_info)
#                     parsed_data["has_urgent_items"] = True
#                 else:
#                     parsed_data["upcoming_tasks"].append(task_info)
    
#     return parsed_data

# def parse_task_line(line: str, today_date) -> Dict[str, Any]:
#     """Parse individual task line to extract task information"""
    
#     # Pattern: • [URGENCY] Task Name (Priority: X, Due: Y)
#     pattern = r"•\s*\[([^\]]+)\]\s*([^(]+)\s*\(Priority:\s*([^,]+),\s*(?:Status:\s*([^,]+),\s*)?Due:\s*([^)]+)\)"
    
#     match = re.search(pattern, line)
#     if not match:
#         # Fallback parsing
#         return {
#             "task_name": line.replace("•", "").strip(),
#             "urgency": "Unknown",
#             "priority": "Normal",
#             "status": "Pending",
#             "due_date": "No date"
#         }
    
#     urgency = match.group(1).strip()
#     task_name = match.group(2).strip()
#     priority = match.group(3).strip()
#     status = match.group(4).strip() if match.group(4) else "Pending"
#     due_date = match.group(5).strip()
    
#     return {
#         "task_name": task_name,
#         "urgency": urgency,
#         "priority": priority,
#         "status": status,
#         "due_date": due_date
#     }

# def get_rag_response(query: str, user_context: str = ""):
#     """Enhanced RAG response with professional task analysis"""
#     print("🚨 USING ENHANCED RAG ENGINE")
#     print(f"\n🔍 Incoming query: {query}")
#     print(f"\n📊 User context length: {len(user_context)} characters")

#     if not wait_for_ollama():
#         return "⚠️ AI backend is temporarily unavailable. Please try again in a moment."

#     # Parse the user context to understand task structure
#     task_data = parse_task_context(user_context)
    
#     print(f"📋 Parsed task data: {task_data['total_tasks']} total tasks")
#     print(f"🚨 Overdue: {len(task_data['overdue_tasks'])}")
#     print(f"📅 Due today: {len(task_data['today_tasks'])}")
    
#     # Generate professional response based on task analysis
#     return generate_professional_response(query, task_data, user_context)

# def generate_professional_response(query: str, task_data: Dict[str, Any], context: str) -> str:
#     """Generate a professional, actionable response based on task analysis"""
    
#     query_lower = query.lower()
#     is_today_query = any(word in query_lower for word in ["today", "now", "current"])
#     is_priority_query = any(word in query_lower for word in ["priority", "important", "urgent", "should", "recommend"])
    
#     # Case 1: User has overdue tasks - HIGHEST PRIORITY
#     if task_data["overdue_tasks"]:
#         return handle_overdue_tasks_response(task_data, is_today_query)
    
#     # Case 2: User has tasks due today
#     if task_data["today_tasks"]:
#         return handle_today_tasks_response(task_data)
    
#     # Case 3: No tasks for today but has upcoming tasks
#     if task_data["upcoming_tasks"]:
#         return handle_upcoming_tasks_response(task_data)
    
#     # Case 4: No tasks at all
#     if task_data["total_tasks"] == 0:
#         return handle_no_tasks_response()
    
#     # Fallback: Use LLM for complex queries
#     return generate_llm_response(query, context)

# def handle_overdue_tasks_response(task_data: Dict[str, Any], is_today_query: bool) -> str:
#     """Handle response when user has overdue tasks"""
    
#     overdue_count = len(task_data["overdue_tasks"])
#     today_count = len(task_data["today_tasks"])
    
#     # Get most critical overdue task (prioritize High priority, then by due date)
#     critical_task = get_most_critical_task(task_data["overdue_tasks"])
    
#     response_parts = [
#         f"🚨 **URGENT ATTENTION REQUIRED**",
#         f"You have **{overdue_count} overdue task{'s' if overdue_count > 1 else ''}** that need immediate attention.",
#         ""
#     ]
    
#     if is_today_query:
#         response_parts.extend([
#             "**❌ Nothing should be worked on 'today' until overdue items are resolved.**",
#             ""
#         ])
    
#     response_parts.extend([
#         "**🎯 IMMEDIATE ACTION REQUIRED:**",
#         f"**Start with: {critical_task['task_name']}**",
#         f"• Originally due: {critical_task['due_date']}",
#         f"• Priority: {critical_task['priority']}",
#         ""
#     ])
    
#     if overdue_count > 1:
#         response_parts.extend([
#             "**📋 Other overdue tasks to tackle next:**"
#         ])
        
#         for task in task_data["overdue_tasks"][1:min(3, overdue_count)]:  # Show next 2
#             response_parts.append(f"• {task['task_name']} (Due: {task['due_date']}, Priority: {task['priority']})")
        
#         if overdue_count > 3:
#             response_parts.append(f"• ...and {overdue_count - 3} more overdue items")
        
#         response_parts.append("")
    
#     if today_count > 0:
#         response_parts.extend([
#             f"**⚠️ Additional Pressure:** You also have {today_count} task{'s' if today_count > 1 else ''} due today.",
#             "Focus on clearing overdue items first to prevent further backlog.",
#             ""
#         ])
    
#     response_parts.extend([
#         "**💡 Recommendation:**",
#         "1. Clear your calendar for the next 2-3 hours",
#         "2. Focus exclusively on the most critical overdue task",
#         "3. Communicate delays to stakeholders if needed",
#         "4. Once caught up, establish better deadline tracking"
#     ])
    
#     return "\n".join(response_parts)

# def handle_today_tasks_response(task_data: Dict[str, Any]) -> str:
#     """Handle response when user has tasks due today (no overdue)"""
    
#     today_count = len(task_data["today_tasks"])
#     critical_task = get_most_critical_task(task_data["today_tasks"])
    
#     response_parts = [
#         f"📅 **TODAY'S FOCUS** ({today_count} task{'s' if today_count > 1 else ''} due)",
#         "",
#         f"**🎯 Start with: {critical_task['task_name']}**",
#         f"• Priority: {critical_task['priority']}",
#         f"• Status: {critical_task['status']}",
#         ""
#     ]
    
#     if today_count > 1:
#         response_parts.extend([
#             "**📋 Complete these today:**"
#         ])
        
#         for i, task in enumerate(task_data["today_tasks"], 1):
#             status_indicator = "🔥" if task['priority'] == "High" else "📝"
#             response_parts.append(f"{i}. {status_indicator} {task['task_name']} (Priority: {task['priority']})")
        
#         response_parts.append("")
    
#     if task_data["upcoming_tasks"]:
#         next_task = task_data["upcoming_tasks"][0]
#         response_parts.extend([
#             "**👀 Coming up next:**",
#             f"• {next_task['task_name']} (Due: {next_task['due_date']}, Priority: {next_task['priority']})",
#             ""
#         ])
    
#     response_parts.extend([
#         "**💡 Today's Strategy:**",
#         "1. Tackle high-priority items during your peak energy hours",
#         "2. Break large tasks into smaller, manageable chunks",
#         "3. Set realistic time estimates and buffer time between tasks"
#     ])
    
#     return "\n".join(response_parts)

# def handle_upcoming_tasks_response(task_data: Dict[str, Any]) -> str:
#     """Handle response when no tasks today but has upcoming tasks"""
    
#     next_task = get_most_critical_task(task_data["upcoming_tasks"])
#     upcoming_count = len(task_data["upcoming_tasks"])
    
#     response_parts = [
#         "✅ **GREAT NEWS!** No tasks due today.",
#         "",
#         f"**🔮 Next priority: {next_task['task_name']}**",
#         f"• Due: {next_task['due_date']}",
#         f"• Priority: {next_task['priority']}",
#         ""
#     ]
    
#     if upcoming_count > 1:
#         response_parts.extend([
#             f"**📋 Upcoming tasks ({upcoming_count} total):**"
#         ])
        
#         for task in task_data["upcoming_tasks"][:3]:  # Show next 3
#             response_parts.append(f"• {task['task_name']} (Due: {task['due_date']}, Priority: {task['priority']})")
        
#         if upcoming_count > 3:
#             response_parts.append(f"• ...and {upcoming_count - 3} more upcoming")
        
#         response_parts.append("")
    
#     response_parts.extend([
#         "**💡 Today's Opportunity:**",
#         "1. **Get ahead**: Start prep work on your next high-priority task",
#         "2. **Plan better**: Review and organize your upcoming workload",
#         "3. **Skill building**: Use free time for professional development",
#         "4. **Communication**: Check in with team members on their progress"
#     ])
    
#     return "\n".join(response_parts)

# def handle_no_tasks_response() -> str:
#     """Handle response when user has no tasks"""
    
#     return """🎉 **EXCELLENT!** You have no pending tasks.

# **💡 Productive ways to use this time:**

# 1. **Strategic Planning**
#    • Review your long-term goals and milestones
#    • Plan upcoming projects and initiatives

# 2. **Professional Development**
#    • Learn new skills relevant to your role
#    • Review industry trends and best practices

# 3. **Team Collaboration**
#    • Check if colleagues need assistance
#    • Contribute to team knowledge sharing

# 4. **Process Improvement**
#    • Document workflows and procedures
#    • Identify areas for optimization

# **🌟 You're in an excellent position to be proactive rather than reactive!**"""

# def get_most_critical_task(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
#     """Get the most critical task based on priority and due date"""
    
#     if not tasks:
#         return None
    
#     # Sort by priority (High > Medium > Low) then by due date
#     priority_order = {"High": 0, "Medium": 1, "Low": 2, "Normal": 1}
    
#     sorted_tasks = sorted(tasks, key=lambda t: (
#         priority_order.get(t.get("priority", "Normal"), 3),
#         t.get("due_date", "9999-12-31")  # Far future for missing dates
#     ))
    
#     return sorted_tasks[0]

# def generate_llm_response(query: str, context: str) -> str:
#     """Fallback to LLM for complex queries"""
    
#     os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
    
#     prompt_template = PromptTemplate.from_template("""
# You are a professional project management assistant. Based on the user's task data, provide specific, actionable recommendations.

# IMPORTANT RULES:
# - If user has overdue tasks, ALWAYS prioritize them over everything else
# - Be direct and professional - avoid generic advice
# - Reference specific task names from their data
# - Provide clear next steps and priorities
# - If no tasks for today, clearly state this and suggest the most important upcoming task

# USER'S CURRENT TASKS AND SCHEDULE:
# {context}

# USER QUESTION: {query}

# Provide a professional, specific response focusing on their actual tasks:
# """)

#     try:
#         llm = OllamaLLM(model="llama3")
#         final_prompt = prompt_template.format(
#             context=context or "No task data available",
#             query=query
#         )
        
#         result = llm.invoke(final_prompt)
#         return result.strip()
        
#     except Exception as e:
#         print(f"❌ LLM call failed: {e}")
#         return "⚠️ Unable to analyze your tasks right now. Please try again in a moment."

# # Keep the existing interpret_query function unchanged
# def interpret_query(query: str, hints: Dict[str, Any] | None = None) -> Dict[str, Any]:
#     """Enhanced query interpretation with better user name resolution"""
#     hints = hints or {}
#     names = hints.get("team_member_names", [])
#     me = hints.get("current_user_name", "")

#     # Enhanced user detection
#     query_lower = query.lower()
#     target_user = {"type": "me"}
    
#     # Check for specific user names in query
#     for name in names:
#         if name.lower() in query_lower:
#             target_user = {"type": "name", "value": name}
#             break
    
#     # Check for common name patterns
#     name_patterns = [
#         r'\b(\w+)\s+task',
#         r'(\w+)\'s\s+task',
#         r'for\s+(\w+)',
#         r'about\s+(\w+)'
#     ]
    
#     for pattern in name_patterns:
#         match = re.search(pattern, query_lower)
#         if match:
#             potential_name = match.group(1).title()
#             # Find closest match in team names
#             for name in names:
#                 if potential_name.lower() in name.lower() or name.lower().startswith(potential_name.lower()):
#                     target_user = {"type": "name", "value": name}
#                     break

#     # Determine action based on query content
#     action = "general_question"
#     if any(word in query_lower for word in ["task", "complete", "work on", "priority", "due"]):
#         action = "query_tasks"
#     elif any(word in query_lower for word in ["kanban", "board", "column"]):
#         action = "query_kanban"
#     elif any(word in query_lower for word in ["message", "chat", "conversation"]):
#         action = "query_messages"
    
#     # Time and priority detection
#     due_bucket = None
#     if "today" in query_lower:
#         due_bucket = "today"
#     elif "overdue" in query_lower:
#         due_bucket = "overdue"
#     elif "tomorrow" in query_lower:
#         due_bucket = "tomorrow"
    
#     return {
#         "action": action,
#         "target_user": target_user,
#         "time": {
#             "natural": query,
#             "start": None,
#             "end": None
#         },
#         "filters": {
#             "priority": None,
#             "status": None,
#             "due_bucket": due_bucket,
#             "board": None,
#             "limit": None,
#             "sort": "due_date_asc"
#         }
#     }