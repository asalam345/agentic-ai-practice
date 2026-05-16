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
import sqlite3
from contextlib import contextmanager

# ============= CONFIGURATION =============
OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_MODEL = "qwen3:8b"  # or "llama3.2", "mistral", etc.
DATA_DIR = Path("workflow_data")
DATA_DIR.mkdir(exist_ok=True)

# Database file path
DB_FILE = DATA_DIR / "workflow.db"

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

# ============= DATABASE SETUP =============
def init_database():
    """Initialize SQLite database with all required tables"""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                created_at TIMESTAMP NOT NULL,
                is_active BOOLEAN DEFAULT 1
            )
        """)
        
        # Tasks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'pending',
                priority TEXT DEFAULT 'medium',
                created_at TIMESTAMP NOT NULL,
                due_date TIMESTAMP,
                FOREIGN KEY (username) REFERENCES users(username)
            )
        """)
        
        # Workflow state table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workflow_state (
                username TEXT PRIMARY KEY,
                current_state TEXT NOT NULL,
                context_data TEXT,
                last_updated TIMESTAMP NOT NULL,
                FOREIGN KEY (username) REFERENCES users(username)
            )
        """)
        
        # Audit log table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                timestamp TIMESTAMP NOT NULL
            )
        """)
        
        # Conversation memory table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                FOREIGN KEY (username) REFERENCES users(username)
            )
        """)
        
        # Create index for better query performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_username 
            ON tasks(username)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_username 
            ON audit_log(username)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_username 
            ON conversation_memory(username)
        """)
        
        conn.commit()

@contextmanager
def get_db():
    """Context manager for database connections"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# ============= DATABASE HELPERS =============
def create_default_admin():
    """Create default admin user if no users exist"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM users")
        result = cursor.fetchone()
        
        if result['count'] == 0:
            admin_hash = hashlib.sha256("admin123".encode()).hexdigest()
            cursor.execute("""
                INSERT INTO users (username, password_hash, role, created_at, is_active)
                VALUES (?, ?, ?, ?, ?)
            """, ('admin', admin_hash, 'admin', datetime.now().isoformat(), True))
            print("✅ Default admin user created: admin / admin123")

# ============= PERSISTENT MEMORY MANAGEMENT =============
class PersistentMemory:
    def __init__(self, username: str):
        self.username = username
        self.load_memory()
    
    def load_memory(self):
        """Load conversation memory from database"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT role, content, timestamp 
                FROM conversation_memory 
                WHERE username = ? 
                ORDER BY id DESC 
                LIMIT 100
            """, (self.username,))
            
            rows = cursor.fetchall()
            self.conversation_history = [
                {'role': row['role'], 'content': row['content'], 'timestamp': row['timestamp']}
                for row in reversed(rows)
            ]
    
    def add_message(self, role: str, content: str):
        """Add message to memory"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO conversation_memory (username, role, content, timestamp)
                VALUES (?, ?, ?, ?)
            """, (self.username, role, content, datetime.now().isoformat()))
            
            # Keep only last 100 messages per user
            cursor.execute("""
                DELETE FROM conversation_memory 
                WHERE id IN (
                    SELECT id FROM conversation_memory 
                    WHERE username = ? 
                    ORDER BY id DESC 
                    LIMIT -1 OFFSET 100
                )
            """, (self.username,))
        
        # Update local cache
        self.conversation_history.append({
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat()
        })
        if len(self.conversation_history) > 100:
            self.conversation_history = self.conversation_history[-100:]
    
    def get_context(self, limit: int = 10) -> str:
        """Get recent conversation context"""
        recent = self.conversation_history[-limit:]
        context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in recent])
        return context
    
    def clear(self):
        """Clear conversation memory"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM conversation_memory WHERE username = ?", (self.username,))
        self.conversation_history = []

# ============= STATE MANAGER =============
class StateManager:
    def __init__(self, username: str):
        self.username = username
        self.current_state = WorkflowState.UNAUTHENTICATED
        self.context_data = {}
        self.load_state()
    
    def load_state(self):
        """Load workflow state from database"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT current_state, context_data 
                FROM workflow_state 
                WHERE username = ?
            """, (self.username,))
            
            row = cursor.fetchone()
            if row:
                try:
                    self.current_state = WorkflowState(row['current_state'])
                except ValueError:
                    self.current_state = WorkflowState.UNAUTHENTICATED
                self.context_data = json.loads(row['context_data']) if row['context_data'] else {}
            else:
                self.current_state = WorkflowState.UNAUTHENTICATED
                self.context_data = {}
    
    def save_state(self):
        """Save workflow state to database"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO workflow_state 
                (username, current_state, context_data, last_updated)
                VALUES (?, ?, ?, ?)
            """, (
                self.username, 
                self.current_state.value, 
                json.dumps(self.context_data), 
                datetime.now().isoformat()
            ))
    
    def transition_to(self, new_state: WorkflowState, context_update: Dict = None):
        """Transition to a new workflow state"""
        old_state = self.current_state
        self.current_state = new_state
        if context_update:
            self.context_data.update(context_update)
        self.save_state()
        
        self.log_audit(f"State transition: {old_state.value} -> {new_state.value}")
        return f"Workflow state changed from {old_state.value} to {new_state.value}"
    
    def log_audit(self, action: str, details: str = ""):
        """Log actions to audit trail"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audit_log (username, action, details, timestamp)
                VALUES (?, ?, ?, ?)
            """, (self.username, action, details, datetime.now().isoformat()))
            
            cursor.execute("""
                DELETE FROM audit_log 
                WHERE id IN (
                    SELECT id FROM audit_log 
                    WHERE username = ? 
                    ORDER BY id DESC 
                    LIMIT -1 OFFSET 1000
                )
            """, (self.username,))

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

# ============= SIMPLE DIRECT TOOLS (NO LLM NEEDED) =============
def register_user_direct(username: str, password: str) -> str:
    """Direct registration function that doesn't rely on LLM tool calling"""
    print(f"[TOOL] 📝 Registering new user: {username}")
    
    if not username or not password:
        return "❌ Please provide both username and password."
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute("SELECT username FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            return f"❌ Username '{username}' already exists."
        
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        cursor.execute("""
            INSERT INTO users (username, password_hash, role, created_at, is_active)
            VALUES (?, ?, ?, ?, ?)
        """, (username, password_hash, 'user', datetime.now().isoformat(), True))
        
        return f"✅ User '{username}' registered successfully! You can now login with: login {username} {password}"

def login_user_direct(username: str, password: str) -> str:
    """Direct login function that doesn't rely on LLM tool calling"""
    print(f"[TOOL] 🔐 Login attempt: {username}")
    
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT username, role FROM users 
            WHERE username = ? AND password_hash = ? AND is_active = 1
        """, (username, password_hash))
        
        user = cursor.fetchone()
        
        if user:
            global _current_username, _current_state_manager, _current_memory
            _current_username = username
            _current_state_manager = StateManager(username)
            _current_memory = PersistentMemory(username)
            
            role = user['role']
            _current_state_manager.transition_to(WorkflowState.AUTHENTICATED, {'role': role})
            
            return f"✅ Welcome back {username}! You are now logged in as {role}."
    
    return "❌ Invalid username or password."

# ============= TOOL DEFINITIONS (For LLM) =============
@tool
def register_user(username: str, password: str) -> str:
    """Register a new user account with username and password"""
    return register_user_direct(username, password)

@tool
def login_user(username: str, password: str) -> str:
    """Authenticate user with username and password"""
    return login_user_direct(username, password)

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

@tool
def create_task(title: str, description: str = "", priority: str = "medium", due_date: str = None) -> str:
    """Create a new task with title, description, priority, and optional due date"""
    print(f"[TOOL] 📝 Creating task: {title}")
    
    username = get_current_username()
    if not username:
        return "You must be logged in to create tasks."
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tasks (username, title, description, priority, created_at, due_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (username, title, description, priority, datetime.now().isoformat(), due_date))
        
        task_id = cursor.lastrowid
    
    return f"✅ Task '{title}' created successfully with ID: {task_id}"

@tool
def list_tasks(status: str = None, priority: str = None) -> str:
    """List all tasks, optionally filtered by status or priority"""
    print(f"[TOOL] 📋 Listing tasks")
    
    username = get_current_username()
    if not username:
        return "You must be logged in to view tasks."
    
    with get_db() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM tasks WHERE username = ?"
        params = [username]
        
        if status:
            query += " AND status = ?"
            params.append(status)
        if priority:
            query += " AND priority = ?"
            params.append(priority)
        
        query += " ORDER BY id DESC"
        cursor.execute(query, params)
        user_tasks = cursor.fetchall()
    
    if not user_tasks:
        return "📭 No tasks found."
    
    result = "📋 Your Tasks:\n" + "="*40 + "\n"
    for task in user_tasks:
        status_icon = "✅" if task['status'] == 'completed' else "🔄" if task['status'] == 'in_progress' else "⏳"
        result += f"{status_icon} [{task['id']}] {task['title']}\n"
        result += f"   Status: {task['status']} | Priority: {task['priority']}\n"
        if task['due_date']:
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
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM tasks WHERE id = ? AND username = ?", (task_id, username))
        task = cursor.fetchone()
        
        if not task:
            return f"❌ Task {task_id} not found or you don't have permission."
        
        old_status = task['status']
        cursor.execute("UPDATE tasks SET status = ? WHERE id = ? AND username = ?", 
                      (new_status, task_id, username))
        
        return f"✅ Task {task_id} status updated from '{old_status}' to '{new_status}'"

@tool
def analyze_my_tasks() -> str:
    """Analyze your tasks and provide productivity insights"""
    print(f"[TOOL] 📊 Analyzing tasks")
    
    username = get_current_username()
    if not username:
        return "You must be logged in to analyze tasks."
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN priority = 'high' THEN 1 ELSE 0 END) as high_priority,
                SUM(CASE WHEN priority = 'medium' THEN 1 ELSE 0 END) as medium_priority,
                SUM(CASE WHEN priority = 'low' THEN 1 ELSE 0 END) as low_priority
            FROM tasks 
            WHERE username = ?
        """, (username,))
        
        stats = cursor.fetchone()
    
    if stats['total'] == 0:
        return "No tasks to analyze. Create some tasks first!"
    
    total = stats['total']
    completed = stats['completed'] or 0
    in_progress = stats['in_progress'] or 0
    pending = stats['pending'] or 0
    high_priority = stats['high_priority'] or 0
    medium_priority = stats['medium_priority'] or 0
    low_priority = stats['low_priority'] or 0
    
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
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN priority = 'high' AND status = 'completed' THEN 1 ELSE 0 END) as high_completed,
                SUM(CASE WHEN priority = 'high' THEN 1 ELSE 0 END) as high_total
            FROM tasks 
            WHERE username = ?
        """, (username,))
        
        stats = cursor.fetchone()
    
    if stats['total'] == 0:
        return "No tasks to report. Create some tasks first!"
    
    total = stats['total']
    completed = stats['completed'] or 0
    in_progress = stats['in_progress'] or 0
    pending = stats['pending'] or 0
    high_completed = stats['high_completed'] or 0
    high_total = stats['high_total'] or 0
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

# ============= WORKFLOW ORCHESTRATOR =============
class WorkflowOrchestrator:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            api_key="ollama",
            temperature=0.7,
        )
    
    def process_direct_command(self, user_input: str) -> str:
        """Process commands directly without LLM for registration/login"""
        user_input_lower = user_input.lower().strip()
        
        # Handle registration
        if user_input_lower.startswith("register"):
            parts = user_input.split()
            if len(parts) >= 3:
                username = parts[1]
                password = parts[2]
                return register_user_direct(username, password)
            else:
                return "❌ Usage: register <username> <password>"
        
        # Handle login
        if user_input_lower.startswith("login"):
            parts = user_input.split()
            if len(parts) >= 3:
                username = parts[1]
                password = parts[2]
                return login_user_direct(username, password)
            else:
                return "❌ Usage: login <username> <password>"
        
        return None  # Not a direct command
    
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
            IMPORTANT: To register, the user must type: register [username] [password]
            To login, the user must type: login [username] [password]
            Do not try to handle registration yourself - just tell them the command format.
            Available commands: register <username> <password>, login <username> <password>
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
        
        # First, check for direct commands (registration/login)
        direct_result = self.process_direct_command(user_input)
        if direct_result:
            return direct_result
        
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
    
    # Initialize database
    init_database()
    
    # Create default admin user if no users exist
    create_default_admin()
    
    # Initialize orchestrator
    orchestrator = WorkflowOrchestrator()
    
    print("\n" + "="*60)
    print("🤖 ADVANCED WORKFLOW AGENTIC SYSTEM (SQLite Edition)")
    print("="*60)
    print("\n📚 Available Workflow States:")
    for state in WorkflowState:
        print(f"   • {state.value}")
    print("\n💡 Commands:")
    print("   • register <username> <password> - Create new account")
    print("   • login <username> <password> - Login to existing account")
    print("   • status - Check current state")
    print("   • help - Show all commands")
    print("   • logout - Logout current user")
    print("   • exit - Exit application")
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
                print("   • register <username> <password> - Create new account")
                print("   • login <username> <password> - Login to existing account")
                print("   • logout - End session")
                print("\n📝 TASK MANAGEMENT (after login):")
                print("   • create task <title> - Add new task")
                print("   • list tasks - View all tasks")
                print("   • update task <id> to <status> - Change status")
                print("\n📊 ANALYTICS & REPORTS (after login):")
                print("   • analyze my tasks - Get insights")
                print("   • generate weekly report - Create report")
                print("\n🔄 WORKFLOW CONTROL (after login):")
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