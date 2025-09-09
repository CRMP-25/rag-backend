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

def parse_message_context(user_context: str) -> Dict[str, Any]:
    """Enhanced parsing of user context to extract both task and message information"""
    
    parsed_data = {
        "overdue_tasks": [],
        "today_tasks": [],
        "upcoming_tasks": [],
        "total_tasks": 0,
        "has_urgent_items": False,
        "messages": [],
        "message_stats": {},
        "team_members": []
    }
    
    if not user_context.strip():
        return parsed_data
    
    # Extract today's date from context
    today_match = re.search(r"📅 TODAY'S DATE: ([^\n]+)", user_context)
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
        elif "TEAM MESSAGES:" in line:
            current_section = "messages"
        elif "TEAM MEMBERS:" in line:
            # Extract team member names
            members_text = line.replace("👥 TEAM MEMBERS:", "").strip()
            parsed_data["team_members"] = [name.strip() for name in members_text.split(",") if name.strip()]
        elif line.startswith("•"):
            if current_section == "messages":
                # Enhanced message parsing
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
    """Enhanced message line parsing with better name extraction"""
    
    # Multiple patterns to catch different message formats
    patterns = [
        r"From\s+([^(]+?)\s*\((\d+)\s*messages?\).*?Latest\s*\(([^)]+)\):\s*(.+)",  # From Name (X messages) Latest (time): message
        r"From\s+([^:]+):\s*([^(]+)\s*\(([^)]+)\)",  # From Name: message (time)
        r"•\s*From\s+([^:]+):\s*(.+)",  # • From Name: message
        r"•\s*([^:]+?):\s*(.+)",  # • Name: message (simple format)
    ]
    
    for pattern in patterns:
        match = re.search(pattern, line, re.IGNORECASE)
        if match:
            if len(match.groups()) == 4:  # Pattern with message count
                sender_name = match.group(1).strip()
                message_count = int(match.group(2)) if match.group(2).isdigit() else 1
                timestamp_str = match.group(3).strip()
                message_content = match.group(4).strip()
            else:  # Simple pattern
                sender_name = match.group(1).strip()
                message_content = match.group(2).strip()
                timestamp_str = match.group(3).strip() if len(match.groups()) >= 3 else "recent"
                message_count = 1
            
            # Parse timestamp
            timestamp = parse_timestamp(timestamp_str)
            
            # Calculate recency
            recency = calculate_recency(timestamp, today_date)
            
            return {
                "sender_name": sender_name,
                "message_content": message_content,
                "timestamp": timestamp,
                "timestamp_str": timestamp_str,
                "recency": recency,
                "message_count": message_count
            }
    
    return None

def parse_timestamp(timestamp_str: str) -> datetime:
    """Parse various timestamp formats"""
    
    # Common timestamp formats
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M", 
        "%Y-%m-%d",
        "%m/%d/%Y %H:%M",
        "%H:%M",  # Time only
    ]
    
    for fmt in formats:
        try:
            if fmt == "%H:%M":
                # Assume today for time-only format
                today = datetime.now().date()
                time_obj = datetime.strptime(timestamp_str, fmt).time()
                return datetime.combine(today, time_obj)
            else:
                return datetime.strptime(timestamp_str, fmt)
        except ValueError:
            continue
    
    # Fallback to current time
    return datetime.now()

def calculate_recency(timestamp: datetime, reference_date) -> str:
    """Calculate message recency relative to reference date"""
    
    if isinstance(reference_date, str):
        reference_date = datetime.strptime(reference_date, "%Y-%m-%d").date()
    elif hasattr(reference_date, 'date'):
        reference_date = reference_date.date()
    
    message_date = timestamp.date()
    
    if message_date == reference_date:
        return "today"
    elif message_date == reference_date - timedelta(days=1):
        return "yesterday"
    elif (reference_date - message_date).days <= 7:
        return "this_week"
    else:
        return "older"

def calculate_message_stats(messages: List[Dict], today_date) -> Dict[str, Any]:
    """Calculate comprehensive message statistics"""
    
    stats = {
        "total_messages": len(messages),
        "today_messages": 0,
        "yesterday_messages": 0,
        "this_week_messages": 0,
        "sender_counts": {},
        "recent_senders": [],
        "today_senders": []
    }
    
    today_senders = set()
    all_recent_senders = set()
    
    for msg in messages:
        sender = msg["sender_name"]
        recency = msg["recency"]
        
        # Count by sender
        if sender not in stats["sender_counts"]:
            stats["sender_counts"][sender] = 0
        stats["sender_counts"][sender] += msg.get("message_count", 1)
        
        all_recent_senders.add(sender)
        
        # Count by time period
        if recency == "today":
            stats["today_messages"] += msg.get("message_count", 1)
            today_senders.add(sender)
        elif recency == "yesterday":
            stats["yesterday_messages"] += msg.get("message_count", 1)
        elif recency == "this_week":
            stats["this_week_messages"] += msg.get("message_count", 1)
    
    stats["today_senders"] = list(today_senders)
    stats["recent_senders"] = list(all_recent_senders)
    
    return stats

def parse_task_line(line: str, today_date) -> Dict[str, Any]:
    """Parse individual task line to extract task information"""
    
    # Pattern: • [URGENCY] Task Name (Priority: X, Due: Y)
    pattern = r"•\s*\[([^\]]+)\]\s*([^(]+)\s*\(Priority:\s*([^,]+),\s*(?:Status:\s*([^,]+),\s*)?Due:\s*([^)]+)\)"
    
    match = re.search(pattern, line)
    if not match:
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
    """Enhanced RAG response with superior message and task analysis"""
    print("🔥 ENHANCED RAG ENGINE WITH ADVANCED MESSAGE SUPPORT")
    print(f"\n🔍 Incoming query: {query}")
    print(f"\n📊 User context length: {len(user_context)} characters")

    if not wait_for_ollama():
        return "⚠️ AI backend is temporarily unavailable. Please try again in a moment."

    # Parse the user context to understand both tasks and messages
    parsed_data = parse_message_context(user_context)
    
    print(f"📋 Parsed task data: {parsed_data['total_tasks']} total tasks")
    print(f"💬 Parsed message data: {parsed_data['message_stats']['total_messages']} total messages")
    print(f"📧 Today's messages: {parsed_data['message_stats']['today_messages']}")
    print(f"👥 Team members: {len(parsed_data['team_members'])}")
    
    # Determine query type with enhanced classification
    query_type = classify_query_type(query, parsed_data['team_members'])
    print(f"🎯 Query type classified as: {query_type}")
    
    # Generate appropriate response based on query type
    if query_type == "message_query":
        return generate_message_response(query, parsed_data)
    elif query_type == "task_query":
        return generate_task_response(query, parsed_data)
    else:
        return generate_mixed_response(query, parsed_data, user_context)

def classify_query_type(query: str, team_members: List[str] = None) -> str:
    """Enhanced query classification with team member awareness"""
    
    query_lower = query.lower()
    team_members = team_members or []
    
    # Message-related keywords - EXPANDED LIST
    message_keywords = [
        "message", "messages", "chat", "said", "told", "replied", 
        "conversation", "spoke", "mentioned", "contacted", "reached out",
        "sent", "received", "hear from", "got any", "any word from",
        "text", "texted", "communicate", "communication", "msg", "msgs"
    ]
    
    # Task-related keywords
    task_keywords = [
        "task", "tasks", "work", "complete", "finish", "priority", 
        "due", "deadline", "project", "assignment", "todo", "do today",
        "overdue", "schedule", "kanban", "start", "begin", "working on"
    ]
    
    # Check for team member names in query - ENHANCED MATCHING
    mentions_team_member = False
    mentioned_member = None
    for member in team_members:
        member_lower = member.lower()
        first_name = member.split()[0].lower()
        
        if (member_lower in query_lower or 
            first_name in query_lower or
            f"from {first_name}" in query_lower or
            f"from {member_lower}" in query_lower):
            mentions_team_member = True
            mentioned_member = member
            break
    
    print(f"🔍 Query analysis:")
    print(f"  - Mentions team member: {mentions_team_member} ({mentioned_member})")
    print(f"  - Message keywords found: {[k for k in message_keywords if k in query_lower]}")
    print(f"  - Task keywords found: {[k for k in task_keywords if k in query_lower]}")
    
    # Enhanced message query patterns - MORE COMPREHENSIVE
    message_patterns = [
        r"did.*get.*message",
        r"any.*message.*from",
        r"message.*from.*today",
        r"hear.*from",
        r"said.*anything",
        r"contact.*me",
        r"anyone.*message",
        r"team.*message",
        r"word.*from",
        r"got.*any.*message",
        r"receive.*message",
        r"message.*today",
        r"chat.*with",
        r"talk.*to",
        r"spoke.*with"
    ]
    
    # Strong indicators for message queries
    for pattern in message_patterns:
        if re.search(pattern, query_lower):
            print(f"✅ Message pattern matched: {pattern}")
            return "message_query"
    
    # If mentions team member + any communication terms, it's likely a message query
    if mentions_team_member and any(keyword in query_lower for keyword in message_keywords):
        print(f"✅ Team member + message keyword = message_query")
        return "message_query"
    
    # Strong task indicators
    task_patterns = [
        r"what.*should.*do",
        r"what.*should.*complete",
        r"what.*should.*work",
        r"what.*should.*start",
        r"task.*today",
        r"work.*today",
        r"complete.*today",
        r"priority.*today"
    ]
    
    for pattern in task_patterns:
        if re.search(pattern, query_lower):
            print(f"✅ Task pattern matched: {pattern}")
            return "task_query"
    
    # Count keyword scores
    message_score = sum(1 for keyword in message_keywords if keyword in query_lower)
    task_score = sum(1 for keyword in task_keywords if keyword in query_lower)
    
    print(f"📊 Scores - Messages: {message_score}, Tasks: {task_score}")
    
    # Final classification with bias toward message queries when ambiguous
    if message_score > 0 and message_score >= task_score:
        return "message_query"
    elif task_score > message_score and task_score > 0:
        return "task_query"
    else:
        # Default based on context clues
        if any(word in query_lower for word in ["today", "now", "should", "complete", "do"]):
            return "task_query"
        return "general_query"

def generate_message_response(query: str, parsed_data: Dict[str, Any]) -> str:
    """Generate comprehensive response for message-related queries"""
    
    query_lower = query.lower()
    messages = parsed_data["messages"]
    stats = parsed_data["message_stats"]
    team_members = parsed_data["team_members"]
    
    print(f"🔍 Processing message query: {query}")
    print(f"💬 Available message data: {len(messages)} messages")
    print(f"📊 Message stats: {stats}")
    
    # Extract specific person name from query
    mentioned_person = extract_person_from_query(query, team_members)
    print(f"👤 Mentioned person: {mentioned_person}")
    
    # Handle different types of message queries
    if "today" in query_lower:
        return handle_today_messages_query(messages, stats, mentioned_person)
    elif "yesterday" in query_lower:
        return handle_yesterday_messages_query(messages, stats, mentioned_person)
    elif mentioned_person:
        return handle_person_specific_messages(messages, mentioned_person, stats)
    elif any(word in query_lower for word in ["any", "anyone", "team"]) and "message" in query_lower:
        return handle_general_message_check(messages, stats)
    else:
        return handle_general_message_query(messages, stats, query)

def extract_person_from_query(query: str, team_members: List[str]) -> str:
    """Enhanced person name extraction with team member matching"""
    
    query_lower = query.lower()
    
    # First check for exact team member matches
    for member in team_members:
        member_lower = member.lower()
        first_name = member.split()[0].lower()
        
        # Check for full name or first name
        if member_lower in query_lower or first_name in query_lower:
            return member
    
    # Fallback to pattern-based extraction
    patterns = [
        r"from\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)",
        r"message.*from\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)",
        r"hear.*from\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)",
        r"([A-Za-z]+)\s+message",
        r"did\s+([A-Za-z]+)\s+",
        r"has\s+([A-Za-z]+)\s+"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, query_lower)
        if match:
            name = match.group(1).title()
            # Filter out common words
            if name.lower() not in ["any", "get", "got", "have", "has", "did", "the", "a", "an", "me", "you"]:
                # Try to match with team members
                for member in team_members:
                    if name.lower() in member.lower():
                        return member
                return name
    
    return None

def handle_today_messages_query(messages: List[Dict], stats: Dict, person: str = None) -> str:
    """Handle queries about today's messages"""
    
    today_messages = [msg for msg in messages if msg["recency"] == "today"]
    
    if person:
        person_messages = []
        for msg in today_messages:
            if person.lower() in msg["sender_name"].lower():
                person_messages.append(msg)
        
        if person_messages:
            total_count = sum(msg.get("message_count", 1) for msg in person_messages)
            response_parts = [
                f"✅ **Yes, you received {total_count} message{'s' if total_count > 1 else ''} from {person} today:**",
                ""
            ]
            
            for msg in person_messages[:3]:  # Show first 3 message entries
                time_str = msg["timestamp"].strftime("%H:%M")
                count_str = f"({msg.get('message_count', 1)} messages) " if msg.get('message_count', 1) > 1 else ""
                response_parts.append(f"🕒 **{time_str}:** {count_str}{msg['message_content']}")
            
            if len(person_messages) > 3:
                response_parts.append(f"... and {len(person_messages) - 3} more message entries")
                
        else:
            response_parts = [
                f"❌ **No messages from {person} today.**"
            ]
            
            if today_messages:
                other_senders = list(set([msg["sender_name"] for msg in today_messages]))
                total_today = sum(msg.get("message_count", 1) for msg in today_messages)
                response_parts.extend([
                    "",
                    f"📬 You did receive {total_today} message{'s' if total_today > 1 else ''} today from: {', '.join(other_senders)}"
                ])
    else:
        if today_messages:
            sender_counts = {}
            for msg in today_messages:
                sender = msg["sender_name"]
                count = msg.get("message_count", 1)
                sender_counts[sender] = sender_counts.get(sender, 0) + count
            
            total_today = sum(sender_counts.values())
            response_parts = [
                f"📧 **You received {total_today} message{'s' if total_today > 1 else ''} today:**",
                ""
            ]
            
            for sender, count in sender_counts.items():
                # Find most recent message from this sender
                sender_messages = [msg for msg in today_messages if msg["sender_name"] == sender]
                recent_msg = max(sender_messages, key=lambda x: x["timestamp"])
                time_str = recent_msg["timestamp"].strftime("%H:%M")
                
                response_parts.append(f"👤 **{sender}** ({count} message{'s' if count > 1 else ''})")
                response_parts.append(f"   Latest ({time_str}): {recent_msg['message_content'][:100]}{'...' if len(recent_msg['message_content']) > 100 else ''}")
                response_parts.append("")
        else:
            response_parts = [
                "❌ **No messages received today.**",
                "",
                "🔭 Your inbox is empty for today. Check back later or review yesterday's messages."
            ]
    
    return "\n".join(response_parts)

def handle_yesterday_messages_query(messages: List[Dict], stats: Dict, person: str = None) -> str:
    """Handle queries about yesterday's messages"""
    
    yesterday_messages = [msg for msg in messages if msg["recency"] == "yesterday"]
    
    if person:
        person_messages = []
        for msg in yesterday_messages:
            if person.lower() in msg["sender_name"].lower():
                person_messages.append(msg)
        
        if person_messages:
            total_count = sum(msg.get("message_count", 1) for msg in person_messages)
            response_parts = [
                f"✅ **Yes, you received {total_count} message{'s' if total_count > 1 else ''} from {person} yesterday:**",
                ""
            ]
            
            for msg in person_messages[:2]:  # Show last 2 messages
                time_str = msg["timestamp"].strftime("%H:%M")
                response_parts.append(f"🕒 **{time_str}:** {msg['message_content']}")
                
        else:
            response_parts = [
                f"❌ **No messages from {person} yesterday.**"
            ]
    else:
        if yesterday_messages:
            total_yesterday = sum(msg.get("message_count", 1) for msg in yesterday_messages)
            response_parts = [
                f"📧 **You received {total_yesterday} message{'s' if total_yesterday > 1 else ''} yesterday.**"
            ]
        else:
            response_parts = [
                "❌ **No messages received yesterday.**"
            ]
    
    return "\n".join(response_parts)

def handle_person_specific_messages(messages: List[Dict], person: str, stats: Dict) -> str:
    """Handle queries about messages from a specific person"""
    
    person_messages = []
    for msg in messages:
        if person.lower() in msg["sender_name"].lower():
            person_messages.append(msg)
    
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
            today_total = sum(msg.get("message_count", 1) for msg in today_msgs)
            response_parts.append(f"**Today ({today_total} message{'s' if today_total > 1 else ''}):**")
            for msg in today_msgs[:2]:  # Show last 2 from today
                time_str = msg["timestamp"].strftime("%H:%M")
                count_str = f"({msg.get('message_count', 1)} msgs) " if msg.get('message_count', 1) > 1 else ""
                response_parts.append(f"🕒 {time_str}: {count_str}{msg['message_content']}")
            response_parts.append("")
        
        if yesterday_msgs:
            yesterday_total = sum(msg.get("message_count", 1) for msg in yesterday_msgs)
            response_parts.append(f"**Yesterday ({yesterday_total} message{'s' if yesterday_total > 1 else ''}):**")
            if yesterday_msgs:
                latest_yesterday = yesterday_msgs[0]
                time_str = latest_yesterday["timestamp"].strftime("%H:%M")
                response_parts.append(f"🕒 {time_str}: {latest_yesterday['message_content']}")
            response_parts.append("")
        
        if this_week_msgs:
            week_total = sum(msg.get("message_count", 1) for msg in this_week_msgs)
            response_parts.append(f"**This week:** {week_total} more message{'s' if week_total > 1 else ''}")
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
        return "❌ **No recent messages found.**\n\n🔭 Your inbox appears empty. Check your message settings or try refreshing."
    
    response_parts = [
        f"📧 **Message Summary ({stats['total_messages']} total messages):**",
        ""
    ]
    
    if stats["today_messages"] > 0:
        response_parts.append(f"**Today:** {stats['today_messages']} message{'s' if stats['today_messages'] > 1 else ''}")
        if stats["today_senders"]:
            response_parts.append(f"**From:** {', '.join(stats['today_senders'])}")
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

def generate_task_response(query: str, parsed_data: Dict[str, Any]) -> str:
    """Generate response for task-related queries"""
    
    query_lower = query.lower()
    is_today_query = any(word in query_lower for word in ["today", "now", "current"])
    is_priority_query = any(word in query_lower for word in ["priority", "important", "urgent", "should", "recommend"])
    
    # Case 1: User has overdue tasks - HIGHEST PRIORITY
    if parsed_data["overdue_tasks"]:
        return handle_overdue_tasks_response(parsed_data, is_today_query)
    
    # Case 2: User has tasks due today
    if parsed_data["today_tasks"]:
        return handle_today_tasks_response(parsed_data)
    
    # Case 3: No tasks for today but has upcoming tasks
    if parsed_data["upcoming_tasks"]:
        return handle_upcoming_tasks_response(parsed_data)
    
    # Case 4: No tasks at all
    if parsed_data["total_tasks"] == 0:
        return handle_no_tasks_response()
    
    # Fallback
    return "I can see your task data but need clarification on what specific information you're looking for."

def handle_overdue_tasks_response(parsed_data: Dict[str, Any], is_today_query: bool) -> str:
    """Handle response when user has overdue tasks"""
    
    overdue_count = len(parsed_data["overdue_tasks"])
    today_count = len(parsed_data["today_tasks"])
    
    # Get most critical overdue task
    critical_task = parsed_data["overdue_tasks"][0] if parsed_data["overdue_tasks"] else None
    
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
    
    if critical_task:
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
        
        for task in parsed_data["overdue_tasks"][1:min(3, overdue_count)]:
            response_parts.append(f"• {task['task_name']} (Due: {task['due_date']}, Priority: {task['priority']})")
        
        if overdue_count > 3:
            response_parts.append(f"• ...and {overdue_count - 3} more overdue items")
        
        response_parts.append("")
    
    response_parts.extend([
        "**💡 Recommendation:**",
        "1. Clear your calendar for the next 2-3 hours",
        "2. Focus exclusively on the most critical overdue task",
        "3. Communicate delays to stakeholders if needed",
        "4. Once caught up, establish better deadline tracking"
    ])
    
    return "\n".join(response_parts)

def handle_today_tasks_response(parsed_data: Dict[str, Any]) -> str:
    """Handle response for today's tasks"""
    
    today_count = len(parsed_data["today_tasks"])
    
    response_parts = [
        f"📅 **You have {today_count} task{'s' if today_count > 1 else ''} due today:**",
        ""
    ]
    
    for task in parsed_data["today_tasks"]:
        response_parts.append(f"• **{task['task_name']}** (Priority: {task['priority']})")
    
    response_parts.extend([
        "",
        "**💡 Recommendation:** Start with the highest priority task and work through them systematically."
    ])
    
    return "\n".join(response_parts)

def handle_upcoming_tasks_response(parsed_data: Dict[str, Any]) -> str:
    """Handle response for upcoming tasks"""
    
    upcoming_count = len(parsed_data["upcoming_tasks"])
    
    response_parts = [
        "✅ **No tasks due today.**",
        f"📈 You have {upcoming_count} upcoming task{'s' if upcoming_count > 1 else ''}:",
        ""
    ]
    
    for task in parsed_data["upcoming_tasks"][:5]:  # Show first 5
        response_parts.append(f"• **{task['task_name']}** (Due: {task['due_date']}, Priority: {task['priority']})")
    
    if upcoming_count > 5:
        response_parts.append(f"• ...and {upcoming_count - 5} more tasks")
    
    response_parts.extend([
        "",
        "**💡 Recommendation:** Great time to get ahead on upcoming work or focus on professional development."
    ])
    
    return "\n".join(response_parts)

def handle_no_tasks_response() -> str:
    """Handle response when no tasks are found"""
    
    return """🎉 **Excellent! No pending tasks found.**

You're all caught up! This is the perfect time to:
• Plan ahead for upcoming projects
• Focus on professional development
• Take a well-deserved break

Keep up the great work!"""

def generate_mixed_response(query: str, parsed_data: Dict[str, Any], context: str) -> str:
    """Generate response for queries that might involve both tasks and messages"""
    
    return generate_llm_response(query, context)

def generate_llm_response(query: str, context: str) -> str:
    """Enhanced LLM response with better prompting"""
    
    os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
    
    prompt_template = PromptTemplate.from_template("""
You are a professional project management assistant analyzing both task and message data for a user.

CONTEXT DATA:
{context}

USER QUESTION: "{query}"

IMPORTANT RULES:
- For message queries: Answer directly about messages with specific names, times, and content
- For task queries: Prioritize overdue items, be specific about task names and due dates  
- Reference actual data from the context - don't make up information
- If no relevant data exists, state this clearly
- Be professional but conversational
- Keep responses focused and actionable

Provide a specific, helpful response based on their actual data:
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

# Keep existing interpret_query function
def interpret_query(query: str, hints: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Enhanced query interpretation with better user name resolution"""
    hints = hints or {}
    names = hints.get("team_member_names", [])
    me = hints.get("current_user_name", "")

    query_lower = query.lower()
    target_user = {"type": "me"}
    
    # Check for specific user names in query
    for name in names:
        if name.lower() in query_lower:
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