# -*- coding: utf-8 -*-
"""
Conversation Memory Service - Maintains clinical context during consultation.

This service keeps track of all clinical information gathered during a consultation,
including patient data, findings, medications, decisions, and alerts.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, field, asdict
import json


@dataclass
class ClinicalFinding:
    """Represents a clinical finding discovered during consultation."""
    timestamp: str
    type: str  # "symptom", "sign", "vital", "lab", "diagnosis"
    description: str
    severity: Optional[str] = None  # "mild", "moderate", "severe"
    source: str = "physician"  # "physician", "patient", "agent"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MedicationMention:
    """Represents a medication mentioned during consultation."""
    timestamp: str
    name: str
    dose: Optional[str] = None
    frequency: Optional[str] = None
    route: Optional[str] = None
    indication: Optional[str] = None
    status: str = "proposed"  # "proposed", "prescribed", "rejected", "current"
    validation_status: Optional[str] = None  # "validated", "warning", "contraindicated"
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClinicalDecision:
    """Represents a clinical decision made during consultation."""
    timestamp: str
    type: str  # "diagnosis", "treatment", "order", "referral"
    description: str
    rationale: Optional[str] = None
    evidence: List[Dict[str, Any]] = field(default_factory=list)  # PubMed references
    confidence: Optional[str] = None  # "high", "medium", "low"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClinicalAlert:
    """Represents a clinical alert triggered during consultation."""
    timestamp: str
    type: str  # "drug_interaction", "contraindication", "dose_warning", "clinical_guideline"
    severity: str  # "critical", "warning", "info"
    message: str
    details: Optional[str] = None
    action_required: bool = True
    acknowledged: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ConversationMemory:
    """
    Maintains the complete clinical context for a consultation encounter.
    
    This class acts as the "memory" of the clinical agent, storing all
    information gathered during the consultation and providing methods
    to query and update this information.
    """
    
    def __init__(self, encounter_id: str, patient_id: Optional[str] = None):
        self.encounter_id = encounter_id
        self.patient_id = patient_id
        self.started_at = datetime.now().isoformat()
        
        # Patient context
        self.patient_context: Dict[str, Any] = {}
        
        # Clinical data
        self.clinical_findings: List[ClinicalFinding] = []
        self.medications_mentioned: List[MedicationMention] = []
        self.decisions_made: List[ClinicalDecision] = []
        self.alerts_triggered: List[ClinicalAlert] = []
        
        # Conversation turns
        self.conversation_turns: List[Dict[str, Any]] = []
        
        # Agent reasoning history
        self.reasoning_history: List[Dict[str, Any]] = []
    
    def set_patient_context(self, context: Dict[str, Any]) -> None:
        """Update patient context information."""
        self.patient_context.update(context)
    
    def add_conversation_turn(self, speaker: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Add a conversation turn to the history."""
        turn = {
            "timestamp": datetime.now().isoformat(),
            "speaker": speaker,
            "text": text,
            "metadata": metadata or {}
        }
        self.conversation_turns.append(turn)
    
    def add_finding(self, finding_type: str, description: str, severity: Optional[str] = None, source: str = "physician") -> ClinicalFinding:
        """Add a clinical finding."""
        finding = ClinicalFinding(
            timestamp=datetime.now().isoformat(),
            type=finding_type,
            description=description,
            severity=severity,
            source=source
        )
        self.clinical_findings.append(finding)
        return finding
    
    def add_medication(self, name: str, dose: Optional[str] = None, frequency: Optional[str] = None,
                      route: Optional[str] = None, indication: Optional[str] = None, 
                      status: str = "proposed") -> MedicationMention:
        """Add a medication mention."""
        medication = MedicationMention(
            timestamp=datetime.now().isoformat(),
            name=name,
            dose=dose,
            frequency=frequency,
            route=route,
            indication=indication,
            status=status
        )
        self.medications_mentioned.append(medication)
        return medication
    
    def update_medication_validation(self, medication_name: str, validation_status: str, warnings: List[str]) -> None:
        """Update validation status for a medication."""
        for med in reversed(self.medications_mentioned):
            if med.name.lower() == medication_name.lower():
                med.validation_status = validation_status
                med.warnings = warnings
                break
    
    def add_decision(self, decision_type: str, description: str, rationale: Optional[str] = None,
                    evidence: Optional[List[Dict[str, Any]]] = None, confidence: Optional[str] = None) -> ClinicalDecision:
        """Add a clinical decision."""
        decision = ClinicalDecision(
            timestamp=datetime.now().isoformat(),
            type=decision_type,
            description=description,
            rationale=rationale,
            evidence=evidence or [],
            confidence=confidence
        )
        self.decisions_made.append(decision)
        return decision
    
    def add_alert(self, alert_type: str, severity: str, message: str, 
                 details: Optional[str] = None, action_required: bool = True) -> ClinicalAlert:
        """Add a clinical alert."""
        alert = ClinicalAlert(
            timestamp=datetime.now().isoformat(),
            type=alert_type,
            severity=severity,
            message=message,
            details=details,
            action_required=action_required
        )
        self.alerts_triggered.append(alert)
        return alert
    
    def acknowledge_alert(self, alert_index: int) -> None:
        """Mark an alert as acknowledged."""
        if 0 <= alert_index < len(self.alerts_triggered):
            self.alerts_triggered[alert_index].acknowledged = True
    
    def add_reasoning(self, step: str, input_data: Dict[str, Any], output_data: Dict[str, Any], 
                     model_used: Optional[str] = None) -> None:
        """Add agent reasoning step to history."""
        reasoning = {
            "timestamp": datetime.now().isoformat(),
            "step": step,
            "input": input_data,
            "output": output_data,
            "model": model_used
        }
        self.reasoning_history.append(reasoning)
    
    def get_current_medications(self) -> List[MedicationMention]:
        """Get all current and proposed medications."""
        return [m for m in self.medications_mentioned if m.status in ["proposed", "prescribed", "current"]]
    
    def get_active_alerts(self) -> List[ClinicalAlert]:
        """Get all unacknowledged alerts."""
        return [a for a in self.alerts_triggered if not a.acknowledged]
    
    def get_diagnoses(self) -> List[ClinicalFinding]:
        """Get all diagnosis findings."""
        return [f for f in self.clinical_findings if f.type == "diagnosis"]
    
    def get_symptoms(self) -> List[ClinicalFinding]:
        """Get all symptom findings."""
        return [f for f in self.clinical_findings if f.type == "symptom"]
    
    def get_context_summary(self) -> Dict[str, Any]:
        """Get a summary of the current clinical context."""
        return {
            "encounter_id": self.encounter_id,
            "patient_id": self.patient_id,
            "patient_context": self.patient_context,
            "chief_complaint": self.patient_context.get("chief_complaint", ""),
            "age": self.patient_context.get("age"),
            "allergies": self.patient_context.get("allergies", []),
            "current_medications": [m.to_dict() for m in self.get_current_medications()],
            "diagnoses": [f.description for f in self.get_diagnoses()],
            "symptoms": [f.description for f in self.get_symptoms()],
            "active_alerts": [a.to_dict() for a in self.get_active_alerts()],
            "conversation_turns_count": len(self.conversation_turns)
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Export complete memory as dictionary."""
        return {
            "encounter_id": self.encounter_id,
            "patient_id": self.patient_id,
            "started_at": self.started_at,
            "patient_context": self.patient_context,
            "clinical_findings": [f.to_dict() for f in self.clinical_findings],
            "medications_mentioned": [m.to_dict() for m in self.medications_mentioned],
            "decisions_made": [d.to_dict() for d in self.decisions_made],
            "alerts_triggered": [a.to_dict() for a in self.alerts_triggered],
            "conversation_turns": self.conversation_turns,
            "reasoning_history": self.reasoning_history
        }
    
    def to_json(self) -> str:
        """Export complete memory as JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# Global memory store (in production, use Redis or database)
_memory_store: Dict[str, ConversationMemory] = {}


def get_or_create_memory(encounter_id: str, patient_id: Optional[str] = None) -> ConversationMemory:
    """Get existing memory or create new one for encounter."""
    if encounter_id not in _memory_store:
        _memory_store[encounter_id] = ConversationMemory(encounter_id, patient_id)
    return _memory_store[encounter_id]


def get_memory(encounter_id: str) -> Optional[ConversationMemory]:
    """Get existing memory for encounter."""
    return _memory_store.get(encounter_id)


def clear_memory(encounter_id: str) -> None:
    """Clear memory for encounter."""
    if encounter_id in _memory_store:
        del _memory_store[encounter_id]


def list_active_encounters() -> List[str]:
    """List all active encounter IDs."""
    return list(_memory_store.keys())
