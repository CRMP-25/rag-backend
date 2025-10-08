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
    print(f"🔍 CONTEXT PARSER - Raw context preview:")
    print(f"First 500 characters: {user_context[:500]}")
    print("="*50)
    
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
        elif (re.search(r"(team messages:|message data|recent messages:?)", line, re.I)
            or line.strip().startswith("🧾 Recent Messages")
            or "TEAM MESSAGES" in line):  # ✅ NEW: Also catch "💬 TEAM MESSAGES"
            current_section = "messages"
            current_user = None
            print(f"💬 Line {line_num}: Entered MESSAGES section via: {line[:50]}")
            continue

        # Check for user headers in team task sections (e.g., "👤 John Doe:")
        # FIXED: This should work regardless of current section
        if line.startswith("👤"):
            # If we see a user header, we're definitely in team tasks section
            if current_section != "team_tasks":
                current_section = "team_tasks"
                print(f"🏢 Line {line_num}: Implicitly entered TEAM TASKS section (saw user header)")
            
            user_match = re.search(r"👤\s*([^:]+):", line)
            if user_match:
                current_user = user_match.group(1).strip()
                if current_user not in parsed_data["team_tasks"]:
                    parsed_data["team_tasks"][current_user] = []
                # Add to team members list if not already there
                if current_user not in parsed_data["team_members"]:
                    parsed_data["team_members"].append(current_user)
                print(f"👤 Line {line_num}: Found user section for '{current_user}'")
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
                    print(f"🏢 Line {line_num}: Found team task for '{current_user}': {task_info['task_name']}")
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
    """Parse task line with created_date support"""
    
    clean_line = re.sub(r"^[\s•→'-]+", "", line).strip()
    
    # Enhanced pattern to capture created date
    mhead = re.search(r"\[([^\]]+)\]\s*([^(]+?)\s*\((.*)\)\s*$", clean_line)
    if mhead:
        urgency = mhead.group(1).strip()
        task_name = mhead.group(2).strip()
        meta = mhead.group(3)
        
        pm = re.search(r"Priority:\s*([^,)\]]+)", meta, re.I)
        sm = re.search(r"Status:\s*([^,)\]]+)", meta, re.I)
        dm = re.search(r"Due:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", meta, re.I)
        # 🆕 NEW: Extract created date
        cm = re.search(r"Created:\s*([^,)\]]+)", meta, re.I)
        # 🆕 NEW: Extract Task ID
        im = re.search(r"Task ID:\s*([^,)\]]+)", meta, re.I)
        
        due_date_raw = dm.group(1).strip() if dm else None
        created_date = cm.group(1).strip() if cm else None
        task_id = im.group(1).strip() if im else None
        
        return {
            "task_name": task_name,
            "urgency": urgency,
            "priority": (pm.group(1).strip() if pm else "Medium"),
            "status": (sm.group(1).strip() if sm else "Active"),
            "due_date": (due_date_raw or "No date"),
            "created_date": (created_date or "Unknown"),  # 🆕 NEW
            "task_id": task_id  # 🆕 NEW
        }
    
    # Keep existing fallback patterns...
    pattern3 = r"\[([^\]]+)\]\s*(.+)"
    match3 = re.search(pattern3, clean_line)
    if match3:
        urgency = match3.group(1).strip()
        task_name = match3.group(2).strip()
        
        return {
            "task_name": task_name,
            "urgency": urgency,
            "priority": "Medium",
            "status": "Active",
            "due_date": "No date",
            "created_date": "Unknown",  # 🆕 NEW
            "task_id": None  # 🆕 NEW
        }
    
    if clean_line:
        return {
            "task_name": clean_line,
            "urgency": "Unknown",
            "priority": "Medium",
            "status": "Active", 
            "due_date": "No date",
            "created_date": "Unknown",  # 🆕 NEW
            "task_id": None  # 🆕 NEW
        }
    
    return None

# Add this new function to your mascot.js or equivalent Python backend

def get_team_members_by_query(query: str, users_data: List[Dict]) -> Dict[str, List[str]]:
    """
    Dynamically determine which team members to include based on query
    Returns dict with team_type and list of user_names
    """
    query_lower = query.lower()
    
    # Define team mappings - you can expand this
    team_patterns = {
        'tech_team': ['tech team', 'technical team', 'engineering team', 'developers', 'dev team'],
        'management': ['management team', 'managers', 'team leads', 'leadership', 'management'],
        'intern': ['intern', 'interns', 'trainee', 'trainees'],
        'qa': ['qa team', 'quality assurance', 'testing team', 'testers'],
        'design': ['design team', 'designers', 'ui team', 'ux team'],
        'sales': ['sales team', 'sales', 'business development'],
        'hr': ['hr team', 'human resources', 'people team']
    }
    
    # Role-based patterns
    role_patterns = {
        'admin': ['admin', 'administrator', 'system admin'],
        'lead': ['lead', 'team lead', 'project lead', 'tech lead'],
        'senior': ['senior', 'senior developer', 'senior engineer'],
        'junior': ['junior', 'junior developer', 'junior engineer']
    }
    
    selected_teams = []
    selected_roles = []
    
    # Check for team matches
    for team_key, patterns in team_patterns.items():
        if any(pattern in query_lower for pattern in patterns):
            selected_teams.append(team_key)
            print(f"🎯 Detected team: {team_key}")
    
    # Check for role matches  
    for role_key, patterns in role_patterns.items():
        if any(pattern in query_lower for pattern in patterns):
            selected_roles.append(role_key)
            print(f"🎯 Detected role: {role_key}")
    
    # Filter users based on detected teams and roles
    filtered_users = []
    
    for user in users_data:
        user_team = user.get('team', '').lower()
        user_role = user.get('role', '').lower()
        user_name = user.get('name', '')
        
        # Check team match
        team_match = False
        if selected_teams:
            for team in selected_teams:
                if team == 'tech_team' and any(t in user_team for t in ['tech', 'engineering', 'development']):
                    team_match = True
                elif team == 'management' and any(t in user_team for t in ['management', 'admin']):
                    team_match = True
                elif team == 'intern' and 'intern' in user_team:
                    team_match = True
                elif team == 'qa' and any(t in user_team for t in ['qa', 'quality', 'testing']):
                    team_match = True
                elif team == 'design' and any(t in user_team for t in ['design', 'ui', 'ux']):
                    team_match = True
                elif team == 'sales' and any(t in user_team for t in ['sales', 'business']):
                    team_match = True
                elif team == 'hr' and any(t in user_team for t in ['hr', 'human']):
                    team_match = True
        
        # Check role match
        role_match = False
        if selected_roles:
            for role in selected_roles:
                if role == 'admin' and 'admin' in user_role:
                    role_match = True
                elif role == 'lead' and 'lead' in user_role:
                    role_match = True
                elif role == 'senior' and 'senior' in user_role:
                    role_match = True
                elif role == 'junior' and 'junior' in user_role:
                    role_match = True
        
        # Include user if they match team OR role criteria
        if (not selected_teams and not selected_roles) or team_match or role_match:
            filtered_users.append(user_name)
            print(f"✅ Including user: {user_name} (Team: {user.get('team')}, Role: {user.get('role')})")
    
    return {
        'team_type': '_'.join(selected_teams + selected_roles) if (selected_teams or selected_roles) else 'all',
        'users': filtered_users,
        'detected_teams': selected_teams,
        'detected_roles': selected_roles
    }


def get_user_tasks_by_name(user_name: str) -> List[Dict]:
    """
    Fetch tasks for a specific user by name from database
    You'll need to implement this based on your database structure
    """
    # This is pseudocode - replace with your actual database query
    try:
        # Example SQL query (adjust for your database):
        # SELECT * FROM tasks WHERE assigned_to = user_name AND status != 'completed'
        
        # For now, return empty list - you'll implement the actual database call
        return []
        
    except Exception as e:
        print(f"❌ Error fetching tasks for {user_name}: {e}")
        return []
    
def determine_task_urgency(task: Dict) -> str:
    """
    Determine task urgency based on due date
    """
    due_date_str = task.get('due_date')
    if not due_date_str or due_date_str == 'No date':
        return "LATER"
    
    try:
        from datetime import datetime, date
        
        # Parse due date (adjust format as needed)
        m = re.search(r'\d{4}-\d{2}-\d{2}', due_date_str or '')
        if not m:
            return "LATER"
        due_date = datetime.strptime(m.group(0), '%Y-%m-%d').date()

        today = date.today()
        
        if due_date < today:
            return "OVERDUE"
        elif due_date == today:
            return "DUE TODAY"
        else:
            return "UPCOMING"
            
    except Exception:
        return "LATER"


def build_dynamic_team_context(current_user_id: str, target_info: Dict) -> str:
    """
    Build context for dynamically determined team members
    """
    team_type = target_info.get('team_type', 'all')
    target_users = target_info.get('users', [])
    
    if not target_users:
        return f"TEAM TASKS ({team_type.upper()}): No users found matching the criteria.\n\n"
    
    context_parts = [f"TEAM TASKS ({team_type.upper()}):"]
    context_parts.append("")
    
    # Get tasks for each target user
    for user_name in target_users:
        # You'll need to implement get_user_tasks_by_name function
        user_tasks = get_user_tasks_by_name(user_name)  # This function needs to be implemented
        
        if user_tasks:
            context_parts.append(f"👤 {user_name}:")
            for task in user_tasks:
                # Format task line
                urgency = determine_task_urgency(task)  # You'll need this function too
                task_line = f"  • [{urgency}] {task['name']} (Priority: {task.get('priority', 'Medium')}, Status: {task.get('status', 'Active')}, Due: {task.get('due_date', 'No date')})"
                context_parts.append(task_line)
            context_parts.append("")
        else:
            context_parts.append(f"👤 {user_name}: No active tasks")
            context_parts.append("")
    
    return "\n".join(context_parts)

def parse_message_line(line: str) -> Dict[str, Any]:
    """Parse one message bullet into a dict with sender, content, timestamp_str, recency, count."""
    
    print(f"🔍 PARSING MESSAGE LINE: {line[:80]}")  # ✅ NEW: Debug what we're parsing

    # Multiple formats your context can emit
    patterns = [
        # e.g. "From John Doe (3 messages) Latest (2025-09-09 10:22): Fixed issue"
        r"From\s+([^(]+?)\s*\((\d+)\s*messages?\).*?Latest\s*\(([^)]+)\):\s*(.+)",

        # e.g. "From John Doe: Hello there (2025-09-09 10:22)"
        r"From\s+([^:]+):\s*([^(]+)\s*\(([^)]+)\)",

        # ✅ NEW PATTERN: "• From John Doe: message (HH:MM AM/PM, YYYY-MM-DD)"
        r"[•➤]\s*From\s+([^:]+):\s*(.+?)\s*\(([^,]+),\s*([^)]+)\)",

        # e.g. "• From John Doe: Hello there"
        r"[•➤]\s*From\s+([^:]+):\s*(.+)",

        # e.g. "• John Doe: Hello there"
        r"[•➤]\s*([^:]+?):\s*(.+)"
    ]

    sender_name = None
    message_content = ""
    timestamp_str = "recent"
    message_count = 1
    date_str = None  # ✅ NEW: Store date separately

    for i, pattern in enumerate(patterns):
        m = re.search(pattern, line, re.IGNORECASE)
        if not m:
            continue

        print(f"✅ Pattern {i} MATCHED: {pattern[:50]}")  # ✅ NEW: Debug match

        if i == 0:  # complex "Latest (...)" form
            sender_name = m.group(1).strip()
            message_count = int(m.group(2)) if m.group(2).isdigit() else 1
            timestamp_str = m.group(3).strip()
            message_content = m.group(4).strip()
        elif i == 1:  # "...: text (YYYY-MM-DD ...)"
            sender_name = m.group(1).strip()
            message_content = m.group(2).strip()
            timestamp_str = m.group(3).strip()
            message_count = 1
        # After line 492 where it says "elif i == 2:"
        elif i == 2:  # ✅ NEW: "• From X: msg (time, date)"
            sender_name = m.group(1).strip()
            message_content = m.group(2).strip()
            timestamp_str = m.group(3).strip()
            date_str = m.group(4).strip()  # ✅ Got the date!
            message_count = 1
            print(f"✅ EXTRACTED: sender={sender_name}, date={date_str}, time={timestamp_str}")
        else:  # simple 2-group forms
            sender_name = m.group(1).strip()
            message_content = m.group(2).strip() if len(m.groups()) >= 2 else ""
            timestamp_str = "recent"
            message_count = 1
        break

    if not sender_name:
        print(f"❌ NO SENDER FOUND in line: {line[:80]}")
        return None

    # --- recency detection ---
    recency = "this_week"  # Default

    # 1. Check section markers in ORIGINAL LINE
    if "TODAY:" in line or "📅 TODAY:" in line:
        recency = "today"
        print(f"✅ Message marked as TODAY (section marker)")
    elif "YESTERDAY:" in line or "📅 YESTERDAY:" in line:
        recency = "yesterday"
        print(f"✅ Message marked as YESTERDAY (section marker)")
    else:
        # 2. Try to parse date from extracted date_str OR timestamp
        try:
            # Use extracted date_str if we have it
            date_to_check = date_str or timestamp_str or ""
            
            # Look for ISO date YYYY-MM-DD format
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", date_to_check)
            
            if date_match:
                date_part = date_match.group(1)
                today_iso = datetime.utcnow().date().isoformat()
                yest_iso = (datetime.utcnow() - timedelta(days=1)).date().isoformat()
                
                print(f"🔍 Comparing dates - Message: {date_part}, Today: {today_iso}, Yesterday: {yest_iso}")
                
                if date_part == today_iso:
                    recency = "today"
                    print(f"✅ Message classified as TODAY by date match")
                elif date_part == yest_iso:
                    recency = "yesterday"
                    print(f"✅ Message classified as YESTERDAY by date match")
                else:
                    # Calculate days difference
                    try:
                        msg_date = datetime.strptime(date_part, '%Y-%m-%d').date()
                        today_date = datetime.utcnow().date()
                        days_diff = (today_date - msg_date).days
                        
                        if days_diff <= 7:
                            recency = "this_week"
                            print(f"📅 Message is from this week ({days_diff} days ago)")
                        else:
                            recency = "older"
                            print(f"📅 Message is older ({days_diff} days ago)")
                    except Exception as e:
                        print(f"⚠️ Date calculation error: {e}")
            else:
                print(f"⚠️ No date found in: {date_to_check[:50]}")
        except Exception as e:
            print(f"❌ Date parsing error: {e}")
            import traceback
            traceback.print_exc()

    print(f"📊 Final: sender={sender_name}, recency={recency}, content={message_content[:30]}")

    return {
        "sender_name": sender_name,
        "message_content": message_content,
        "timestamp_str": timestamp_str,
        "recency": recency,
        "message_count": message_count
    }


def classify_query_type(query: str, team_members: List[str] = None) -> str:
    """🆕 ENHANCED: More comprehensive query classification"""
    
    query_lower = query.lower()
    team_members = team_members or []
    
    # 🆕 NEW: Specific field queries (created_at, due_date, status, etc.)
    field_specific_patterns = [
        r"(what|when).*created.*date",
        r"(what|when).*due.*date", 
        r"(what|show).*status",
        r"(what|show).*priority",
        r"(what|show).*description",
        r"when.*task.*created",
        r"when.*task.*due",
        r"what.*task.*status",
        r"specific task",
        r"task.*named",
        r"task.*called"
    ]
    
    for pattern in field_specific_patterns:
        if re.search(pattern, query_lower):
            print(f"🎯 FIELD-SPECIFIC QUERY MATCH: {pattern}")
            return "field_specific_query"
    
    # 🆕 NEW: Date-specific message queries
    date_message_patterns = [
        r"message.*september.*\d+",
        r"message.*\d{4}-\d{2}-\d{2}",
        r"message.*yesterday",
        r"message.*last.*week",
        r"message.*last.*month"
    ]
    
    for pattern in date_message_patterns:
        if re.search(pattern, query_lower):
            print(f"📅 DATE-SPECIFIC MESSAGE QUERY: {pattern}")
            return "date_message_query"
    
    # 🆕 NEW: Kanban-specific queries
    kanban_patterns = [
        r"kanban.*task",
        r"board.*task",
        r"kanban.*column",
        r"what.*on.*kanban",
        r"kanban.*status",
        r"show.*kanban"
    ]
    
    for pattern in kanban_patterns:
        if re.search(pattern, query_lower):
            print(f"📋 KANBAN QUERY MATCH: {pattern}")
            return "kanban_query"
    
    # 🆕 NEW: Attachment queries
    attachment_patterns = [
        r"attachment",
        r"file.*upload",
        r"document.*attach",
        r"what.*file",
        r"show.*attachment"
    ]
    
    for pattern in attachment_patterns:
        if re.search(pattern, query_lower):
            print(f"📎 ATTACHMENT QUERY MATCH: {pattern}")
            return "attachment_query"
    
    # Keep existing team task detection
    team_task_patterns = [
        r"show.*all.*team.*task",
        r"all.*team.*member.*task", 
        r"team.*task",
        r"show.*all.*management.*task",
        r"show.*all.*intern.*task",
        r"show.*all.*lead.*task",
        r"show.*all.*member.*task"
    ]
    
    for pattern in team_task_patterns:
        if re.search(pattern, query_lower):
            print(f"🏢 TEAM TASK PATTERN MATCH: {pattern}")
            return "team_task_query"
    
    # Keep existing strong task patterns
    strong_task_patterns = [
        r"what.*should.*complete",
        r"what.*should.*do",
        r"my.*task",
        r"my.*overdue",
        r"complete.*today",
        r"work.*today"
    ]
    
    for pattern in strong_task_patterns:
        if re.search(pattern, query_lower):
            print(f"🎯 STRONG TASK PATTERN MATCH: {pattern}")
            return "task_query"
    
    # Keep existing strong message patterns
    strong_message_patterns = [
        r"did.*get.*message",
        r"any.*message.*from",
        r"got.*any.*message",
        r"hear.*from"
    ]
    
    for pattern in strong_message_patterns:
        if re.search(pattern, query_lower):
            print(f"💬 STRONG MESSAGE PATTERN MATCH: {pattern}")
            return "message_query"
    
    # Default scoring logic (keep existing)
    task_keywords = ["task", "work", "complete", "priority", "due"]
    message_keywords = ["message", "chat", "said", "told"]
    
    task_score = sum(1 for kw in task_keywords if kw in query_lower)
    message_score = sum(1 for kw in message_keywords if kw in query_lower)
    
    if task_score >= message_score and task_score > 0:
        return "task_query"
    elif message_score > 0:
        return "message_query"
    else:
        return "general_query"
    


def get_rag_response(query: str, user_context: str = ""):
    """Main RAG response function with enhanced routing"""
    
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
    
    # 🆕 NEW: Route to appropriate handler
    if query_type == "field_specific_query":
        print("🔍 Generating FIELD-SPECIFIC response")
        return generate_field_specific_response(query, parsed_data)
    
    elif query_type == "kanban_query":
        print("📋 Generating KANBAN response")
        return generate_kanban_response(query, parsed_data)
    
    elif query_type == "date_message_query":
        print("📅 Generating DATE-SPECIFIC MESSAGE response")
        return generate_date_message_response(query, parsed_data)
    
    elif query_type == "attachment_query":
        # You'll need to implement this based on your attachment data structure
        print("📎 Generating ATTACHMENT response")
        return "📎 Attachment queries are being processed..."
    
    elif query_type == "team_task_query":
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
    """🆕 ENHANCED: More professional overdue response with full details"""
    
    count = len(overdue_tasks)
    print(f"🚨 Processing {count} overdue tasks")
    
    response_parts = [
        f"🚨 **CRITICAL ALERT: {count} Overdue Task{'s' if count > 1 else ''}**",
        "",
        "**Status:** Your schedule requires immediate attention.",
        "**Action Required:** Please prioritize the following tasks:",
        ""
    ]
    
    # Show ALL overdue tasks with complete details
    for i, task in enumerate(overdue_tasks, 1):
        task_name = task['task_name']
        due_date = task['due_date']
        priority = task['priority']
        status = task['status']
        created_date = task.get('created_date', 'Unknown')
        task_id = task.get('task_id', 'N/A')
        
        # Calculate days overdue
        if due_date != "No date":
            try:
                due = datetime.strptime(due_date, '%Y-%m-%d')
                today = datetime.now()
                days_overdue = (today - due).days
            except:
                days_overdue = 0
        else:
            days_overdue = 0
        
        priority_emoji = "🔴" if priority == "High" else "🟡" if priority == "Medium" else "🟢"
        
        response_parts.append(f"""
**{i}. {task_name}** {priority_emoji}
   • **Due Date:** {due_date} ⚠️ ({days_overdue} days overdue)
   • **Priority:** {priority}
   • **Status:** {status}
   • **Created:** {created_date}
   • **Task ID:** {task_id}
""".strip())
    
    response_parts.extend([
        "",
        "---",
        "**📋 Immediate Action Plan:**",
        f"1️⃣ **Start immediately with:** '{overdue_tasks[0]['task_name']}'",
        "2️⃣ **Clear your calendar** to focus on overdue items",
        "3️⃣ **Notify stakeholders** about any delays",
        "4️⃣ **Request deadline extensions** if needed",
        "",
        "**💡 Professional Tip:** Tackle high-priority overdue tasks first, then work chronologically by due date.",
        "",
        f"**📊 Overview:** {count} overdue, {sum(1 for t in overdue_tasks if t['priority'] == 'High')} high priority"
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
                               key=lambda x: x['due'] if x['due'] not in ('No date', 'No due date') else '2999-12-31'
)
        
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


def generate_field_specific_response(query: str, parsed_data: Dict[str, Any]) -> str:
    """🆕 NEW: Handle queries about specific task fields"""
    
    print("🔍 Generating FIELD-SPECIFIC response")
    
    query_lower = query.lower()
    
    # Extract task name from query
    task_name_match = re.search(r'task.*"([^"]+)"', query_lower) or \
                     re.search(r'task.*called\s+([^\?]+)', query_lower) or \
                     re.search(r'task.*named\s+([^\?]+)', query_lower)
    
    target_task_name = task_name_match.group(1).strip() if task_name_match else None
    
    if not target_task_name:
        return """❌ **Please specify which task you're asking about.**

**Try asking like:**
- "What is the created date for my task 'Project Proposal'?"
- "When is 'Bug Fix' task due?"
- "What is the status of my task 'Code Review'?"
"""
    
    # Search for the task in parsed data
    all_tasks = (parsed_data["tasks"]["overdue"] + 
                parsed_data["tasks"]["today"] + 
                parsed_data["tasks"]["upcoming"])
    
    matching_task = None
    for task in all_tasks:
        if target_task_name.lower() in task["task_name"].lower():
            matching_task = task
            break
    
    if not matching_task:
        return f"""❌ **Task '{target_task_name}' not found in your active tasks.**

**Possible reasons:**
- Task name spelling doesn't match exactly
- Task is already completed
- Task belongs to a different user

**Try:** "Show all my tasks" to see your complete task list."""
    
    # Determine what field user is asking about
    response_parts = [f"📋 **Task Details: '{matching_task['task_name']}'**", ""]
    
    if "created" in query_lower or "creation date" in query_lower:
        response_parts.append(f"🗓️ **Created:** {matching_task.get('created_date', 'Date not available')}")
    
    if "due" in query_lower:
        response_parts.append(f"📅 **Due Date:** {matching_task['due_date']}")
    
    if "status" in query_lower:
        response_parts.append(f"📊 **Status:** {matching_task['status']}")
    
    if "priority" in query_lower:
        response_parts.append(f"🎯 **Priority:** {matching_task['priority']}")
    
    # If no specific field mentioned, show all details
    if not any(word in query_lower for word in ["created", "due", "status", "priority"]):
        response_parts.extend([
            f"📊 **Status:** {matching_task['status']}",
            f"🎯 **Priority:** {matching_task['priority']}",
            f"📅 **Due Date:** {matching_task['due_date']}",
            f"⏰ **Urgency:** {matching_task['urgency']}",
            f"🗓️ **Created:** {matching_task.get('created_date', 'Date not available')}"
        ])
    
    return "\n".join(response_parts)


def generate_kanban_response(query: str, parsed_data: Dict[str, Any]) -> str:
    """🆕 NEW: Handle Kanban-specific queries"""
    
    print("📋 Generating KANBAN response")
    
    # This would need kanban-specific data in parsed_data
    # You'll need to enhance parse_user_context to include kanban column info
    
    return """📋 **Your Kanban Board Overview**

**Note:** For detailed Kanban information, please use the Kanban board view directly.

**What I can help with:**
- "Show all my tasks" (includes Kanban tasks)
- "Show my overdue tasks" (includes Kanban)
- "What should I complete today?" (includes Kanban priorities)

**Try the Kanban board for:**
- Visual column organization
- Drag-and-drop task management
- Attachment viewing
- Detailed task cards"""


def generate_date_message_response(query: str, parsed_data: Dict[str, Any]) -> str:
    """🆕 NEW: Handle date-specific message queries"""
    
    print("📅 Generating DATE-SPECIFIC MESSAGE response")
    
    messages = parsed_data["messages"]
    query_lower = query.lower()
    
    # 🔧 FIXED: Better date extraction with multiple patterns
    target_date = None
    
    # Pattern 1: "October 7, 2025" or "October 7 2025"
    month_match = re.search(r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d+),?\s*(\d{4})?', query_lower)
    
    if month_match:
        month_name = month_match.group(1)
        day = month_match.group(2).zfill(2)
        year = month_match.group(3) or str(datetime.now().year)
        
        # Convert month name to number
        month_map = {
            'january': '01', 'february': '02', 'march': '03', 'april': '04',
            'may': '05', 'june': '06', 'july': '07', 'august': '08',
            'september': '09', 'october': '10', 'november': '11', 'december': '12'
        }
        month_num = month_map.get(month_name, '01')
        target_date = f"{year}-{month_num}-{day}"
        print(f"✅ Extracted date from month name: {target_date}")
    
    # Pattern 2: ISO format "2025-09-06"
    elif re.search(r'(\d{4})-(\d{2})-(\d{2})', query_lower):
        date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', query_lower)
        target_date = date_match.group(0)
        print(f"✅ Extracted ISO date: {target_date}")
    
    # Pattern 3: "10/7/2025" or "10/7/25"
    elif re.search(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', query_lower):
        date_match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', query_lower)
        month = date_match.group(1).zfill(2)
        day = date_match.group(2).zfill(2)
        year = date_match.group(3)
        if len(year) == 2:
            year = "20" + year
        target_date = f"{year}-{month}-{day}"
        print(f"✅ Extracted slash date: {target_date}")
    
    if not target_date:
        print("❌ Could not parse date from query")
        return """❌ **Couldn't parse the date from your query.**

Try asking like:
- "Did I get any messages on October 7, 2025?"
- "Show messages from 2025-10-07"
- "Messages from 10/7/2025"
"""
    
    print(f"🔍 Searching for messages on: {target_date}")
    
    # 🔧 FIXED: Check if query says "on" (specific day) vs "from" (date range)
    is_specific_day = " on " in query_lower or "messages on" in query_lower
    is_date_range = " from " in query_lower or "since" in query_lower
    
    # 🔧 FIXED: Search ALL message categories with better date matching
    all_messages = (
        messages.get("today", []) + 
        messages.get("yesterday", []) + 
        messages.get("this_week", [])
    )
    
    print(f"📊 Total messages to search: {len(all_messages)}")
    
    # Filter messages for target date
    if is_specific_day:
        # ONLY that specific day
        date_messages = []
        for msg in all_messages:
            msg_date_str = msg.get("timestamp_str", "")
            date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', msg_date_str)
            
            if date_match:
                msg_date = date_match.group(0)
                if msg_date == target_date:
                    date_messages.append(msg)
                    print(f"  ✅ MATCH! Added message from {msg.get('sender_name')}")
    else:
        # FROM that date onwards (date range)
        date_messages = []
        for msg in all_messages:
            msg_date_str = msg.get("timestamp_str", "")
            date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', msg_date_str)
            
            if date_match:
                msg_date = date_match.group(0)
                if msg_date >= target_date:  # All messages from this date forward
                    date_messages.append(msg)
                    print(f"  ✅ RANGE MATCH! Added message from {msg.get('sender_name')}")
    
    print(f"📊 Found {len(date_messages)} messages for {target_date}")
    
    if date_messages:
        date_type = "on" if is_specific_day else "since"
        response_parts = [
            f"📧 **Messages {date_type} {target_date}:**",
            ""
        ]
        
        for msg in date_messages:
            time = msg.get("timestamp_str", "Unknown time")
            sender = msg.get("sender_name", "Unknown")
            content = msg.get("message_content", "")
            
            # Clean up time display if it contains the date
            time_only = re.sub(r'\d{4}-\d{2}-\d{2}', '', time).strip(' ,')
            
            response_parts.append(f"• [{time_only}] **{sender}**: {content}")
        
        # Add summary
        response_parts.extend([
            "",
            f"📊 **Total**: {len(date_messages)} message{'s' if len(date_messages) != 1 else ''}"
        ])
        
        return "\n".join(response_parts)
    else:
        date_type = "on" if is_specific_day else "since"
        return f"""❌ **No messages found {date_type} {target_date}**

**Possible reasons:**
- No messages were sent/received on this date
- Messages may have been archived or deleted
- The date is outside the message history range

**Try:**
- Checking a different date
- Asking "Show all my messages" to see available dates
- Verifying the date format (October 7, 2025)
"""

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