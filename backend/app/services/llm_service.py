import requests
from app.core.config import settings
from app.core.logger import logger

class LLMService:
    @staticmethod
    def generate(prompt: str, json_mode: bool = False) -> str:
        provider = settings.LLM_PROVIDER
        
        if provider == "ollama":
            return LLMService._generate_ollama(prompt, json_mode)
        elif provider == "internal":
            # Future expansion
            return LLMService._generate_internal(prompt)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    @staticmethod
    def _generate_ollama(prompt: str, json_mode: bool = False) -> str:
        model = settings.LLM_MODEL
        base_url = settings.LLM_BASE_URL.rstrip('/')
        url = f"{base_url}/api/generate"
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False
        }
        
        if json_mode:
            payload["format"] = "json"
        
        logger.info(f"[LLMService] Calling Ollama provider at {url} with model {model}")
        
        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except requests.exceptions.RequestException as e:
            logger.error(f"[LLMService] Error calling Ollama API: {e}")
            if response is not None:
                logger.error(f"[LLMService] Response content: {response.text}")
            raise

    @staticmethod
    def _generate_internal(prompt: str) -> str:
        # Placeholder for future internal LLM logic
        raise NotImplementedError("Internal provider not yet implemented")
