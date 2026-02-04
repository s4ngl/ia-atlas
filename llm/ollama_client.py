"""
Ollama client for local LLM interactions
Handles all communication with Ollama API
"""
import requests
import json
from typing import Dict, Optional, Any
import time


class OllamaClient:
    """
    Client for interacting with Ollama local LLM server
    """
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.1:8b"):
        """
        Initialize Ollama client
        
        Args:
            base_url: Base URL for Ollama API
            model: Model name to use (e.g., 'llama3.1:8b', 'mistral:7b')
        """
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = 120  # 2 minutes timeout for generation
        
    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.1,
        format: Optional[str] = None
    ) -> Optional[str]:
        """
        Generate text completion from prompt
        
        Args:
            prompt: User prompt
            system: System prompt (optional)
            temperature: Sampling temperature (0.0-1.0)
            format: Output format ('json' for structured output)
            
        Returns:
            Generated text or None if error
        """
        endpoint = f"{self.base_url}/api/generate"
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "temperature": temperature,
            "stream": False
        }
        
        if system:
            payload["system"] = system
        
        if format:
            payload["format"] = format
        
        try:
            response = requests.post(
                endpoint,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            result = response.json()
            return result.get("response", "")
            
        except requests.exceptions.RequestException as e:
            print(f"Error calling Ollama API: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"Error parsing Ollama response: {e}")
            return None
    
    def generate_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.1
    ) -> Optional[Dict]:
        """
        Generate structured JSON output
        
        Args:
            prompt: User prompt
            system: System prompt (optional)
            temperature: Sampling temperature
            
        Returns:
            Parsed JSON dictionary or None if error
        """
        response = self.generate(
            prompt=prompt,
            system=system,
            temperature=temperature,
            format="json"
        )
        
        if not response:
            return None
        
        try:
            return json.loads(response)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON response: {e}")
            print(f"Response was: {response[:200]}...")
            return None
    
    def chat(
        self,
        messages: list,
        temperature: float = 0.1,
        format: Optional[str] = None
    ) -> Optional[str]:
        """
        Chat completion with message history
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature
            format: Output format ('json' for structured output)
            
        Returns:
            Assistant response or None if error
        """
        endpoint = f"{self.base_url}/api/chat"
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False
        }
        
        if format:
            payload["format"] = format
        
        try:
            response = requests.post(
                endpoint,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            result = response.json()
            message = result.get("message", {})
            return message.get("content", "")
            
        except requests.exceptions.RequestException as e:
            print(f"Error calling Ollama chat API: {e}")
            return None
    
    def check_connection(self) -> bool:
        """
        Check if Ollama server is accessible
        
        Returns:
            True if server is accessible
        """
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
    
    def list_models(self) -> list:
        """
        List available models
        
        Returns:
            List of model names
        """
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            response.raise_for_status()
            
            result = response.json()
            models = result.get("models", [])
            return [model.get("name") for model in models]
            
        except requests.exceptions.RequestException as e:
            print(f"Error listing models: {e}")
            return []
    
    def pull_model(self, model_name: str) -> bool:
        """
        Pull/download a model if not available
        
        Args:
            model_name: Name of model to pull
            
        Returns:
            True if successful
        """
        endpoint = f"{self.base_url}/api/pull"
        
        payload = {
            "name": model_name,
            "stream": False
        }
        
        try:
            print(f"Pulling model {model_name}... (this may take a while)")
            response = requests.post(
                endpoint,
                json=payload,
                timeout=600  # 10 minutes for model download
            )
            response.raise_for_status()
            print(f"✓ Model {model_name} pulled successfully")
            return True
            
        except requests.exceptions.RequestException as e:
            print(f"Error pulling model: {e}")
            return False
