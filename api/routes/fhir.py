# -*- coding: utf-8 -*-
"""FHIR routes."""

from typing import Dict, Any
from fastapi import APIRouter, Body, HTTPException
from api.services.fhir_service import push_to_fhir_server

router = APIRouter()


@router.post("/fhir/push")
async def push_fhir_bundle(bundle: Dict[str, Any] = Body(...)):
    """
    Push FHIR bundle to FHIR server.
    
    Args:
        bundle: FHIR bundle to push
        
    Returns:
        Server response
    """
    try:
        response = await push_to_fhir_server(bundle)
        return {"status": "ok", "response": response}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"push failed: {e}")
