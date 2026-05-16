import sqlite3
from pathlib import Path

# Database path
db_file = Path("workflow_data/workflow.db")

print(f"Checking database at: {db_file.absolute()}")
print(f"File exists: {db_file.exists()}")
print()

if db_file.exists():
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"Tables in database: {[t[0] for t in tables]}")
    print()
    
    # Check users table
    print("="*50)
    print("USERS TABLE")
    print("="*50)
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    
    if users:
        print(f"Found {len(users)} user(s):\n")
        for user in users:
            print(f"Username: {user[0]}")
            print(f"Password Hash: {user[1][:20]}...")  # Show first 20 chars only
            print(f"Role: {user[2]}")
            print(f"Created: {user[3]}")
            print(f"Active: {user[4]}")
            print("-"*30)
    else:
        print("No users found in database!")
    
    print()
    
    # Check for specific users
    print("="*50)
    print("USER SEARCH")
    print("="*50)
    
    for username in ['salam', 'barkat', 'admin']:
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        if user:
            print(f"✅ User '{username}' FOUND in database!")
        else:
            print(f"❌ User '{username}' NOT found in database!")
    
    # Check tasks table
    print()
    print("="*50)
    print("TASKS TABLE")
    print("="*50)
    cursor.execute("SELECT COUNT(*) FROM tasks")
    task_count = cursor.fetchone()[0]
    print(f"Total tasks: {task_count}")
    
    if task_count > 0:
        cursor.execute("SELECT id, username, title, status FROM tasks LIMIT 5")
        tasks = cursor.fetchall()
        for task in tasks:
            print(f"  Task {task[0]}: {task[2]} (User: {task[1]}, Status: {task[3]})")
    
    conn.close()
else:
    print("❌ Database file not found!")
    print(f"Current directory: {Path.cwd()}")
    print("Files in workflow_data:")
    import os
    if Path("workflow_data").exists():
        for f in os.listdir("workflow_data"):
            print(f"  - {f}")