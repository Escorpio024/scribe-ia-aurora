# -*- coding: utf-8 -*-
import json
from typing import List, Dict, Any, Optional
import httpx

from api.config.settings import settings

__all__ = ["LLMClient", "get_llm"]

class LLMClient:
    """
    Cliente minimalista para Ollama /api/chat con capacidades clínicas mejoradas.
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
        json_mode: bool = False
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
        
        # Force JSON format if requested
        if json_mode:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(f"{self.base_url}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
            # Ollama devuelve {"message":{"role":"assistant","content":"..."} ...}
            return (data.get("message") or {}).get("content", "")
    
    async def chat_with_evidence(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        search_pubmed: bool = True,
        max_evidence: int = 3
    ) -> Dict[str, Any]:
        """
        Chat with automatic PubMed evidence gathering.
        
        Args:
            query: Clinical query
            context: Optional clinical context
            search_pubmed: Whether to search PubMed
            max_evidence: Maximum evidence items to retrieve
            
        Returns:
            Response with evidence and reasoning
        """
        # Import here to avoid circular dependency
        from api.pubmed import pubmed_search, local_search_terms, local_has_db
        
        # First, get LLM response with search terms
        system_msg = "Eres un médico clínico experto. Proporciona respuestas basadas en evidencia."
        context_str = ""
        if context:
            context_str = f"\n\nContexto clínico:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
        
        prompt = f"{query}{context_str}\n\nProporciona tu respuesta y sugiere términos de búsqueda para PubMed si se necesita evidencia adicional."
        
        response = await self.chat(
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        
        evidence = []
        if search_pubmed:
            # Extract search terms from response or use query
            search_terms = [query]  # Simplified - could use LLM to extract better terms
            
            for term in search_terms[:2]:
                try:
                    if local_has_db():
                        local_results = local_search_terms(term, limit=max_evidence)
                        evidence.extend(local_results)
                    else:
                        pubmed_results = await pubmed_search(term, retmax=max_evidence)
                        if pubmed_results.get("ids"):
                            evidence.extend([
                                {"pmid": pmid, "search_term": term}
                                for pmid in pubmed_results["ids"][:max_evidence]
                            ])
                except Exception:
                    pass
        
        return {
            "response": response,
            "evidence": evidence[:max_evidence],
            "query": query
        }
    
    async def clinical_reasoning(
        self,
        clinical_scenario: str,
        patient_data: Optional[Dict[str, Any]] = None,
        use_chain_of_thought: bool = True
    ) -> Dict[str, Any]:
        """
        Perform clinical reasoning with chain-of-thought.
        
        Args:
            clinical_scenario: Clinical scenario description
            patient_data: Patient information
            use_chain_of_thought: Use step-by-step reasoning
            
        Returns:
            Structured clinical reasoning
        """
        patient_str = ""
        if patient_data:
            patient_str = f"\n\nDatos del paciente:\n{json.dumps(patient_data, ensure_ascii=False, indent=2)}"
        
        if use_chain_of_thought:
            prompt = f"""Analiza el siguiente escenario clínico paso a paso:{patient_str}

Escenario: {clinical_scenario}

Proporciona tu razonamiento en formato JSON:
{{
  "initial_assessment": "evaluación inicial",
  "differential_diagnoses": [
    {{"diagnosis": "diagnóstico", "probability": "alta/media/baja", "supporting_factors": ["factores"]}}
  ],
  "recommended_workup": ["estudios o exámenes recomendados"],
  "treatment_considerations": ["consideraciones de tratamiento"],
  "red_flags": ["señales de alarma a vigilar"],
  "confidence": "alta/media/baja"
}}"""
        else:
            prompt = f"""Analiza el siguiente escenario clínico:{patient_str}

Escenario: {clinical_scenario}

Proporciona diagnósticos diferenciales y recomendaciones."""
        
        response = await self.chat(
            messages=[
                {"role": "system", "content": "Eres un médico clínico experto. Usa razonamiento clínico estructurado."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            json_mode=use_chain_of_thought
        )
        
        if use_chain_of_thought:
            try:
                return json.loads(response)
            except Exception:
                return {"raw_response": response}
        else:
            return {"response": response}
    
    async def validate_clinical_decision(
        self,
        decision: str,
        context: Dict[str, Any],
        check_guidelines: bool = True
    ) -> Dict[str, Any]:
        """
        Validate a clinical decision against best practices.
        
        Args:
            decision: Clinical decision to validate
            context: Clinical context
            check_guidelines: Whether to check against guidelines
            
        Returns:
            Validation result with recommendations
        """
        prompt = f"""Valida la siguiente decisión clínica:

Decisión: {decision}

Contexto:
{json.dumps(context, ensure_ascii=False, indent=2)}

Evalúa si la decisión es apropiada y segura. Responde en JSON:
{{
  "is_appropriate": true/false,
  "safety_level": "safe/caution/unsafe",
  "concerns": ["lista de preocupaciones si las hay"],
  "recommendations": ["recomendaciones para mejorar la decisión"],
  "guideline_alignment": "descripción de alineación con guías clínicas"
}}"""
        
        response = await self.chat(
            messages=[
                {"role": "system", "content": "Eres un experto en medicina basada en evidencia y seguridad del paciente."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            json_mode=True
        )
        
        try:
            return json.loads(response)
        except Exception:
            return {"raw_response": response, "is_appropriate": None}

# Singleton
_llm_singleton: Optional[LLMClient] = None

def get_llm() -> LLMClient:
    global _llm_singleton
    if _llm_singleton is None:
        _llm_singleton = LLMClient(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.LLM_MODEL,
            system_prompt=settings.SYSTEM_PROMPT,
        )
    return _llm_singleton