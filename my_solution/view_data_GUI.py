import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk

class DataViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("Workflow Data Viewer")
        self.root.geometry("800x600")
        
        # Create notebook for tabs
        notebook = ttk.Notebook(root)
        notebook.pack(fill='both', expand=True)
        
        # Tasks Tab
        tasks_frame = ttk.Frame(notebook)
        notebook.add(tasks_frame, text="Tasks")
        self.create_tasks_view(tasks_frame)
        
        # Users Tab
        users_frame = ttk.Frame(notebook)
        notebook.add(users_frame, text="Users")
        self.create_users_view(users_frame)
        
        # Workflow States Tab
        states_frame = ttk.Frame(notebook)
        notebook.add(states_frame, text="Workflow States")
        self.create_states_view(states_frame)
        
        # Audit Log Tab
        audit_frame = ttk.Frame(notebook)
        notebook.add(audit_frame, text="Audit Log")
        self.create_audit_view(audit_frame)
    
    def create_tasks_view(self, parent):
        # Treeview for tasks
        columns = ('ID', 'User', 'Title', 'Status', 'Priority', 'Created')
        tree = ttk.Treeview(parent, columns=columns, show='headings')
        
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=120)
        
        # Load data
        tasks_file = Path("workflow_data/tasks.json")
        if tasks_file.exists():
            with open(tasks_file, 'r') as f:
                tasks = json.load(f)
                for task in tasks:
                    tree.insert('', 'end', values=(
                        task['id'],
                        task['username'],
                        task['title'],
                        task['status'],
                        task['priority'],
                        task['created_at'][:10]  # Just date
                    ))
        
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill='both', expand=True)
        scrollbar.pack(side=tk.RIGHT, fill='y')
    
    def create_users_view(self, parent):
        tree = ttk.Treeview(parent, columns=('Username', 'Role', 'Created', 'Active'), show='headings')
        
        for col in ('Username', 'Role', 'Created', 'Active'):
            tree.heading(col, text=col)
            tree.column(col, width=150)
        
        users_file = Path("workflow_data/users.json")
        if users_file.exists():
            with open(users_file, 'r') as f:
                users = json.load(f)
                for username, data in users.items():
                    tree.insert('', 'end', values=(
                        username,
                        data.get('role', 'user'),
                        data.get('created_at', 'N/A')[:10],
                        'Yes' if data.get('is_active', True) else 'No'
                    ))
        
        tree.pack(fill='both', expand=True)
    
    def create_states_view(self, parent):
        tree = ttk.Treeview(parent, columns=('User', 'State', 'Last Updated'), show='headings')
        
        for col in ('User', 'State', 'Last Updated'):
            tree.heading(col, text=col)
            tree.column(col, width=200)
        
        states_file = Path("workflow_data/workflow_state.json")
        if states_file.exists():
            with open(states_file, 'r') as f:
                states = json.load(f)
                for username, data in states.items():
                    tree.insert('', 'end', values=(
                        username,
                        data.get('current_state', 'unknown'),
                        data.get('last_updated', 'N/A')[:19]
                    ))
        
        tree.pack(fill='both', expand=True)
    
    def create_audit_view(self, parent):
        tree = ttk.Treeview(parent, columns=('Timestamp', 'User', 'Action', 'Details'), show='headings')
        
        tree.heading('Timestamp', text='Timestamp')
        tree.heading('User', text='User')
        tree.heading('Action', text='Action')
        tree.heading('Details', text='Details')
        
        tree.column('Timestamp', width=150)
        tree.column('User', width=100)
        tree.column('Action', width=200)
        tree.column('Details', width=300)
        
        audit_file = Path("workflow_data/audit_log.json")
        if audit_file.exists():
            with open(audit_file, 'r') as f:
                logs = json.load(f)
                for log in logs[-100:]:  # Last 100 logs
                    tree.insert('', 'end', values=(
                        log.get('timestamp', 'N/A')[:19],
                        log.get('username', 'N/A'),
                        log.get('action', 'N/A'),
                        log.get('details', '')
                    ))
        
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill='both', expand=True)
        scrollbar.pack(side=tk.RIGHT, fill='y')

if __name__ == "__main__":
    root = tk.Tk()
    app = DataViewer(root)
    root.mainloop()