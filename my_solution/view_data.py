import json
from pathlib import Path
from pprint import pprint

DATA_DIR = Path("workflow_data")

def view_all_data():
    """Display all data from the workflow system"""
    
    print("\n" + "="*60)
    print("📊 WORKFLOW DATA VIEWER")
    print("="*60)
    
    # 1. View Users
    users_file = DATA_DIR / "users.json"
    if users_file.exists():
        with open(users_file, 'r') as f:
            users = json.load(f)
        print("\n👥 USERS:")
        print("-" * 40)
        for username, data in users.items():
            print(f"  • {username}")
            print(f"    Role: {data.get('role', 'user')}")
            print(f"    Created: {data.get('created_at', 'N/A')}")
            print(f"    Active: {data.get('is_active', True)}")
    else:
        print("\n⚠️ No users found")
    
    # 2. View Tasks
    tasks_file = DATA_DIR / "tasks.json"
    if tasks_file.exists():
        with open(tasks_file, 'r') as f:
            tasks = json.load(f)
        print("\n📋 TASKS:")
        print("-" * 40)
        if tasks:
            for task in tasks:
                print(f"  • [{task['id']}] {task['title']}")
                print(f"    User: {task['username']}")
                print(f"    Status: {task['status']} | Priority: {task['priority']}")
                print(f"    Created: {task['created_at']}")
                if task.get('due_date'):
                    print(f"    Due: {task['due_date']}")
                print()
        else:
            print("  No tasks found")
    
    # 3. View Workflow States
    state_file = DATA_DIR / "workflow_state.json"
    if state_file.exists():
        with open(state_file, 'r') as f:
            states = json.load(f)
        print("\n🔄 WORKFLOW STATES:")
        print("-" * 40)
        for username, state in states.items():
            print(f"  • {username}: {state.get('current_state', 'unknown')}")
            print(f"    Last updated: {state.get('last_updated', 'N/A')}")
    
    # 4. View Audit Log (last 10 entries)
    audit_file = DATA_DIR / "audit_log.json"
    if audit_file.exists():
        with open(audit_file, 'r') as f:
            logs = json.load(f)
        print("\n📝 RECENT AUDIT LOGS (last 10):")
        print("-" * 40)
        for log in logs[-10:]:
            print(f"  • {log['timestamp']}")
            print(f"    User: {log['username']} | Action: {log['action']}")
            if log.get('details'):
                print(f"    Details: {log['details']}")
            print()
    
    # 5. View Conversation Memories
    memories_dir = DATA_DIR / "memories"
    if memories_dir.exists():
        print("\n💬 CONVERSATION MEMORIES:")
        print("-" * 40)
        memory_files = list(memories_dir.glob("*.json"))
        if memory_files:
            for mem_file in memory_files:
                with open(mem_file, 'r') as f:
                    memory = json.load(f)
                username = mem_file.stem
                msg_count = len(memory.get('history', []))
                print(f"  • {username}: {msg_count} messages stored")
        else:
            print("  No conversation memories found")
    
    print("\n" + "="*60)

def view_user_tasks(username: str):
    """View tasks for a specific user"""
    tasks_file = DATA_DIR / "tasks.json"
    if tasks_file.exists():
        with open(tasks_file, 'r') as f:
            tasks = json.load(f)
        
        user_tasks = [t for t in tasks if t.get('username') == username]
        
        print(f"\n📋 TASKS FOR USER: {username}")
        print("="*40)
        if user_tasks:
            for task in user_tasks:
                print(f"\n  ID: {task['id']}")
                print(f"  Title: {task['title']}")
                print(f"  Description: {task.get('description', 'No description')}")
                print(f"  Status: {task['status']}")
                print(f"  Priority: {task['priority']}")
                print(f"  Created: {task['created_at']}")
        else:
            print("  No tasks found")

def view_user_memory(username: str, limit: int = 10):
    """View conversation history for a user"""
    memory_file = DATA_DIR / "memories" / f"{username}.json"
    if memory_file.exists():
        with open(memory_file, 'r') as f:
            memory = json.load(f)
        
        history = memory.get('history', [])[-limit:]
        
        print(f"\n💬 LAST {len(history)} CONVERSATIONS FOR {username}:")
        print("="*40)
        for msg in history:
            print(f"\n  [{msg['timestamp']}]")
            print(f"  {msg['role']}: {msg['content'][:100]}...")
    else:
        print(f"No memory found for user: {username}")

def delete_all_data():
    """WARNING: Deletes all workflow data"""
    confirm = input("\n⚠️  This will delete ALL data. Type 'DELETE' to confirm: ")
    if confirm == "DELETE":
        import shutil
        if DATA_DIR.exists():
            shutil.rmtree(DATA_DIR)
            print("✅ All data deleted successfully!")
    else:
        print("❌ Deletion cancelled")

if __name__ == "__main__":
    while True:
        print("\n" + "="*40)
        print("DATA VIEWER MENU")
        print("="*40)
        print("1. View all data")
        print("2. View tasks for specific user")
        print("3. View conversation history for user")
        print("4. Delete all data (WARNING!)")
        print("5. Exit")
        
        choice = input("\nSelect option (1-5): ")
        
        if choice == '1':
            view_all_data()
        elif choice == '2':
            username = input("Enter username: ")
            view_user_tasks(username)
        elif choice == '3':
            username = input("Enter username: ")
            limit = input("Number of messages to show (default 10): ")
            limit = int(limit) if limit else 10
            view_user_memory(username, limit)
        elif choice == '4':
            delete_all_data()
        elif choice == '5':
            print("Goodbye!")
            break
        else:
            print("Invalid option")
        
        input("\nPress Enter to continue...")