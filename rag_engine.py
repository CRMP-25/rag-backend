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
    """Parse the user context to extract structured task information"""
    
    parsed_data = {
        "overdue_tasks": [],
        "today_tasks": [],
        "upcoming_tasks": [],
        "total_tasks": 0,
        "has_urgent_items": False,
        "messages": [],  # New: parsed messages
        "message_stats": {}  # New: message statistics
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
    
    # Parse sections
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
        elif "RECENT MESSAGES:" in line:
            current_section = "messages"
        elif line.startswith("•"):
            if current_section == "messages":
                # Parse message line: • From John: Hello there (2025-01-15 14:30)
                message_info = parse_message_line(line, today)
                if message_info:
                    parsed_data["messages"].append(message_info)
            else:
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
    
    # Calculate message statistics
    parsed_data["message_stats"] = calculate_message_stats(parsed_data["messages"], today)
    
    return parsed_data

def parse_message_line(line: str, today_date) -> Dict[str, Any]:
    """Parse individual message line to extract message information"""
    
    # Pattern: • From SenderName: Message content (timestamp)
    pattern = r"•\s*From\s+([^:]+):\s*([^(]+)\s*\(([^)]+)\)"
    
    match = re.search(pattern, line)
    if not match:
        # Try alternative pattern without "From"
        pattern2 = r"•\s*([^:]+):\s*([^(]+)\s*\(([^)]+)\)"
        match = re.search(pattern2, line)
        
    if not match:
        return None
    
    sender_name = match.group(1).strip()
    message_content = match.group(2).strip()
    timestamp_str = match.group(3).strip()
    
    # Parse timestamp
    try:
        # Try different timestamp formats
        timestamp = None
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%m/%d/%Y %H:%M"]:
            try:
                timestamp = datetime.strptime(timestamp_str, fmt)
                break
            except ValueError:
                continue
        
        if not timestamp:
            timestamp = datetime.now()
            
    except Exception:
        timestamp = datetime.now()
    
    # Calculate recency
    time_diff = datetime.now() - timestamp
    
    if time_diff.days == 0:
        recency = "today"
    elif time_diff.days == 1:
        recency = "yesterday"
    elif time_diff.days <= 7:
        recency = "this_week"
    else:
        recency = "older"
    
    return {
        "sender_name": sender_name,
        "message_content": message_content,
        "timestamp": timestamp,
        "timestamp_str": timestamp_str,
        "recency": recency
    }

def calculate_message_stats(messages: List[Dict], today_date) -> Dict[str, Any]:
    """Calculate message statistics"""
    
    stats = {
        "total_messages": len(messages),
        "today_messages": 0,
        "yesterday_messages": 0,
        "this_week_messages": 0,
        "sender_counts": {},
        "recent_senders": []
    }
    
    today_senders = set()
    
    for msg in messages:
        sender = msg["sender_name"]
        recency = msg["recency"]
        
        # Count by sender
        if sender not in stats["sender_counts"]:
            stats["sender_counts"][sender] = 0
        stats["sender_counts"][sender] += 1
        
        # Count by time period
        if recency == "today":
            stats["today_messages"] += 1
            today_senders.add(sender)
        elif recency == "yesterday":
            stats["yesterday_messages"] += 1
        elif recency == "this_week":
            stats["this_week_messages"] += 1
    
    stats["recent_senders"] = list(today_senders)
    
    return stats

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

def get_rag_response(query: str, user_context: str = ""):
    """Enhanced RAG response with message and task analysis"""
    print("🚨 USING ENHANCED RAG ENGINE WITH MESSAGE SUPPORT")
    print(f"\n🔍 Incoming query: {query}")
    print(f"\n📊 User context length: {len(user_context)} characters")

    if not wait_for_ollama():
        return "⚠️ AI backend is temporarily unavailable. Please try again in a moment."

    # Parse the user context to understand both tasks and messages
    parsed_data = parse_task_context(user_context)
    
    print(f"📋 Parsed task data: {parsed_data['total_tasks']} total tasks")
    print(f"💬 Parsed message data: {parsed_data['message_stats']['total_messages']} total messages")
    print(f"📧 Today's messages: {parsed_data['message_stats']['today_messages']}")
    
    # Determine query type
    query_type = classify_query_type(query)
    print(f"🎯 Query type classified as: {query_type}")
    
    # Generate appropriate response based on query type
    if query_type == "message_query":
        return generate_message_response(query, parsed_data, user_context)
    elif query_type == "task_query":
        return generate_professional_response(query, parsed_data, user_context)
    else:
        return generate_mixed_response(query, parsed_data, user_context)

def classify_query_type(query: str) -> str:
    """Classify the type of query to determine appropriate response"""
    
    query_lower = query.lower()
    
    # Message-related keywords
    message_keywords = [
        "message", "messages", "chat", "said", "told", "replied", 
        "conversation", "spoke", "mentioned", "contacted", "reached out",
        "sent", "received", "hear from", "got any", "any word from"
    ]
    
    # Task-related keywords
    task_keywords = [
        "task", "tasks", "work", "complete", "finish", "priority", 
        "due", "deadline", "project", "assignment", "todo", "do today"
    ]
    
    # Check for message queries
    message_score = sum(1 for keyword in message_keywords if keyword in query_lower)
    task_score = sum(1 for keyword in task_keywords if keyword in query_lower)
    
    # Specific message query patterns
    message_patterns = [
        r"did.*get.*message",
        r"any.*message.*from",
        r"message.*from.*today",
        r"hear.*from",
        r"said.*anything",
        r"contact.*me"
    ]
    
    for pattern in message_patterns:
        if re.search(pattern, query_lower):
            return "message_query"
    
    # Classify based on keyword scores
    if message_score > task_score and message_score > 0:
        return "message_query"
    elif task_score > message_score and task_score > 0:
        return "task_query"
    else:
        return "general_query"

def generate_message_response(query: str, parsed_data: Dict[str, Any], context: str) -> str:
    """Generate response for message-related queries"""
    
    query_lower = query.lower()
    messages = parsed_data["messages"]
    stats = parsed_data["message_stats"]
    
    # Extract specific person name from query if mentioned
    mentioned_person = extract_person_from_query(query)
    
    # Handle different types of message queries
    if "today" in query_lower:
        return handle_today_messages_query(messages, stats, mentioned_person)
    elif "yesterday" in query_lower:
        return handle_yesterday_messages_query(messages, stats, mentioned_person)
    elif mentioned_person:
        return handle_person_specific_messages(messages, mentioned_person)
    elif "any" in query_lower and "message" in query_lower:
        return handle_general_message_check(messages, stats)
    else:
        return handle_general_message_query(messages, stats, query)

def extract_person_from_query(query: str) -> str:
    """Extract person name from query"""
    
    query_lower = query.lower()
    
    # Common patterns for person mentions
    patterns = [
        r"from\s+(\w+)",
        r"message.*from\s+(\w+)",
        r"hear.*from\s+(\w+)",
        r"(\w+)\s+message",
        r"did\s+(\w+)\s+",
        r"has\s+(\w+)\s+"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, query_lower)
        if match:
            name = match.group(1).title()
            # Filter out common words
            if name.lower() not in ["any", "get", "got", "have", "has", "did", "the", "a", "an"]:
                return name
    
    return None

def handle_today_messages_query(messages: List[Dict], stats: Dict, person: str = None) -> str:
    """Handle queries about today's messages"""
    
    today_messages = [msg for msg in messages if msg["recency"] == "today"]
    
    if person:
        person_messages = [msg for msg in today_messages if person.lower() in msg["sender_name"].lower()]
        
        if person_messages:
            response_parts = [
                f"📧 **Yes, you received {len(person_messages)} message{'s' if len(person_messages) > 1 else ''} from {person} today:**",
                ""
            ]
            
            for msg in person_messages[-3:]:  # Show last 3 messages
                time_str = msg["timestamp"].strftime("%H:%M")
                response_parts.append(f"🕐 **{time_str}:** {msg['message_content']}")
            
            if len(person_messages) > 3:
                response_parts.append(f"... and {len(person_messages) - 3} more messages")
                
        else:
            response_parts = [
                f"❌ **No messages from {person} today.**"
            ]
            
            if today_messages:
                other_senders = list(set([msg["sender_name"] for msg in today_messages]))
                response_parts.extend([
                    "",
                    f"📬 You did receive {len(today_messages)} message{'s' if len(today_messages) > 1 else ''} today from: {', '.join(other_senders)}"
                ])
    else:
        if today_messages:
            sender_counts = {}
            for msg in today_messages:
                sender = msg["sender_name"]
                sender_counts[sender] = sender_counts.get(sender, 0) + 1
            
            response_parts = [
                f"📧 **You received {len(today_messages)} message{'s' if len(today_messages) > 1 else ''} today:**",
                ""
            ]
            
            for sender, count in sender_counts.items():
                recent_msg = next(msg for msg in reversed(today_messages) if msg["sender_name"] == sender)
                time_str = recent_msg["timestamp"].strftime("%H:%M")
                response_parts.append(f"👤 **{sender}** ({count} message{'s' if count > 1 else ''})")
                response_parts.append(f"   Latest ({time_str}): {recent_msg['message_content'][:100]}...")
                response_parts.append("")
        else:
            response_parts = [
                "❌ **No messages received today.**",
                "",
                "📭 Your inbox is empty for today. Check back later or review yesterday's messages."
            ]
    
    return "\n".join(response_parts)

def handle_yesterday_messages_query(messages: List[Dict], stats: Dict, person: str = None) -> str:
    """Handle queries about yesterday's messages"""
    
    yesterday_messages = [msg for msg in messages if msg["recency"] == "yesterday"]
    
    if person:
        person_messages = [msg for msg in yesterday_messages if person.lower() in msg["sender_name"].lower()]
        
        if person_messages:
            response_parts = [
                f"📧 **Yes, you received {len(person_messages)} message{'s' if len(person_messages) > 1 else ''} from {person} yesterday:**",
                ""
            ]
            
            for msg in person_messages[-2:]:  # Show last 2 messages
                time_str = msg["timestamp"].strftime("%H:%M")
                response_parts.append(f"🕐 **{time_str}:** {msg['message_content']}")
                
        else:
            response_parts = [
                f"❌ **No messages from {person} yesterday.**"
            ]
    else:
        if yesterday_messages:
            response_parts = [
                f"📧 **You received {len(yesterday_messages)} message{'s' if len(yesterday_messages) > 1 else ''} yesterday.**"
            ]
        else:
            response_parts = [
                "❌ **No messages received yesterday.**"
            ]
    
    return "\n".join(response_parts)

def handle_person_specific_messages(messages: List[Dict], person: str) -> str:
    """Handle queries about messages from a specific person"""
    
    person_messages = [msg for msg in messages if person.lower() in msg["sender_name"].lower()]
    
    if person_messages:
        # Group by recency
        today_msgs = [msg for msg in person_messages if msg["recency"] == "today"]
        yesterday_msgs = [msg for msg in person_messages if msg["recency"] == "yesterday"]
        this_week_msgs = [msg for msg in person_messages if msg["recency"] == "this_week"]
        
        response_parts = [
            f"📧 **Message history with {person}:**",
            ""
        ]
        
        if today_msgs:
            response_parts.append(f"**Today ({len(today_msgs)} message{'s' if len(today_msgs) > 1 else ''}):**")
            for msg in today_msgs[-2:]:  # Show last 2 from today
                time_str = msg["timestamp"].strftime("%H:%M")
                response_parts.append(f"🕐 {time_str}: {msg['message_content']}")
            response_parts.append("")
        
        if yesterday_msgs:
            response_parts.append(f"**Yesterday ({len(yesterday_msgs)} message{'s' if len(yesterday_msgs) > 1 else ''}):**")
            latest_yesterday = yesterday_msgs[-1]
            time_str = latest_yesterday["timestamp"].strftime("%H:%M")
            response_parts.append(f"🕐 {time_str}: {latest_yesterday['message_content']}")
            response_parts.append("")
        
        if this_week_msgs:
            response_parts.append(f"**This week:** {len(this_week_msgs)} more message{'s' if len(this_week_msgs) > 1 else ''}")
    else:
        response_parts = [
            f"❌ **No recent messages from {person}.**",
            "",
            "🔍 Try checking with a different name spelling or look at your full message history."
        ]
    
    return "\n".join(response_parts)

def handle_general_message_check(messages: List[Dict], stats: Dict) -> str:
    """Handle general 'any messages?' type queries"""
    
    if stats["total_messages"] == 0:
        return "❌ **No recent messages found.**\n\n📭 Your inbox appears empty. Check your message settings or try refreshing."
    
    response_parts = [
        f"📧 **Message Summary ({stats['total_messages']} total messages):**",
        ""
    ]
    
    if stats["today_messages"] > 0:
        response_parts.append(f"**Today:** {stats['today_messages']} message{'s' if stats['today_messages'] > 1 else ''}")
        if stats["recent_senders"]:
            response_parts.append(f"**From:** {', '.join(stats['recent_senders'])}")
        response_parts.append("")
    
    if stats["yesterday_messages"] > 0:
        response_parts.append(f"**Yesterday:** {stats['yesterday_messages']} message{'s' if stats['yesterday_messages'] > 1 else ''}")
        response_parts.append("")
    
    if stats["this_week_messages"] > 0:
        response_parts.append(f"**This week:** {stats['this_week_messages']} message{'s' if stats['this_week_messages'] > 1 else ''}")
        response_parts.append("")
    
    # Show top message senders
    if stats["sender_counts"]:
        top_senders = sorted(stats["sender_counts"].items(), key=lambda x: x[1], reverse=True)[:3]
        response_parts.append("**Most active contacts:**")
        for sender, count in top_senders:
            response_parts.append(f"• {sender}: {count} message{'s' if count > 1 else ''}")
    
    return "\n".join(response_parts)

def handle_general_message_query(messages: List[Dict], stats: Dict, query: str) -> str:
    """Handle other general message queries"""
    
    if stats["total_messages"] == 0:
        return "❌ **No recent messages found.**\n\nTry asking about tasks instead or check your message settings."
    
    # Use LLM for complex message queries
    return generate_llm_response(query, f"Messages: {len(messages)} total. Recent activity: {stats}")

# Keep existing task-related functions unchanged
def generate_professional_response(query: str, task_data: Dict[str, Any], context: str) -> str:
    """Generate a professional, actionable response based on task analysis"""
    
    query_lower = query.lower()
    is_today_query = any(word in query_lower for word in ["today", "now", "current"])
    is_priority_query = any(word in query_lower for word in ["priority", "important", "urgent", "should", "recommend"])
    
    # Case 1: User has overdue tasks - HIGHEST PRIORITY
    if task_data["overdue_tasks"]:
        return handle_overdue_tasks_response(task_data, is_today_query)
    
    # Case 2: User has tasks due today
    if task_data["today_tasks"]:
        return handle_today_tasks_response(task_data)
    
    # Case 3: No tasks for today but has upcoming tasks
    if task_data["upcoming_tasks"]:
        return handle_upcoming_tasks_response(task_data)
    
    # Case 4: No tasks at all
    if task_data["total_tasks"] == 0:
        return handle_no_tasks_response()
    
    # Fallback: Use LLM for complex queries
    return generate_llm_response(query, context)

def generate_mixed_response(query: str, parsed_data: Dict[str, Any], context: str) -> str:
    """Generate response for queries that might involve both tasks and messages"""
    
    return generate_llm_response(query, context)

# Keep all existing task response functions unchanged...
def handle_overdue_tasks_response(task_data: Dict[str, Any], is_today_query: bool) -> str:
    """Handle response when user has overdue tasks"""
    
    overdue_count = len(task_data["overdue_tasks"])
    today_count = len(task_data["today_tasks"])
    
    # Get most critical overdue task (prioritize High priority, then by due date)
    critical_task = get_most_critical_task(task_data["overdue_tasks"])
    
    response_parts = [
        f"🚨 **URGENT ATTENTION REQUIRED**",
        f"You have **{overdue_count} overdue task{'s' if overdue_count > 1 else ''}** that need immediate attention.",
        ""
    ]
    
    if is_today_query:
        response_parts.extend([
            "**❌ Nothing should be worked on 'today' until overdue items are resolved.**",
            ""
        ])
    
    response_parts.extend([
        "**🎯 IMMEDIATE ACTION REQUIRED:**",
        f"**Start with: {critical_task['task_name']}**",
        f"• Originally due: {critical_task['due_date']}",
        f"• Priority: {critical_task['priority']}",
        ""
    ])
    
    if overdue_count > 1:
        response_parts.extend([
            "**📋 Other overdue tasks to tackle next:**"
        ])
        
        for task in task_data["overdue_tasks"][1:min(3, overdue_count)]:  # Show next 2
            response_parts.append(f"• {task['task_name']} (Due: {task['due_date']}, Priority: {task['priority']})")
        
        if overdue_count > 3:
            response_parts.append(f"• ...and {overdue_count - 3} more overdue items")
        
        response_parts.append("")
    
    if today_count > 0:
        response_parts.extend([
            f"**⚠️ Additional Pressure:** You also have {today_count} task{'s' if today_count > 1 else ''} due today.",
            "Focus on clearing overdue items first to prevent further backlog.",
            ""
        ])
    
    response_parts.extend([
        "**💡 Recommendation:**",
        "1. Clear your calendar for the next 2-3 hours",
        "2. Focus exclusively on the most critical overdue task",
        "3. Communicate delays to stakeholders if needed",
        "4. Once caught up, establish better deadline tracking"
    ])
    
    return "\n".join(response_parts)

# ... (keep all other existing functions unchanged)

def get_most_critical_task(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Get the most critical task based on priority and due date"""
    
    if not tasks:
        return None
    
    # Sort by priority (High > Medium > Low) then by due date
    priority_order = {"High": 0, "Medium": 1, "Low": 2, "Normal": 1}
    
    sorted_tasks = sorted(tasks, key=lambda t: (
        priority_order.get(t.get("priority", "Normal"), 3),
        t.get("due_date", "9999-12-31")  # Far future for missing dates
    ))
    
    return sorted_tasks[0]

def generate_llm_response(query: str, context: str) -> str:
    """Fallback to LLM for complex queries"""
    
    os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
    
    prompt_template = PromptTemplate.from_template("""
You are a professional project management assistant with access to both task and message data. 

Based on the user's data, provide specific, actionable responses.

IMPORTANT RULES:
- For message queries: Answer directly about messages, be specific about senders and timing
- For task queries: Prioritize overdue tasks, be direct and professional
- Reference specific names, dates, and content from their data
- If no relevant data exists, state this clearly

USER'S CURRENT DATA (TASKS AND MESSAGES):
{context}

USER QUESTION: {query}

Provide a professional, specific response focusing on their actual data:
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
        return "⚠️ Unable to analyze your data right now. Please try again in a moment."

# Keep the existing interpret_query function unchanged
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
    if any(word in query_lower for word in ["message", "messages", "chat", "said", "told"]):
        action = "query_messages"
    elif any(word in query_lower for word in ["task", "complete", "work on", "priority", "due"]):
        action = "query_tasks"
    elif any(word in query_lower for word in ["kanban", "board", "column"]):
        action = "query_kanban"
    
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