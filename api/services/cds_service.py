# -*- coding: utf-8 -*-
"""Clinical Decision Support (CDS) service."""

from typing import Dict, Any, List
from api.cds import suggest_cds, build_context_from_json

__all__ = ["get_cds_suggestions", "build_cds_context"]


def build_cds_context(json_clinico: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build CDS context from clinical JSON.
    
    Args:
        json_clinico: Clinical JSON data
        
    Returns:
        CDS context dictionary
    """
    return build_context_from_json(json_clinico)


async def get_cds_suggestions(
    context: Dict[str, Any],
    use_pubmed: bool = True,
    pubmed_max: int = 5
) -> List[Dict[str, Any]]:
    """
    Get clinical decision support suggestions.
    
    Args:
        context: Clinical context
        use_pubmed: Whether to use PubMed for evidence
        pubmed_max: Maximum PubMed results
        
    Returns:
        List of CDS suggestions
    """
    return await suggest_cds(
        context,
        use_pubmed=use_pubmed,
        pubmed_max=pubmed_max
    )
