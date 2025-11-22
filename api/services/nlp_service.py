# -*- coding: utf-8 -*-
"""NLP service for generating structured clinical JSON from transcripts."""

from typing import Dict, Any, List
from api.nlp_pipeline import generate_structured_json
from api.utils.text_processing import normalize_transcript_turns, cleanup_json

__all__ = ["generate_clinical_json"]


async def generate_clinical_json(
    schema_id: str,
    transcript: List[Dict[str, Any]],
    extra_context: str = ""
) -> Dict[str, Any]:
    """
    Generate structured clinical JSON from transcript using LLM.
    
    Args:
        schema_id: Schema identifier (e.g., "consulta_general", "respiratorio")
        transcript: List of conversation turns
        extra_context: Additional context for the LLM
        
    Returns:
        Structured clinical JSON
    """
    # Normalize transcript
    normalized_transcript = normalize_transcript_turns(transcript)
    
    # Generate with LLM
    json_clinico = await generate_structured_json(
        schema_id,
        normalized_transcript,
        extra_context=extra_context
    )
    
    # Cleanup
    json_clinico = cleanup_json(json_clinico)
    
    return json_clinico
