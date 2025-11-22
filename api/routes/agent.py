# -*- coding: utf-8 -*-
"""
Agent routes - API endpoints for the clinical AI agent.

These endpoints provide interactive access to the clinical agent's
capabilities including chat, validation, reasoning, and suggestions.
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel

from api.services.clinical_agent_service import (
    ClinicalAgent,
    create_clinical_agent,
    get_clinical_agent
)

router = APIRouter(prefix="/agent")


# Request/Response Models

class ChatRequest(BaseModel):
    encounter_id: str
    speaker: str  # "DOCTOR" or "PACIENTE"
    text: str
    patient_context: Optional[Dict[str, Any]] = None
    auto_extract: bool = True


class ClinicalReasoningRequest(BaseModel):
    encounter_id: str
    query: str
    use_pubmed: bool = True


class PrescriptionValidationRequest(BaseModel):
    encounter_id: str
    medications: List[Dict[str, Any]]


class InitializeAgentRequest(BaseModel):
    encounter_id: str
    patient_id: Optional[str] = None
    patient_context: Optional[Dict[str, Any]] = None


# Endpoints

@router.post("/initialize")
async def initialize_agent(request: InitializeAgentRequest):
    """
    Initialize a new clinical agent for an encounter.
    
    Args:
        request: Initialization parameters
        
    Returns:
        Agent status and initial context
    """
    try:
        agent = await create_clinical_agent(
            encounter_id=request.encounter_id,
            patient_id=request.patient_id,
            patient_context=request.patient_context
        )
        
        return {
            "status": "initialized",
            "encounter_id": request.encounter_id,
            "patient_id": request.patient_id,
            "context": agent.get_conversation_summary()
        }
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to initialize agent: {e}")


@router.post("/chat")
async def chat_with_agent(request: ChatRequest):
    """
    Process a conversation turn with the clinical agent.
    
    The agent will:
    - Extract clinical information
    - Validate any medications mentioned
    - Generate contextual suggestions
    - Trigger alerts if needed
    
    Args:
        request: Chat request with speaker and text
        
    Returns:
        Processing result with extracted info, suggestions, and alerts
    """
    try:
        # Get or create agent
        agent = get_clinical_agent(request.encounter_id)
        if not agent:
            agent = await create_clinical_agent(
                encounter_id=request.encounter_id,
                patient_context=request.patient_context
            )
        
        # Process the turn
        result = await agent.process_conversation_turn(
            speaker=request.speaker,
            text=request.text,
            auto_extract=request.auto_extract
        )
        
        # Add current context
        result["context"] = agent.get_conversation_summary()
        result["active_alerts"] = agent.get_active_alerts()
        
        return result
    except Exception as e:
        raise HTTPException(500, detail=f"Chat processing failed: {e}")


@router.post("/clinical-reasoning")
async def get_clinical_reasoning(request: ClinicalReasoningRequest):
    """
    Get clinical reasoning for a specific query.
    
    The agent will:
    - Analyze the query in context of the current consultation
    - Generate differential diagnoses if applicable
    - Provide evidence-based recommendations
    - Search PubMed for supporting evidence
    
    Args:
        request: Reasoning request with query
        
    Returns:
        Clinical reasoning with evidence and recommendations
    """
    try:
        agent = get_clinical_agent(request.encounter_id)
        if not agent:
            raise HTTPException(404, detail="Agent not found. Initialize first.")
        
        reasoning = await agent.get_clinical_reasoning(
            query=request.query,
            use_pubmed=request.use_pubmed
        )
        
        return reasoning
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=f"Clinical reasoning failed: {e}")


@router.post("/validate-prescription")
async def validate_prescription(request: PrescriptionValidationRequest):
    """
    Validate a complete prescription.
    
    Checks for:
    - Drug interactions
    - Contraindications
    - Inappropriate doses
    - Duplicate therapy
    
    Args:
        request: Prescription validation request
        
    Returns:
        Complete validation report with safety assessment
    """
    try:
        agent = get_clinical_agent(request.encounter_id)
        if not agent:
            raise HTTPException(404, detail="Agent not found. Initialize first.")
        
        validation = await agent.validate_complete_prescription(
            medications=request.medications
        )
        
        return validation
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=f"Prescription validation failed: {e}")


@router.post("/suggest-next-steps")
async def suggest_next_steps(encounter_id: str = Body(..., embed=True)):
    """
    Get suggestions for next clinical steps.
    
    Based on the current consultation state, suggests:
    - Additional history questions
    - Physical examination findings to check
    - Diagnostic studies to order
    - Treatment considerations
    - Patient education topics
    
    Args:
        encounter_id: Encounter ID
        
    Returns:
        Prioritized list of next steps with rationale
    """
    try:
        agent = get_clinical_agent(encounter_id)
        if not agent:
            raise HTTPException(404, detail="Agent not found. Initialize first.")
        
        suggestions = await agent.suggest_next_steps()
        
        return suggestions
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=f"Next steps suggestion failed: {e}")


@router.get("/conversation/{encounter_id}")
async def get_conversation(encounter_id: str):
    """
    Get complete conversation history and context.
    
    Args:
        encounter_id: Encounter ID
        
    Returns:
        Complete conversation memory including all clinical data
    """
    try:
        agent = get_clinical_agent(encounter_id)
        if not agent:
            raise HTTPException(404, detail="Agent not found")
        
        return agent.export_memory()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to get conversation: {e}")


@router.get("/summary/{encounter_id}")
async def get_summary(encounter_id: str):
    """
    Get conversation summary (lighter than full conversation).
    
    Args:
        encounter_id: Encounter ID
        
    Returns:
        Summary of clinical context
    """
    try:
        agent = get_clinical_agent(encounter_id)
        if not agent:
            raise HTTPException(404, detail="Agent not found")
        
        return agent.get_conversation_summary()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to get summary: {e}")


@router.get("/alerts/{encounter_id}")
async def get_alerts(encounter_id: str):
    """
    Get active alerts for an encounter.
    
    Args:
        encounter_id: Encounter ID
        
    Returns:
        List of active (unacknowledged) alerts
    """
    try:
        agent = get_clinical_agent(encounter_id)
        if not agent:
            raise HTTPException(404, detail="Agent not found")
        
        return {
            "encounter_id": encounter_id,
            "alerts": agent.get_active_alerts()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to get alerts: {e}")


@router.post("/alerts/{encounter_id}/acknowledge")
async def acknowledge_alert(encounter_id: str, alert_index: int = Body(..., embed=True)):
    """
    Acknowledge an alert.
    
    Args:
        encounter_id: Encounter ID
        alert_index: Index of alert to acknowledge
        
    Returns:
        Updated alerts list
    """
    try:
        agent = get_clinical_agent(encounter_id)
        if not agent:
            raise HTTPException(404, detail="Agent not found")
        
        agent.acknowledge_alert(alert_index)
        
        return {
            "acknowledged": True,
            "alerts": agent.get_active_alerts()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to acknowledge alert: {e}")


@router.post("/update-patient-context")
async def update_patient_context(
    encounter_id: str = Body(...),
    patient_context: Dict[str, Any] = Body(...)
):
    """
    Update patient context information.
    
    Args:
        encounter_id: Encounter ID
        patient_context: Updated patient context
        
    Returns:
        Updated context
    """
    try:
        agent = get_clinical_agent(encounter_id)
        if not agent:
            raise HTTPException(404, detail="Agent not found. Initialize first.")
        
        agent.memory.set_patient_context(patient_context)
        
        return {
            "updated": True,
            "context": agent.get_conversation_summary()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to update context: {e}")
