from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from datetime import datetime
import json
import hashlib
from pathlib import Path
from enum import Enum
from typing import Dict, List, Optional, Any

# ============= CONFIGURATION =============
OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_MODEL = "qwen3:8b"  # or "llama3.2", "mistral", etc.
DATA_DIR = Path("workflow_data")
DATA_DIR.mkdir(exist_ok=True)

# File paths for persistent storage
USERS_FILE = DATA_DIR / "users.json"
TASKS_FILE = DATA_DIR / "tasks.json"
WORKFLOW_STATE_FILE = DATA_DIR / "workflow_state.json"
AUDIT_LOG_FILE = DATA_DIR / "audit_log.json"
MEMORY_DIR = DATA_DIR / "memories"
MEMORY_DIR.mkdir(exist_ok=True)

# Initialize FREE local LLM (uses Ollama, NOT OpenAI)
llm = ChatOpenAI(
    model=OLLAMA_MODEL,
    base_url=OLLAMA_BASE_URL,
    api_key="ollama",  # Dummy key - completely free!
    temperature=0.7,
)

# ============= ENUMS FOR STATE MANAGEMENT =============
class WorkflowState(Enum):
    AUTHENTICATED = "authenticated"
    UNAUTHENTICATED = "unauthenticated"
    TASK_MANAGEMENT = "task_management"
    DATA_ANALYSIS = "data_analysis"
    REPORTING = "reporting"
    ADMIN = "admin"

# ============= JSON FILE HELPERS =============
def read_json(file_path: Path, default: Any = None) -> Any:
    """Read JSON file safely"""
    if file_path.exists():
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return default if default is not None else {}
    return default if default is not None else {}

def write_json(file_path: Path, data: Any):
    """Write JSON file safely"""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
    except IOError as e:
        print(f"Error writing to {file_path}: {e}")

# ============= PERSISTENT MEMORY MANAGEMENT =============
class PersistentMemory:
    def __init__(self, username: str):
        self.username = username
        self.memory_file = MEMORY_DIR / f"{username}.json"
        self.conversation_history = []
        self.load_memory()
    
    def load_memory(self):
        """Load conversation memory from file"""
        data = read_json(self.memory_file, {'history': []})
        self.conversation_history = data.get('history', [])
    
    def save_memory(self):
        """Save conversation memory to file"""
        # Keep only last 100 messages to prevent unlimited growth
        write_json(self.memory_file, {'history': self.conversation_history[-100:]})
    
    def add_message(self, role: str, content: str):
        """Add message to memory"""
        self.conversation_history.append({
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat()
        })
        self.save_memory()
    
    def get_context(self, limit: int = 10) -> str:
        """Get recent conversation context"""
        recent = self.conversation_history[-limit:]
        context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in recent])
        return context
    
    def clear(self):
        """Clear conversation memory"""
        self.conversation_history = []
        self.save_memory()

# ============= STATE MANAGER =============
class StateManager:
    def __init__(self, username: str):
        self.username = username
        self.current_state = WorkflowState.UNAUTHENTICATED
        self.context_data = {}
        self.load_state()
    
    def load_state(self):
        """Load workflow state from file"""
        all_states = read_json(WORKFLOW_STATE_FILE, {})
        user_state = all_states.get(self.username, {})
        if user_state:
            try:
                self.current_state = WorkflowState(user_state.get('current_state', 'unauthenticated'))
            except ValueError:
                self.current_state = WorkflowState.UNAUTHENTICATED
            self.context_data = user_state.get('context_data', {})
    
    def save_state(self):
        """Save workflow state to file"""
        all_states = read_json(WORKFLOW_STATE_FILE, {})
        all_states[self.username] = {
            'current_state': self.current_state.value,
            'context_data': self.context_data,
            'last_updated': datetime.now().isoformat()
        }
        write_json(WORKFLOW_STATE_FILE, all_states)
    
    def transition_to(self, new_state: WorkflowState, context_update: Dict = None):
        """Transition to a new workflow state"""
        old_state = self.current_state
        self.current_state = new_state
        if context_update:
            self.context_data.update(context_update)
        self.save_state()
        
        # Log state transition
        self.log_audit(f"State transition: {old_state.value} -> {new_state.value}")
        return f"Workflow state changed from {old_state.value} to {new_state.value}"
    
    def log_audit(self, action: str, details: str = ""):
        """Log actions to audit trail"""
        all_logs = read_json(AUDIT_LOG_FILE, [])
        all_logs.append({
            'username': self.username,
            'action': action,
            'details': details,
            'timestamp': datetime.now().isoformat()
        })
        # Keep only last 1000 logs
        write_json(AUDIT_LOG_FILE, all_logs[-1000:])

# ============= GLOBAL CONTEXT =============
_current_username = None
_current_state_manager = None
_current_memory = None

def get_current_username():
    return _current_username

def get_state_manager():
    return _current_state_manager

def get_memory():
    return _current_memory

# ============= TOOL DEFINITIONS =============
@tool
def create_task(title: str, description: str, priority: str = "medium", due_date: str = None) -> str:
    """Create a new task with title, description, priority, and optional due date"""
    print(f"[TOOL] 📝 Creating task: {title}")
    
    username = get_current_username()
    if not username:
        return "You must be logged in to create tasks."
    
    all_tasks = read_json(TASKS_FILE, [])
    
    task_id = len(all_tasks) + 1
    task = {
        'id': task_id,
        'username': username,
        'title': title,
        'description': description,
        'status': 'pending',
        'priority': priority,
        'created_at': datetime.now().isoformat(),
        'due_date': due_date,
    }
    
    all_tasks.append(task)
    write_json(TASKS_FILE, all_tasks)
    
    return f"✅ Task '{title}' created successfully with ID: {task_id}"

@tool
def list_tasks(status: str = None, priority: str = None) -> str:
    """List all tasks, optionally filtered by status or priority"""
    print(f"[TOOL] 📋 Listing tasks")
    
    username = get_current_username()
    if not username:
        return "You must be logged in to view tasks."
    
    all_tasks = read_json(TASKS_FILE, [])
    
    # Filter tasks for current user
    user_tasks = [t for t in all_tasks if t.get('username') == username]
    
    # Apply filters
    if status:
        user_tasks = [t for t in user_tasks if t.get('status') == status]
    if priority:
        user_tasks = [t for t in user_tasks if t.get('priority') == priority]
    
    if not user_tasks:
        return "📭 No tasks found."
    
    result = "📋 Your Tasks:\n" + "="*40 + "\n"
    for task in user_tasks:
        status_icon = "✅" if task['status'] == 'completed' else "🔄" if task['status'] == 'in_progress' else "⏳"
        result += f"{status_icon} [{task['id']}] {task['title']}\n"
        result += f"   Status: {task['status']} | Priority: {task['priority']}\n"
        if task.get('due_date'):
            result += f"   Due: {task['due_date']}\n"
        result += "-"*40 + "\n"
    
    return result

@tool
def update_task_status(task_id: int, new_status: str) -> str:
    """Update the status of a task (pending, in_progress, completed, cancelled)"""
    print(f"[TOOL] ✏️ Updating task {task_id}")
    
    username = get_current_username()
    if not username:
        return "You must be logged in to update tasks."
    
    all_tasks = read_json(TASKS_FILE, [])
    
    for task in all_tasks:
        if task.get('id') == task_id and task.get('username') == username:
            old_status = task['status']
            task['status'] = new_status
            write_json(TASKS_FILE, all_tasks)
            return f"✅ Task {task_id} status updated from '{old_status}' to '{new_status}'"
    
    return f"❌ Task {task_id} not found or you don't have permission."

@tool
def analyze_my_tasks() -> str:
    """Analyze your tasks and provide productivity insights"""
    print(f"[TOOL] 📊 Analyzing tasks")
    
    username = get_current_username()
    if not username:
        return "You must be logged in to analyze tasks."
    
    all_tasks = read_json(TASKS_FILE, [])
    user_tasks = [t for t in all_tasks if t.get('username') == username]
    
    if not user_tasks:
        return "No tasks to analyze. Create some tasks first!"
    
    # Calculate statistics
    total = len(user_tasks)
    completed = len([t for t in user_tasks if t.get('status') == 'completed'])
    in_progress = len([t for t in user_tasks if t.get('status') == 'in_progress'])
    pending = len([t for t in user_tasks if t.get('status') == 'pending'])
    
    # Priority breakdown
    high_priority = len([t for t in user_tasks if t.get('priority') == 'high'])
    medium_priority = len([t for t in user_tasks if t.get('priority') == 'medium'])
    low_priority = len([t for t in user_tasks if t.get('priority') == 'low'])
    
    completion_rate = (completed / total * 100) if total > 0 else 0
    
    result = f"""
📊 TASK ANALYTICS REPORT
{'='*40}
User: {username}
Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}

📈 SUMMARY:
• Total Tasks: {total}
• Completed: {completed} ({completion_rate:.1f}%)
• In Progress: {in_progress}
• Pending: {pending}

🎯 PRIORITY BREAKDOWN:
• High Priority: {high_priority}
• Medium Priority: {medium_priority}
• Low Priority: {low_priority}

💡 INSIGHTS:
"""
    if completion_rate < 30:
        result += "• Focus on completing more tasks to improve productivity\n"
    elif completion_rate > 70:
        result += "• Excellent progress! Keep up the momentum\n"
    else:
        result += "• You're making steady progress. Consider prioritizing high-impact tasks\n"
    
    if high_priority > 5:
        result += "• You have many high-priority tasks. Consider delegating or reprioritizing\n"
    
    return result

@tool
def generate_weekly_report() -> str:
    """Generate a comprehensive weekly report of your tasks and productivity"""
    print(f"[TOOL] 📄 Generating weekly report")
    
    username = get_current_username()
    if not username:
        return "You must be logged in to generate reports."
    
    all_tasks = read_json(TASKS_FILE, [])
    user_tasks = [t for t in all_tasks if t.get('username') == username]
    
    if not user_tasks:
        return "No tasks to report. Create some tasks first!"
    
    # Calculate statistics
    total = len(user_tasks)
    completed = len([t for t in user_tasks if t.get('status') == 'completed'])
    in_progress = len([t for t in user_tasks if t.get('status') == 'in_progress'])
    pending = len([t for t in user_tasks if t.get('status') == 'pending'])
    
    # Completion by priority
    high_completed = len([t for t in user_tasks if t.get('priority') == 'high' and t.get('status') == 'completed'])
    high_total = len([t for t in user_tasks if t.get('priority') == 'high'])
    high_rate = (high_completed / high_total * 100) if high_total > 0 else 0
    
    report = f"""
{'='*50}
📊 WEEKLY PRODUCTIVITY REPORT
{'='*50}
User: {username}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

📈 OVERALL METRICS:
{'─'*40}
Total Tasks:        {total}
Completed:          {completed} ({completed/total*100:.1f}%)
In Progress:        {in_progress}
Pending:            {pending}

🎯 PRIORITY PERFORMANCE:
{'─'*40}
High Priority Tasks:
  • Total: {high_total}
  • Completed: {high_completed} ({high_rate:.1f}%)

💡 RECOMMENDATIONS:
{'─'*40}
"""
    if high_rate < 50 and high_total > 0:
        report += "• ⚠️  Focus on completing high-priority tasks first\n"
    if pending > 10:
        report += "• 📋 Too many pending tasks - consider breaking them down\n"
    if in_progress > 5:
        report += "• 🎯 Limit work in progress to 3-4 tasks for better focus\n"
    
    report += f"""
{'='*50}
Keep up the good work! 🚀
{'='*50}
"""
    return report

@tool
def set_workflow_state(target_state: str) -> str:
    """Manually set the workflow state (authenticated, task_management, data_analysis, reporting)"""
    print(f"[TOOL] 🔄 Setting workflow state to {target_state}")
    
    state_manager = get_state_manager()
    if not state_manager:
        return "You must be logged in to change workflow state."
    
    try:
        new_state = WorkflowState(target_state.lower())
        return state_manager.transition_to(new_state)
    except ValueError:
        return f"Invalid state. Available states: {[s.value for s in WorkflowState]}"

@tool
def get_workflow_status() -> str:
    """Get the current workflow state and context"""
    state_manager = get_state_manager()
    if not state_manager:
        return "Not logged in. Please login first."
    
    memory = get_memory()
    context = memory.get_context(5) if memory else "No memory available"
    
    return f"""
Current Workflow Status:
• State: {state_manager.current_state.value}
• User: {state_manager.username}
• Messages in memory: {len(memory.conversation_history) if memory else 0}
• Context data: {json.dumps(state_manager.context_data, indent=2)}
"""

# ============= AUTHENTICATION TOOLS =============
@tool
def login_user(username: str, password: str) -> str:
    """Authenticate user with username and password"""
    print(f"[TOOL] 🔐 Login attempt: {username}")
    
    users = read_json(USERS_FILE, {})
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    if username in users and users[username]['password_hash'] == password_hash:
        # Set global context
        global _current_username, _current_state_manager, _current_memory
        _current_username = username
        _current_state_manager = StateManager(username)
        _current_memory = PersistentMemory(username)
        
        # Transition to authenticated state
        role = users[username].get('role', 'user')
        _current_state_manager.transition_to(WorkflowState.AUTHENTICATED, {'role': role})
        
        return f"✅ Welcome back {username}! You are now logged in as {role}."
    
    return "❌ Invalid username or password."

@tool
def register_user(username: str, password: str) -> str:
    """Register a new user account"""
    print(f"[TOOL] 📝 Registering new user: {username}")
    
    users = read_json(USERS_FILE, {})
    
    if username in users:
        return f"❌ Username '{username}' already exists."
    
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    users[username] = {
        'username': username,
        'password_hash': password_hash,
        'role': 'user',
        'created_at': datetime.now().isoformat(),
        'is_active': True
    }
    
    write_json(USERS_FILE, users)
    return f"✅ User '{username}' registered successfully! You can now login."

@tool
def logout_user() -> str:
    """Logout current user"""
    print(f"[TOOL] 🚪 Logging out")
    
    global _current_username, _current_state_manager, _current_memory
    if _current_state_manager:
        _current_state_manager.transition_to(WorkflowState.UNAUTHENTICATED)
    
    _current_username = None
    _current_state_manager = None
    _current_memory = None
    
    return "✅ You have been logged out successfully."

# ============= WORKFLOW ORCHESTRATOR =============
class WorkflowOrchestrator:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            api_key="ollama",
            temperature=0.7,
        )
    
    def get_tools_for_state(self, state: WorkflowState):
        """Return available tools based on current workflow state"""
        if state == WorkflowState.UNAUTHENTICATED:
            return [login_user, register_user]
        
        elif state == WorkflowState.AUTHENTICATED:
            return [create_task, list_tasks, update_task_status, 
                   analyze_my_tasks, generate_weekly_report,
                   set_workflow_state, get_workflow_status, logout_user]
        
        elif state == WorkflowState.TASK_MANAGEMENT:
            return [create_task, list_tasks, update_task_status, 
                   analyze_my_tasks, set_workflow_state, get_workflow_status, logout_user]
        
        elif state == WorkflowState.DATA_ANALYSIS:
            return [analyze_my_tasks, generate_weekly_report, list_tasks,
                   set_workflow_state, get_workflow_status, logout_user]
        
        elif state == WorkflowState.REPORTING:
            return [generate_weekly_report, analyze_my_tasks, list_tasks,
                   set_workflow_state, get_workflow_status, logout_user]
        
        elif state == WorkflowState.ADMIN:
            return [create_task, list_tasks, update_task_status, analyze_my_tasks,
                   generate_weekly_report, set_workflow_state, get_workflow_status, logout_user]
        
        return [login_user, register_user]
    
    def get_system_prompt(self, state: WorkflowState) -> str:
        """Generate contextual system prompt based on workflow state"""
        prompts = {
            WorkflowState.UNAUTHENTICATED: """You are a workflow assistant. The user is not logged in.
            Guide them to login or register using the tools available.
            Ask for username and password if needed.
            """,
            
            WorkflowState.AUTHENTICATED: """You are a workflow assistant. User is logged in.
            Available: create tasks, list tasks, update status, analyze tasks, generate reports.
            Suggest switching to specialized states for better focus.
            """,
            
            WorkflowState.TASK_MANAGEMENT: """You are a task management specialist.
            Focus on helping user create, organize, and track tasks efficiently.
            """,
            
            WorkflowState.DATA_ANALYSIS: """You are a data analyst.
            Provide insights on task completion, productivity patterns, and priorities.
            """,
            
            WorkflowState.REPORTING: """You are a reporting specialist.
            Generate comprehensive reports about tasks and productivity.
            """,
            
            WorkflowState.ADMIN: """You are an admin assistant with full access.
            Help with all features: task management, analytics, and reporting.
            """
        }
        return prompts.get(state, "You are a helpful workflow assistant.")
    
    def process_turn(self, user_input: str) -> str:
        """Process a single interaction turn with state awareness"""
        
        if not _current_username:
            tools = [login_user, register_user]
            system_prompt = self.get_system_prompt(WorkflowState.UNAUTHENTICATED)
        else:
            state_manager = get_state_manager()
            tools = self.get_tools_for_state(state_manager.current_state)
            system_prompt = self.get_system_prompt(state_manager.current_state)
        
        # Create agent with state-specific configuration
        agent = create_agent(
            model=self.llm,
            tools=tools,
            system_prompt=system_prompt
        )
        
        # Prepare messages with memory
        messages = []
        if get_memory():
            for msg in get_memory().conversation_history[-5:]:
                if msg['role'] == 'user':
                    messages.append(HumanMessage(content=msg['content']))
                else:
                    messages.append(AIMessage(content=msg['content']))
        
        messages.append(HumanMessage(content=user_input))
        
        # Invoke agent
        result = agent.invoke({"messages": messages})
        response = result["messages"][-1].content
        
        # Store in memory
        if get_memory():
            get_memory().add_message("user", user_input)
            get_memory().add_message("assistant", response)
        
        return response

# ============= MAIN APPLICATION =============
def main():
    """Main application entry point"""
    
    # Create default admin user if no users exist
    users = read_json(USERS_FILE, {})
    if not users:
        admin_hash = hashlib.sha256("admin123".encode()).hexdigest()
        users['admin'] = {
            'username': 'admin',
            'password_hash': admin_hash,
            'role': 'admin',
            'created_at': datetime.now().isoformat(),
            'is_active': True
        }
        write_json(USERS_FILE, users)
        print("✅ Default admin user created: admin / admin123")
    
    # Initialize orchestrator
    orchestrator = WorkflowOrchestrator()
    
    print("\n" + "="*60)
    print("🤖 ADVANCED WORKFLOW AGENTIC SYSTEM")
    print("="*60)
    print("\n📚 Available Workflow States:")
    for state in WorkflowState:
        print(f"   • {state.value}")
    print("\n💡 Commands: 'status', 'help', 'logout', 'exit'")
    print("="*60 + "\n")
    
    while True:
        try:
            user_input = input("You: ").strip()
            
            if user_input.lower() == 'exit':
                print("\n👋 Goodbye!")
                break
            
            elif user_input.lower() == 'status':
                if _current_state_manager:
                    print(f"\n✅ Logged in as: {_current_username}")
                    print(f"📊 Current State: {_current_state_manager.current_state.value}")
                    print(f"📝 Messages in memory: {len(_current_memory.conversation_history) if _current_memory else 0}")
                else:
                    print("\n❌ Not logged in")
                continue
            
            elif user_input.lower() == 'help':
                print("\n" + "="*50)
                print("📚 COMMAND GUIDE")
                print("="*50)
                print("\n🔐 AUTHENTICATION:")
                print("   • register <username> <password> - Create account")
                print("   • login <username> <password> - Login")
                print("   • logout - End session")
                print("\n📝 TASK MANAGEMENT:")
                print("   • create task <title> - Add new task")
                print("   • list tasks - View all tasks")
                print("   • update task <id> to <status> - Change status")
                print("\n📊 ANALYTICS & REPORTS:")
                print("   • analyze my tasks - Get insights")
                print("   • generate weekly report - Create report")
                print("\n🔄 WORKFLOW CONTROL:")
                print("   • set workflow state to <state> - Change mode")
                print("   • status - Check current state")
                print("="*50 + "\n")
                continue
            
            # Process the turn
            response = orchestrator.process_turn(user_input)
            print(f"\n🤖 Assistant: {response}\n")
            print("-"*60)
            
        except KeyboardInterrupt:
            print("\n\n👋 Exiting...")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")
            continue

if __name__ == "__main__":
    main()