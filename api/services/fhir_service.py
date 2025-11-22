# -*- coding: utf-8 -*-
"""FHIR service for building and pushing FHIR bundles."""

from typing import Dict, Any
import httpx
from api.fhir_builder import build_bundle
from api.config import settings

__all__ = ["create_fhir_bundle", "push_to_fhir_server"]


def create_fhir_bundle(
    encounter_id: str,
    patient_id: str,
    practitioner_id: str,
    json_clinico: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build FHIR bundle from clinical JSON.
    
    Args:
        encounter_id: Encounter identifier
        patient_id: Patient identifier
        practitioner_id: Practitioner identifier
        json_clinico: Clinical JSON data
        
    Returns:
        FHIR bundle
    """
    return build_bundle(
        encounter_id=encounter_id,
        patient_id=patient_id,
        practitioner_id=practitioner_id,
        json_clinico=json_clinico
    )


async def push_to_fhir_server(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """
    Push FHIR bundle to FHIR server.
    
    Args:
        bundle: FHIR bundle to push
        
    Returns:
        Server response
    """
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            settings.FHIR_BASE_URL,
            json=bundle,
            headers={"Content-Type": "application/fhir+json"},
        )
        response.raise_for_status()
        return response.json()
