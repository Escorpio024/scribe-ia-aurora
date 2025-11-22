# -*- coding: utf-8 -*-
"""PubMed integration routes."""

from fastapi import APIRouter, Query, HTTPException
from api.services.knowledge_service import search_pubmed, bootstrap_pubmed_knowledge

router = APIRouter()


@router.get("/pubmed/search")
async def search_pubmed_articles(q: str, retmax: int = 5):
    """Search PubMed for articles."""
    try:
        return await search_pubmed(q, retmax=retmax)
    except Exception as e:
        raise HTTPException(502, f"PubMed error: {e}")


@router.post("/pubmed/bootstrap")
async def bootstrap_knowledge_base(
    q: str = Query(..., description="query PubMed"),
    total: int = Query(500, ge=1, le=5000),
):
    """Bootstrap knowledge base with PubMed articles."""
    try:
        result = await bootstrap_pubmed_knowledge(q, total)
        return {"status": "ok", **result}
    except Exception as e:
        raise HTTPException(500, f"bootstrap failed: {e}")
