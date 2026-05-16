import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from enum import Enum
import requests

# ============= OLLAMA DIRECT API CALLS (NO OPENAI) =============
class OllamaLLM:
    """Direct Ollama integration without OpenAI dependencies"""
    
    def __init__(self, model: str = "qwen3:8b", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url
        self.api_url = f"{base_url}/api/generate"
    
    def invoke(self, messages: List[Dict]) -> str:
        """Send messages to Ollama and get response"""
        
        # Convert messages to prompt format
        prompt = ""
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt += f"System: {content}\n\n"
            elif role == "user":
                prompt += f"User: {content}\n"
            elif role == "assistant":
                prompt += f"Assistant: {content}\n"
        
        prompt += "Assistant: "
        
        # Call Ollama API
        response = requests.post(
            self.api_url,
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "temperature": 0.7,
            }
        )
        
        if response.status_code == 200:
            return response.json().get("response", "")
        else:
            return f"Error: {response.status_code}"

# ============= SIMPLE AGENT WITHOUT LANGCHAIN =============
class SimpleAgent:
    """A simple agent that can use tools with Ollama"""
    
    def __init__(self, llm: OllamaLLM, tools: List, system_prompt: str = ""):
        self.llm = llm
        self.tools = {tool.name: tool for tool in tools}
        self.system_prompt = system_prompt
    
    def invoke(self, input_data: Dict) -> Dict:
        """Process input and return response"""
        messages = input_data.get("messages", [])
        
        # Add system prompt if provided
        if self.system_prompt:
            messages.insert(0, {"role": "system", "content": self.system_prompt})
        
        # Get response from LLM
        response = self.llm.invoke(messages)
        
        # Simple tool detection (look for tool calls in response)
        # In a real implementation, you'd parse structured output
        for tool_name, tool_func in self.tools.items():
            if tool_name.lower() in response.lower():
                # Try to extract arguments (simplified)
                result = tool_func.func()
                response += f"\n\nTool result: {result}"
        
        return {"messages": messages + [{"role": "assistant", "content": response}]}

# But actually, LangChain's ChatOpenAI with Ollama endpoint IS free!
# So let's keep using that since it's more robust