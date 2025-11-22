# -*- coding: utf-8 -*-
"""Knowledge management routes."""

from fastapi import APIRouter, Query, Body, HTTPException
from api.services.knowledge_service import list_knowledge_files, save_knowledge_file

router = APIRouter()


@router.get("/knowledge/list")
async def list_knowledge():
    """List all knowledge files."""
    try:
        files = list_knowledge_files()
        return {"count": len(files), "files": files}
    except Exception as e:
        raise HTTPException(500, f"knowledge list failed: {e}")


@router.post("/knowledge/upsert")
async def upsert_knowledge(
    name: str = Query(..., description="nombre del archivo en KNOWLEDGE_DIR"),
    content: str = Body(..., media_type="text/plain"),
):
    """Create or update a knowledge file."""
    try:
        path = save_knowledge_file(name, content)
        return {"status": "ok", "path": path}
    except Exception as e:
        raise HTTPException(500, f"knowledge upsert failed: {e}")
