# -*- coding: utf-8 -*-
import json
from typing import List, Dict, Any, Optional
import httpx

from api.config import OLLAMA_BASE_URL, LLM_MODEL, SYSTEM_PROMPT

__all__ = ["LLMClient", "get_llm"]

class LLMClient:
    """
    Cliente minimalista para Ollama /api/chat.
    """
    def __init__(self, base_url: str, model: str, system_prompt: str):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.system_prompt = system_prompt

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Llama al endpoint /api/chat de Ollama.
        messages = [{"role":"system"|"user"|"assistant","content":"..."}]
        Devuelve el texto del último mensaje del modelo.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(f"{self.base_url}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
            # Ollama devuelve {"message":{"role":"assistant","content":"..."} ...}
            return (data.get("message") or {}).get("content", "")

# Singleton
_llm_singleton: Optional[LLMClient] = None

def get_llm() -> LLMClient:
    global _llm_singleton
    if _llm_singleton is None:
        _llm_singleton = LLMClient(
            base_url=OLLAMA_BASE_URL,
            model=LLM_MODEL,
            system_prompt=SYSTEM_PROMPT,
        )
    return _llm_singleton