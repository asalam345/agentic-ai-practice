from langchain.agents import create_agent  # This is now the correct import!
from langchain.tools import tool
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
import json

load_dotenv()

FILE_NAME = "conversation_summary.txt"

state = {
    "messages": [],
    "token": None,
}

users = {
    "alex": {
        "username": "alex",
        "password": "1234"
    },
    "bob": {
        "username": "bob",
        "password": "4321"
    }
}

personal_data = {}

def write_json(filename, data):
    """Saves a Python dictionary or list to a JSON file."""
    try:
        with open(filename, 'w', encoding='utf-8') as file:
            json.dump(data, file, indent=4)
        print(f"Data successfully saved to {filename}")
    except IOError as e:
        print(f"An error occurred while writing JSON: {e}")
        
def read_json(filename):
    """Reads a JSON file and returns the parsed Python object."""
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        return "Error: JSON file not found."
    except json.JSONDecodeError:
        return "Error: Failed to decode JSON. Check if the file format is valid."
    except IOError as e:
        return f"An error occurred: {e}"

@tool
def get_personal_data() -> str:
    """Fetch personal data for a given name. Only available to authenticated users."""
    print(f"[TOOL] 🔐 Accessing personal data...")
    if state["token"] in personal_data:
        return personal_data[state["token"]]
    return "You do not have any personal data. Add some personal data first."

@tool
def add_personal_data(data: str) -> str:
    """Only available to authenticated users."""
    print(f"[TOOL] 🔐 Adding personal data for {state['token']}...")
    if state["token"] in personal_data:
        personal_data[state["token"]] = personal_data[state["token"]] + data
        write_json("personal_data.json", personal_data)
        return f"Personal data for {state['token']} added successfully."
    return "You do not have permission to add personal data. Please authenticate first."

@tool
def login_user(username: str, password: str) -> str:
    """Pass username and password to authenticate the user."""
    print(f"[TOOL] 🔐 Authenticating user username: {username} password: {password} ...")
    if username.lower() in users and users[username.lower()]["password"] == password:
        state["token"] = username.lower()
        if state["token"] not in personal_data:
            personal_data[state["token"]] = ""
            write_json("personal_data.json", personal_data)
        return f"User {username} authenticated successfully. You are now logged in."
    return "Invalid username or password. Please try again or register if you don't have an account."

@tool
def logout_user() -> str:
    """Logout the current user."""
    print(f"[TOOL] 🔐 Logging out user {state['token']}...")
    state["token"] = None
    return "User logged out successfully."

@tool
def register_user(username: str, password: str) -> str:
    """Register a new user with username and password."""
    print(f"[TOOL] 🔐 Registering user username: {username} password: {password} ...")
    if username.lower() in users:
        return "Username already exists. Please choose a different username."
    users[username.lower()] = {
        "username": username.lower(),
        "password": password
    }
    personal_data[username.lower()] = ""
    write_json("personal_data.json", personal_data)
    return f"User {username} registered successfully. You can now login to access personal data."

def load_conversation():
    print(f"[UTILITY] 📂 Loading conversation...")
    try:
        with open(FILE_NAME, 'r', encoding='utf-8') as file:
            content = file.read()
            if content:
                state["messages"] = [{"role": "user", "content": f"Previous conversation summary: {content}"}]
            else:
                state["messages"] = []
            return True
    except FileNotFoundError:
        print("No previous conversation found. Starting fresh.")
        state["messages"] = []
        return True
    except IOError as e:
        print(f"An error occurred while reading: {e}")
        return False

def save_conversation(summary: str):
    print(f"[UTILITY] 💾 Saving conversation...")
    try:
        with open(FILE_NAME, 'w', encoding='utf-8') as file:
            file.write(summary)
        print(f"Successfully written to {FILE_NAME}")
    except IOError as e:
        print(f"An error occurred while writing: {e}")
        return False
    return True

def summarize_context():
    print(f"[UTILITY] 🧠 Summarizing conversation context...")
    
    # Use Ollama for summarization
    llm_summary = ChatOpenAI(
        model="qwen3:8b",
        base_url="http://localhost:11434/v1",
        api_key="ollama",
        temperature=0.3,
    )
    
    # Prepare conversation text
    conversation_text = ""
    for msg in state["messages"]:
        role = msg["role"]
        content = msg["content"]
        conversation_text += f"{role}: {content}\n"
    
    response = llm_summary.invoke([
        {"role": "system", "content": "Summarize the following conversation in a concise manner. Make sure to write all the historic details about the conversation, including user inputs and assistant responses. The summary should be comprehensive enough to provide context for future interactions without needing to refer back to the original messages, but not unnecessarily large."},
        {"role": "user", "content": conversation_text}
    ])
    
    summary = response.content
    save_conversation(summary)
    return summary

def run_turn(user_input: str):
    
    # Summarize if conversation gets too long
    if len(state["messages"]) > 10:
        summary = summarize_context()
        state["messages"] = [{"role": "system", "content": f"Previous conversation summary: {summary}"}]
    
    state["messages"].append({"role": "user", "content": user_input})
    
    print(f"User Input: {user_input}")
    print(f"Current User Token: {state['token']}\n")
    
    # Select tools based on authentication state
    tools = []
    if state["token"]:
        tools = [get_personal_data, add_personal_data, logout_user]
    else:
        tools = [login_user, register_user]
    
    # Use Ollama model
    llm = ChatOpenAI(
        model="qwen3:8b",
        base_url="http://localhost:11434/v1",
        api_key="ollama",
        temperature=0.7,
    )
    
    # Create the agent with proper system prompt - using 'system_prompt' parameter
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt="""You are a helpful assistant that manages user authentication and personal data.

IMPORTANT RULES:
1. When a user provides username and password, you MUST use the login_user tool
2. When they want to register, use register_user tool
3. After login, you can use get_personal_data and add_personal_data tools
4. Always call the appropriate tool - don't just respond with text
5. If user says "logout", use logout_user tool

Respond naturally but always use tools when appropriate."""
    )
    
    # Invoke the agent
    result = agent.invoke({
        "messages": state["messages"]
    })
    
    # Extract the response
    last_message = result["messages"][-1]
    state["messages"].append({"role": "assistant", "content": last_message.content})
    
    print(f"AI Response: {last_message.content}")
    print("-" * 50)

if __name__ == "__main__":
    # Load conversation history
    load_conversation()
    
    # Load personal data
    personal_data_from_file = read_json("personal_data.json")
    print(f"Personal data from file: {personal_data_from_file}")
    if isinstance(personal_data_from_file, dict):
        personal_data.update(personal_data_from_file)
        print("Personal data loaded successfully.")
    
    print("\n" + "="*50)
    print("Chat started! Type 'exit' or 'quit' to end the conversation.")
    print("="*50 + "\n")
    
    while True:
        user_input = input("You: ")
        if user_input.lower() in ["exit", "quit"]:
            print("Exiting chat...")
            break
        run_turn(user_input)