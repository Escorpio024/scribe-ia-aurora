# -*- coding: utf-8 -*-
"""Knowledge management and PubMed integration service."""

import os
from typing import Dict, Any, List
from api.pubmed import pubmed_search, pubmed_ingest_to_files
from api.augment import augment_with_pubmed
from api.config import settings

__all__ = [
    "list_knowledge_files",
    "save_knowledge_file",
    "search_pubmed",
    "bootstrap_pubmed_knowledge",
    "augment_with_evidence"
]


def list_knowledge_files() -> List[str]:
    """
    List all knowledge files in the knowledge directory.
    
    Returns:
        List of filenames
    """
    os.makedirs(settings.KNOWLEDGE_DIR, exist_ok=True)
    files = [f for f in os.listdir(settings.KNOWLEDGE_DIR) if not f.startswith(".")]
    return files


def save_knowledge_file(filename: str, content: str) -> str:
    """
    Save content to a knowledge file.
    
    Args:
        filename: Name of the file
        content: File content
        
    Returns:
        Path to saved file
    """
    os.makedirs(settings.KNOWLEDGE_DIR, exist_ok=True)
    path = os.path.join(settings.KNOWLEDGE_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


async def search_pubmed(query: str, retmax: int = 5) -> Dict[str, Any]:
    """
    Search PubMed for articles.
    
    Args:
        query: Search query
        retmax: Maximum results to return
        
    Returns:
        Search results
    """
    return await pubmed_search(query, retmax=retmax)


async def bootstrap_pubmed_knowledge(query: str, total: int = 500) -> Dict[str, Any]:
    """
    Bootstrap knowledge base with PubMed articles.
    
    Args:
        query: Search query
        total: Total articles to fetch
        
    Returns:
        Bootstrap results with file paths
    """
    out_dir = os.path.join(settings.KNOWLEDGE_DIR, "pubmed")
    result = await pubmed_ingest_to_files(q=query, total=total, out_dir=out_dir)
    return {**result, "out_dir": out_dir}


def augment_with_evidence(
    json_clinico: Dict[str, Any],
    schema_used: str = None,
    top_k: int = 12
) -> Dict[str, Any]:
    """
    Augment clinical JSON with evidence from PubMed.
    
    Args:
        json_clinico: Clinical JSON
        schema_used: Schema identifier
        top_k: Number of top results
        
    Returns:
        Augmented data with evidence
    """
    return augment_with_pubmed(json_clinico, schema_used=schema_used, top_k=top_k)
