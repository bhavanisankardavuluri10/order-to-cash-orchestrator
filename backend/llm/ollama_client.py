import httpx
from config import settings
import json

class OllamaClient:
    """Async client for Ollama API"""
    
    @staticmethod
    async def generate_response(prompt: str, system: str = "") -> str:
        """
        Sends a request to local Ollama instance.
        Falls back to deterministic behavior if unavailable.
        """
        payload = {
            "model": settings.MODEL_NAME,
            "prompt": prompt,
            "system": system,
            "stream": False
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{settings.OLLAMA_URL}/api/generate",
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                return data.get("response", "")
                
        except Exception as e:
            print(f"Ollama generation failed: {str(e)}")
            return "LLM integration unavailable. Falling back to deterministic mode."
