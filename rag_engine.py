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
    """Enhanced context parsing for both individual and team tasks with debug info"""
    
    print(f"🔍 CONTEXT PARSER - Input length: {len(user_context)}")
    
    parsed_data = {
        # Individual task data (existing)
        "tasks": {
            "overdue": [],
            "today": [],
            "upcoming": [],
            "total_count": 0
        },
        # Team task data (new)
        "team_tasks": {},
        # Message data (existing)
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
        print("⚠️ CONTEXT PARSER - Empty context received")
        return parsed_data
    
    lines = user_context.split('\n')
    current_section = None
    current_user = None  # For team task parsing
    
    print(f"🔍 CONTEXT PARSER - Processing {len(lines)} lines")
    
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
            
        # Section identification with debug
        # ---- FLEXIBLE SECTION DETECTION (accept old + new headers) ----
        # PERSONAL (individual) task sections
        if (
            "YOUR ACTIVE TASKS:" in line or
            "YOUR KANBAN TASKS:" in line or
            line.startswith("🚨 OVERDUE TASKS:") or
            line.startswith("📅 DUE TODAY:") or
            line.startswith("📆 DUE TOMORROW:") or
            line.startswith("📅 THIS WEEK:")
        ):
            current_section = "tasks"
            current_user = None
            print(f"📋 Line {line_num}: Entered PERSONAL TASKS section via header: {line}")
            continue

        elif (
            "TECH TEAM - ACTIVE TASKS:" in line
            or "TECH TEAM - KANBAN TASKS:" in line
            or "TEAM LEADS - ACTIVE TASKS:" in line
            or "TEAM LEADS - KANBAN TASKS:" in line
            or "MEMBERS - ACTIVE TASKS:" in line
            or "MEMBERS - KANBAN TASKS:" in line
            or re.search(r"^\s*TEAM\s+TASKS\b", line, re.I)   # catches: "TEAM TASKS (TECH_TEAM):", etc.
        ):
            current_section = "team_tasks"
            current_user = None
            print(f"🏢 Line {line_num}: Entered TEAM TASKS section via header: {line}")
            continue


        elif (re.search(r"(team messages:|message data|recent messages:?)", line, re.I)
            or line.strip().startswith("🧾 Recent Messages")):
            current_section = "messages"
            current_user = None
            print(f"💬 Line {line_num}: Entered MESSAGES section")
            continue


            
        # Check for user headers in team task sections (e.g., "👤 John Doe:")
        if current_section != "team_tasks" and line.startswith("👤"):
            current_section = "team_tasks"
            current_user = None
            print(f"🏢 Line {line_num}: Implicitly entered TEAM TASKS section (saw user header)")
            # no 'continue' here; let the next block set current_user

            user_match = re.search(r"👤\s*([^:]+):", line)
            if user_match:
                current_user = user_match.group(1).strip()
                if current_user not in parsed_data["team_tasks"]:
                    parsed_data["team_tasks"][current_user] = []
                print(f"👤 Line {line_num}: Found user section for {current_user}")
                continue
            # If we're already inside TEAM TASKS, a "👤 Name:" line should (re)select the user
            if current_section == "team_tasks" and line.startswith("👤"):
                user_match = re.search(r"👤\s*([^:]+):", line)
                if user_match:
                    current_user = user_match.group(1).strip()
                    if current_user not in parsed_data["team_tasks"]:
                        parsed_data["team_tasks"][current_user] = []
                    print(f"👤 Line {line_num}: Found user section for {current_user}")
                    continue


        # Parse content based on section
        if line.startswith("•") or line.startswith("→") or line.startswith("-") or line.startswith("  •"):
            if current_section == "tasks":
                # Individual task parsing (existing logic)
                task_info = parse_task_line(line)
                if task_info:
                    parsed_data["tasks"]["total_count"] += 1
                    if task_info["urgency"] == "OVERDUE":
                        parsed_data["tasks"]["overdue"].append(task_info)
                        print(f"🚨 Line {line_num}: Found OVERDUE task: {task_info['task_name']}")
                    elif task_info["urgency"] == "DUE TODAY":
                        parsed_data["tasks"]["today"].append(task_info)
                        print(f"📅 Line {line_num}: Found TODAY task: {task_info['task_name']}")
                    else:
                        parsed_data["tasks"]["upcoming"].append(task_info)
                        print(f"📈 Line {line_num}: Found UPCOMING task: {task_info['task_name']}")
                else:
                    print(f"⚠️ Line {line_num}: Failed to parse task line: {line[:50]}...")
                        
            elif current_section == "team_tasks" and current_user:
                # Team task parsing (new logic)
                task_info = parse_task_line(line)
                if task_info:
                    task_info["assigned_to"] = current_user
                    parsed_data["team_tasks"][current_user].append(task_info)
                    print(f"🏢 Line {line_num}: Found team task for {current_user}: {task_info['task_name']}")
                else:
                    print(f"⚠️ Line {line_num}: Failed to parse team task line: {line[:50]}...")
                        
            elif current_section == "messages":
                # Message parsing (existing logic)
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
                    print(f"💬 Line {line_num}: Found message from {sender}")
                else:
                    print(f"⚠️ Line {line_num}: Failed to parse message line: {line[:50]}...")
    
    # Final summary
    tasks = parsed_data["tasks"]
    team_tasks = parsed_data["team_tasks"]
    messages = parsed_data["messages"]
    
    team_task_count = sum(len(user_tasks) for user_tasks in team_tasks.values())
    team_users_count = len(team_tasks)
    
    print(f"📊 CONTEXT PARSER SUMMARY:")
    print(f"  Individual Tasks: {tasks['total_count']} total ({len(tasks['overdue'])} overdue, {len(tasks['today'])} today, {len(tasks['upcoming'])} upcoming)")
    print(f"  Team Tasks: {team_task_count} total across {team_users_count} team members")
    print(f"  Messages: {messages['total_count']} total ({len(messages['today'])} today, {len(messages['yesterday'])} yesterday)")
    print(f"  Team members: {len(parsed_data['team_members'])}")
    
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
    """Parse one message bullet into a dict with sender, content, timestamp_str, recency, count."""

    # Multiple formats your context can emit
    patterns = [
        # e.g. "From John Doe (3 messages) Latest (2025-09-09 10:22): Fixed issue"
        r"From\s+([^(]+?)\s*\((\d+)\s*messages?\).*?Latest\s*\(([^)]+)\):\s*(.+)",

        # e.g. "From John Doe: Hello there (2025-09-09 10:22)"
        r"From\s+([^:]+):\s*([^(]+)\s*\(([^)]+)\)",

        # e.g. "• From John Doe: Hello there"
        r"[•→]\s*From\s+([^:]+):\s*(.+)",

        # e.g. "• John Doe: Hello there"
        r"[•→]\s*([^:]+?):\s*(.+)"
    ]

    sender_name = None
    message_content = ""
    timestamp_str = "recent"
    message_count = 1

    for pattern in patterns:
        m = re.search(pattern, line, re.IGNORECASE)
        if not m:
            continue

        if pattern == patterns[0]:  # complex "Latest (...)" form
            sender_name = m.group(1).strip()
            message_count = int(m.group(2)) if m.group(2).isdigit() else 1
            timestamp_str = m.group(3).strip()
            message_content = m.group(4).strip()
        elif pattern == patterns[1]:  # "...: text (YYYY-MM-DD ...)"
            sender_name = m.group(1).strip()
            message_content = m.group(2).strip()
            timestamp_str = m.group(3).strip()
            message_count = 1
        else:  # simple 2-group forms
            sender_name = m.group(1).strip()
            message_content = m.group(2).strip() if len(m.groups()) >= 2 else ""
            timestamp_str = "recent"
            message_count = 1
        break

    if not sender_name:
        return None

    # --- recency detection ---
    # Default
    recency = "this_week"

    # Literal hints
    if "TODAY:" in line or "today" in (timestamp_str or "").lower():
        recency = "today"
    elif "YESTERDAY:" in line or "yesterday" in (timestamp_str or "").lower():
        recency = "yesterday"
    else:
        # Map ISO-like dates in timestamp to today/yesterday
        try:
            m = re.search(r"\d{4}-\d{2}-\d{2}", timestamp_str or "")
            if m:
                date_part = m.group(0)
                today_iso = datetime.utcnow().date().isoformat()
                yest_iso = (datetime.utcnow() - timedelta(days=1)).date().isoformat()
                if date_part == today_iso:
                    recency = "today"
                elif date_part == yest_iso:
                    recency = "yesterday"
        except Exception:
            pass

    return {
        "sender_name": sender_name,
        "message_content": message_content,
        "timestamp_str": timestamp_str,
        "recency": recency,
        "message_count": message_count
    }


def classify_query_type(query: str, team_members: List[str] = None) -> str:
    """Enhanced query classification with team and role query detection"""
    
    query_lower = query.lower()
    team_members = team_members or []
    
    # NEW: Team-wide task queries - highest priority
    team_task_patterns = [
        r"show.*all.*tech.*team.*task",
        r"all.*tech.*team.*member.*task", 
        r"tech.*team.*task",
        r"show.*all.*team.*lead.*task",
        r"all.*team.*lead.*task",
        r"team.*lead.*task",
        r"show.*all.*member.*task",
        r"all.*member.*task",
        r"member.*task",
        r"show.*team.*task",
        r"team.*member.*task"
    ]
    
    # Check team task patterns first (highest priority)
    for pattern in team_task_patterns:
        if re.search(pattern, query_lower):
            print(f"🏢 TEAM TASK PATTERN MATCH: {pattern}")
            return "team_task_query"
    
    # Strong TASK indicators - these should take priority over general patterns
    strong_task_patterns = [
        r"what.*should.*complete",
        r"what.*should.*do",
        r"what.*should.*work.*on",
        r"complete.*today",
        r"work.*today",
        r"task.*today",
        r"what.*task",
        r"which.*task",
        r"next.*task",
        r"priority.*today",
        r"due.*today",
        r"finish.*today",
        r"today.*priority",
        r"today.*task",
        r"overdue.*task",
        r"my.*task"
    ]
    
    # Strong MESSAGE indicators
    strong_message_patterns = [
        r"did.*get.*message",
        r"any.*message.*from",
        r"message.*from.*today",
        r"got.*any.*message",
        r"hear.*from",
        r"said.*anything",
        r"contact.*me",
        r"anyone.*message",
        r"team.*message",
        r"word.*from"
    ]
    
    # Check strong task patterns 
    for pattern in strong_task_patterns:
        if re.search(pattern, query_lower):
            print(f"🎯 STRONG TASK PATTERN MATCH: {pattern}")
            return "task_query"
    
    # Check strong message patterns
    for pattern in strong_message_patterns:
        if re.search(pattern, query_lower):
            print(f"💬 STRONG MESSAGE PATTERN MATCH: {pattern}")
            return "message_query"
    
    # Task keywords (for weaker matches)
    task_keywords = [
        "task", "tasks", "work", "complete", "finish", "priority", 
        "due", "deadline", "project", "assignment", "todo", "do today",
        "overdue", "schedule", "kanban", "start", "begin", "working on",
        "should", "complete today", "work on today"
    ]
    
    # Message keywords (for weaker matches)
    message_keywords = [
        "message", "messages", "chat", "said", "told", "replied", 
        "conversation", "spoke", "mentioned", "contacted", "reached out",
        "sent", "received", "hear from", "got any", "any word from",
        "text", "texted", "communicate", "communication", "msg", "msgs"
    ]
    
    # Check for team member mentions (only affects message queries)
    mentions_team_member = False
    for member in team_members:
        member_lower = member.lower()
        first_name = member.split()[0].lower()
        if (member_lower in query_lower or 
            first_name in query_lower or
            f"from {first_name}" in query_lower):
            mentions_team_member = True
            break
    
    # If mentions team member + message keywords -> message query
    if mentions_team_member and any(kw in query_lower for kw in message_keywords):
        print(f"💬 TEAM MEMBER + MESSAGE KEYWORDS")
        return "message_query"
    
    # Count keyword scores
    task_score = sum(1 for kw in task_keywords if kw in query_lower)
    message_score = sum(1 for kw in message_keywords if kw in query_lower)
    
    print(f"📊 Scores - Task: {task_score}, Message: {message_score}")
    
    # Task queries take precedence when scores are equal or task score is higher
    if task_score >= message_score and task_score > 0:
        print(f"🎯 CLASSIFIED AS TASK QUERY (score: {task_score})")
        return "task_query"
    elif message_score > task_score and message_score > 0:
        print(f"💬 CLASSIFIED AS MESSAGE QUERY (score: {message_score})")
        return "message_query"
    else:
        print(f"❓ CLASSIFIED AS GENERAL QUERY")
        return "general_query"
    

    


def get_rag_response(query: str, user_context: str = ""):
    """Main RAG response function with enhanced team task handling"""
    
    print(f"🔥 ENHANCED RAG ENGINE - Processing query: {query}")
    print(f"📊 Context length: {len(user_context)} characters")

    if not wait_for_ollama():
        return "⚠️ AI backend is temporarily unavailable. Please try again in a moment."

    # Parse the context
    parsed_data = parse_user_context(user_context)
    
    print(f"📋 Parsed tasks: {parsed_data['tasks']['total_count']}")
    print(f"💬 Parsed messages: {parsed_data['messages']['total_count']}")
    
    # Classify the query with debug info
    query_type = classify_query_type(query, parsed_data['team_members'])
    print(f"🎯 Query classified as: {query_type}")
    
    # Force task handling for common task patterns
    task_indicators = [
        "what should i complete",
        "what should i do", 
        "what should i work on",
        "complete today",
        "work today",
        "task today",
        "priority today",
        "due today"
    ]
    
    # Force team task handling for team patterns
    team_task_indicators = [
        "show all tech team",
        "all tech team members task",
        "tech team task",
        "show all team lead",
        "all team lead task",
        "show all member",
        "all member task"
    ]
    
    query_lower = query.lower()
    if any(indicator in query_lower for indicator in task_indicators):
        print(f"🎯 FORCING TASK RESPONSE due to strong task indicators")
        query_type = "task_query"
    elif any(indicator in query_lower for indicator in team_task_indicators):
        print(f"🏢 FORCING TEAM TASK RESPONSE due to team task indicators")
        query_type = "team_task_query"
    
    # Generate response based on query type
    if query_type == "team_task_query":
        print("🏢 Generating TEAM TASK response")
        return generate_team_task_response(query, parsed_data)
    elif query_type == "task_query":
        print("📋 Generating TASK response")
        return generate_task_response(query, parsed_data)
    elif query_type == "message_query":
        print("💬 Generating MESSAGE response")  
        return generate_message_response(query, parsed_data)
    else:
        print("🤖 Generating GENERAL response")
        return generate_general_response(query, parsed_data, user_context)
    


def generate_task_response(query: str, parsed_data: Dict[str, Any]) -> str:
    """Generate response specifically for task queries"""
    
    print("🎯 Generating TASK response")
    
    tasks = parsed_data["tasks"]
    q = (query or "").lower()
    if any(k in q for k in ["overdue", "past due", "late"]) and tasks["overdue"]:
        print("🚨 Overdue requested explicitly — showing overdue first")
        return handle_overdue_tasks(tasks["overdue"], query)

    
    # Log what we found
    print(f"📊 Task breakdown:")
    print(f"  - Overdue: {len(tasks['overdue'])}")
    print(f"  - Due today: {len(tasks['today'])}")
    print(f"  - Upcoming: {len(tasks['upcoming'])}")
    print(f"  - Total: {tasks['total_count']}")
    
    # Handle different task scenarios with priority order
    if tasks["today"]:
        print("📅 Handling TODAY tasks")
        return handle_today_tasks(tasks["today"], query)
    elif tasks["overdue"]:
        print("🚨 Handling OVERDUE tasks")
        return handle_overdue_tasks(tasks["overdue"], query)
   
    elif tasks["upcoming"]:
        print("📈 Handling UPCOMING tasks")
        return handle_upcoming_tasks(tasks["upcoming"], query)
    else:
        print("✅ No tasks found")
        return handle_no_tasks(query)

def handle_overdue_tasks(overdue_tasks: List[Dict], query: str) -> str:
    """Handle overdue task scenarios - HIGHEST PRIORITY"""
    
    count = len(overdue_tasks)
    print(f"🚨 Processing {count} overdue tasks")
    
    response_parts = [
        f"🚨 **URGENT: You have {count} overdue task{'s' if count > 1 else ''}!**",
        "",
        "**❌ CRITICAL: Do NOT start new work until these are resolved:**"
    ]
    
    # Show up to 3 overdue tasks with full details
    for i, task in enumerate(overdue_tasks[:3], 1):
        task_name = task['task_name']
        due_date = task['due_date']
        priority = task['priority']
        
        response_parts.append(
            f"{i}. **{task_name}** (Due: {due_date}, Priority: {priority}) - OVERDUE!"
        )
        print(f"  📌 Overdue task {i}: {task_name}")
    
    if count > 3:
        response_parts.append(f"...and {count - 3} more overdue tasks")
    
    response_parts.extend([
        "",
        "**💡 Immediate Action Required:**",
        f"🎯 **Start immediately with: '{overdue_tasks[0]['task_name']}'**",
        "",
        "📞 Consider notifying stakeholders about delays and clear your schedule to catch up!"
    ])
    
    return "\n".join(response_parts)

def handle_today_tasks(today_tasks: List[Dict], query: str) -> str:
    """Handle tasks due today"""
    
    count = len(today_tasks)
    print(f"📅 Processing {count} tasks due today")
    
    response_parts = [
        f"📅 **You have {count} task{'s' if count > 1 else ''} due TODAY:**",
        ""
    ]
    
    # Show all today's tasks with priorities
    for i, task in enumerate(today_tasks, 1):
        task_name = task['task_name']
        priority = task['priority']
        
        priority_emoji = "🔴" if priority == "High" else "🟡" if priority == "Medium" else "🟢"
        
        response_parts.append(
            f"{i}. {priority_emoji} **{task_name}** (Priority: {priority})"
        )
        print(f"  📌 Today's task {i}: {task_name} ({priority})")
    
    # Provide specific recommendations
    high_priority_tasks = [t for t in today_tasks if t['priority'] == 'High']
    if high_priority_tasks:
        response_parts.extend([
            "",
            f"**💡 Recommendation:** Start with HIGH priority: **{high_priority_tasks[0]['task_name']}**"
        ])
    else:
        response_parts.extend([
            "",
            f"**💡 Recommendation:** Start with: **{today_tasks[0]['task_name']}** and work systematically through the list."
        ])
    
    return "\n".join(response_parts)

def generate_team_task_response(query: str, parsed_data: Dict[str, Any]) -> str:
    """Generate response specifically for team task queries"""
    
    print("🏢 Generating TEAM TASK response")
    
    team_tasks = parsed_data.get("team_tasks", {})
    
    if not team_tasks:
        return """🔍 **No Team Task Data Found**

Unable to retrieve team task information. This could be because:
• No team members have active tasks
• Database access issue  
• Team filtering not working properly

**Suggestion:** Check individual user task dashboards directly."""
    
    # Analyze query to determine specific focus
    query_lower = query.lower()
    is_tech_team_query = "tech team" in query_lower
    is_lead_query = "team lead" in query_lower or "lead" in query_lower
    is_member_query = "member" in query_lower and not is_lead_query
    
    # Process team task data
    total_tasks = sum(len(user_tasks) for user_tasks in team_tasks.values())
    total_users = len(team_tasks)
    
    # Categorize all tasks by urgency
    overdue_tasks = []
    today_tasks = []
    upcoming_tasks = []
    
    for user_name, user_tasks in team_tasks.items():
        for task in user_tasks:
            task_entry = {
                "user": user_name,
                "name": task.get("task_name", "Unnamed task"),
                "due": task.get("due_date", "No due date"),
                "priority": task.get("priority", "Medium"),
                "urgency": task.get("urgency", "Later")
            }
            
            if task.get("urgency") == "OVERDUE":
                overdue_tasks.append(task_entry)
            elif task.get("urgency") == "DUE TODAY":
                today_tasks.append(task_entry)
            else:
                upcoming_tasks.append(task_entry)
    
    # Build response based on query type
    if is_tech_team_query:
        title = "🏢 **Tech Team Task Overview**"
    elif is_lead_query:
        title = "👑 **Team Lead Task Overview**"
    elif is_member_query:
        title = "👤 **Team Member Task Overview**"
    else:
        title = "🏢 **Team Task Overview**"
    
    response_parts = [
        f"{title} ({total_tasks} tasks across {total_users} team members)",
        ""
    ]
    
    # Show overdue tasks first (CRITICAL)
    if overdue_tasks:
        response_parts.extend([
            f"🚨 **CRITICAL - OVERDUE TASKS ({len(overdue_tasks)}):**",
            ""
        ])
        
        # Group overdue by user for better organization
        overdue_by_user = {}
        for task in overdue_tasks:
            user = task["user"]
            if user not in overdue_by_user:
                overdue_by_user[user] = []
            overdue_by_user[user].append(task)
        
        for user, tasks in overdue_by_user.items():
            response_parts.append(f"**{user}** ({len(tasks)} overdue):")
            for task in tasks[:3]:  # Show max 3 per user
                response_parts.append(f"  • {task['name']} (Due: {task['due']}, Priority: {task['priority']})")
            if len(tasks) > 3:
                response_parts.append(f"  • ...and {len(tasks) - 3} more overdue tasks")
            response_parts.append("")
    
    # Show today's tasks
    if today_tasks:
        response_parts.extend([
            f"📅 **DUE TODAY ({len(today_tasks)}):**",
            ""
        ])
        
        # Group today's tasks by user
        today_by_user = {}
        for task in today_tasks:
            user = task["user"]
            if user not in today_by_user:
                today_by_user[user] = []
            today_by_user[user].append(task)
        
        for user, tasks in today_by_user.items():
            response_parts.append(f"**{user}** ({len(tasks)} due today):")
            for task in tasks[:3]:  # Show max 3 per user
                response_parts.append(f"  • {task['name']} (Priority: {task['priority']})")
            if len(tasks) > 3:
                response_parts.append(f"  • ...and {len(tasks) - 3} more tasks due today")
            response_parts.append("")
    
    # Show upcoming tasks (limited view)
    if upcoming_tasks:
        response_parts.extend([
            f"📈 **UPCOMING TASKS (next 5 by due date):**",
            ""
        ])
        
        # Sort upcoming by due date
        upcoming_sorted = sorted(upcoming_tasks, 
                               key=lambda x: x['due'] if x['due'] != 'No due date' else '2999-12-31')
        
        for task in upcoming_sorted[:5]:
            response_parts.append(f"• **{task['user']}**: {task['name']} (Due: {task['due']}, Priority: {task['priority']})")
        
        if len(upcoming_tasks) > 5:
            response_parts.append(f"...and {len(upcoming_tasks) - 5} more upcoming tasks")
        response_parts.append("")
    
    # Team summary and recommendations
    response_parts.extend([
        "**📊 Team Summary:**",
        f"• Total active tasks: {total_tasks}",
        f"• Team members with tasks: {total_users}",
        f"• Overdue tasks: {len(overdue_tasks)}",
        f"• Due today: {len(today_tasks)}",
        f"• Upcoming tasks: {len(upcoming_tasks)}",
        ""
    ])
    
    # Actionable recommendations based on urgency
    if len(overdue_tasks) > 0:
        response_parts.extend([
            "**⚠️ IMMEDIATE ACTION REQUIRED:**",
            f"Team has {len(overdue_tasks)} overdue tasks across {len(set(task['user'] for task in overdue_tasks))} team members!",
            "",
            "**Recommendations:**",
            "• Schedule urgent team standup to address overdue items",
            "• Redistribute workload if team members are overwhelmed", 
            "• Extend deadlines where appropriate and notify stakeholders",
            "• Identify and remove blockers preventing task completion"
        ])
    elif len(today_tasks) > 0:
        response_parts.extend([
            "**💡 Today's Focus:**",
            f"Team has {len(today_tasks)} tasks due today - monitor progress closely.",
            "",
            "**Recommendations:**",
            "• Check in with team members during daily standup",
            "• Be available to help remove any last-minute blockers", 
            "• Prepare for potential deadline extensions if needed"
        ])
    else:
        response_parts.extend([
            "**✅ Excellent Status:**",
            "Team has no overdue tasks and nothing due today!",
            "",
            "**Recommendations:**",
            "• Great time to plan ahead for upcoming deliverables",
            "• Consider taking on additional stretch goals",
            "• Focus on process improvements and team development"
        ])
    
    # If no tasks found at all
    if total_tasks == 0:
        return f"""🎉 **{title.replace('**', '').replace('🏢 ', '').replace('👑 ', '').replace('👤 ', '')}**

No active tasks found for the specified team members.

This could mean:
• All team members are caught up with their work ✅
• Tasks are managed in a different system
• Team members haven't been assigned tasks yet
• Database filtering issue

**Suggestion:** Verify task assignments and check if tasks are in a different status."""
    
    return "\n".join(response_parts)


def handle_no_team_tasks(query: str) -> str:
    """Handle when no team tasks are found"""
    
    print("✅ No team tasks found - generating informative response")
    
    return """🔍 **No Team Task Data Available**

Unable to retrieve team task information for your query.

**Possible reasons:**
• Team members have no active tasks assigned
• Tasks may be in "Completed" or "Archived" status  
• Database connection or filtering issue
• Team structure not properly configured

**What you can do:**
• Check individual team member dashboards
• Verify team assignments in user management
• Look at completed tasks to see recent activity
• Contact your system administrator if this seems incorrect

**Try asking:**
• "Show my tasks today" (for personal tasks)
• "What should I work on today?" (for personal priorities)
• "Any messages from the team?" (for team communications)"""


def handle_upcoming_tasks(upcoming_tasks: List[Dict], query: str) -> str:
    """Handle upcoming tasks when nothing is due today"""
    
    count = len(upcoming_tasks)
    print(f"📈 Processing {count} upcoming tasks")
    
    # Sort upcoming tasks by due date
    sorted_tasks = sorted(upcoming_tasks, key=lambda x: x['due_date'] if x['due_date'] != 'No date' else '2999-12-31')
    
    response_parts = [
        "✅ **Excellent! No tasks due today.**",
        f"📈 You have {count} upcoming task{'s' if count > 1 else ''}:",
        ""
    ]
    
    # Show next 5 upcoming tasks with due dates
    for i, task in enumerate(sorted_tasks[:5], 1):
        task_name = task['task_name']
        due_date = task['due_date']
        priority = task['priority']
        
        response_parts.append(
            f"{i}. **{task_name}** (Due: {due_date}, Priority: {priority})"
        )
        print(f"  📌 Upcoming task {i}: {task_name} (Due: {due_date})")
    
    if count > 5:
        response_parts.append(f"...and {count - 5} more upcoming tasks")
    
    # Suggest next best action
    next_task = sorted_tasks[0] if sorted_tasks else None
    if next_task:
        response_parts.extend([
            "",
            f"**💡 Perfect time to get ahead!**",
            f"🎯 **Consider starting early on: '{next_task['task_name']}' (Due: {next_task['due_date']})**",
            "",
            "**Other options:**",
            "• Focus on professional development",
            "• Review and organize your workflow", 
            "• Plan ahead for upcoming projects"
        ])
    
    return "\n".join(response_parts)

def handle_no_tasks(query: str) -> str:
    """Handle when no tasks are found"""
    
    print("✅ No tasks found - generating positive response")
    
    return """🎉 **Outstanding! No pending tasks found.**

You're completely caught up! This is perfect timing to:
• 🚀 Plan ahead for upcoming projects  
• 📚 Focus on professional development
• 🧘 Take a well-deserved break
• 🗂️ Review and organize your workflow
• 💡 Brainstorm new ideas or improvements

**Keep up the excellent work!** You're ahead of schedule and in great shape."""



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