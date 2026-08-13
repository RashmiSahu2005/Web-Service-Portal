from app.services.llm_service import LLMService

prompt = """You are a senior system administrator. Generate a robust, idempotent Python 3 installation script for a Linux environment for Brave browser. Return ONLY the python script inside ```python. Use subprocess."""

print(LLMService.generate(prompt))
