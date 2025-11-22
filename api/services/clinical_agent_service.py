# -*- coding: utf-8 -*-
"""
Clinical Agent Service - Main orchestrator for the clinical AI agent.

This service acts as the "brain" of the system, coordinating all clinical
reasoning, evidence gathering, medication validation, and decision support.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
import json
import re

from api.models import get_llm
from api.pubmed import pubmed_search, local_search_terms, local_has_db
from api.services.conversation_memory import (
    ConversationMemory,
    get_or_create_memory,
    get_memory
)
from api.services.medication_validator import MedicationValidator


class ClinicalAgent:
    """
    Main clinical AI agent that coordinates all clinical intelligence.
    
    This agent:
    - Maintains conversation context
    - Performs clinical reasoning with Ollama
    - Gathers evidence from PubMed
    - Validates medications
    - Generates clinical alerts
    - Suggests next steps
    """
    
    def __init__(self, encounter_id: str, patient_id: Optional[str] = None):
        self.encounter_id = encounter_id
        self.memory = get_or_create_memory(encounter_id, patient_id)
        self.llm = get_llm()
        self.medication_validator = MedicationValidator()
    
    async def process_conversation_turn(
        self,
        speaker: str,
        text: str,
        auto_extract: bool = True
    ) -> Dict[str, Any]:
        """
        Process a single conversation turn from the consultation.
        
        Args:
            speaker: "DOCTOR" or "PACIENTE"
            text: What was said
            auto_extract: Whether to automatically extract clinical information
            
        Returns:
            Processing result with extracted information and suggestions
        """
        # Add to memory
        self.memory.add_conversation_turn(speaker, text)
        
        result = {
            "turn_added": True,
            "extracted_info": {},
            "suggestions": [],
            "alerts": []
        }
        
        if not auto_extract:
            return result
        
        # Extract clinical information using LLM
        extraction = await self._extract_clinical_info(text, speaker)
        result["extracted_info"] = extraction
        
        # Add findings to memory
        if extraction.get("symptoms"):
            for symptom in extraction["symptoms"]:
                self.memory.add_finding("symptom", symptom, source=speaker.lower())
        
        if extraction.get("diagnoses"):
            for diagnosis in extraction["diagnoses"]:
                self.memory.add_finding("diagnosis", diagnosis, source="physician")
        
        # Check for medications mentioned
        if extraction.get("medications"):
            for med_info in extraction["medications"]:
                medication = self.memory.add_medication(
                    name=med_info.get("name", ""),
                    dose=med_info.get("dose"),
                    frequency=med_info.get("frequency"),
                    route=med_info.get("route"),
                    indication=med_info.get("indication"),
                    status="proposed"
                )
                
                # Validate medication automatically
                validation = await self._validate_medication_auto(med_info)
                if validation:
                    result["alerts"].extend(validation.get("alerts", []))
        
        # Generate contextual suggestions
        suggestions = await self._generate_contextual_suggestions()
        result["suggestions"] = suggestions
        
        return result
    
    async def _extract_clinical_info(self, text: str, speaker: str) -> Dict[str, Any]:
        """Extract structured clinical information from text."""
        prompt = f"""Extrae información clínica del siguiente texto de una consulta médica.

Hablante: {speaker}
Texto: "{text}"

Extrae:
- Síntomas mencionados
- Diagnósticos mencionados
- Medicamentos mencionados (con dosis si está disponible)
- Signos vitales mencionados
- Alergias mencionadas

Responde en JSON:
{{
  "symptoms": ["lista de síntomas"],
  "diagnoses": ["lista de diagnósticos"],
  "medications": [
    {{"name": "nombre", "dose": "dosis", "frequency": "frecuencia", "route": "vía"}}
  ],
  "vitals": {{"TA": "valor", "FC": "valor", "Temp": "valor"}},
  "allergies": ["lista de alergias"]
}}"""
        
        response = await self.llm.chat(
            messages=[
                {"role": "system", "content": "Eres un asistente médico experto en extracción de información clínica. Responde solo en JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=800
        )
        
        try:
            return json.loads(response)
        except Exception:
            return {}
    
    async def _validate_medication_auto(self, med_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Automatically validate a medication and generate alerts."""
        patient_context = self.memory.patient_context
        current_meds = [
            {"name": m.name, "dose": m.dose, "frequency": m.frequency}
            for m in self.memory.get_current_medications()
        ]
        
        validation = await self.medication_validator.validate_prescription(
            medication=med_info,
            patient_context=patient_context,
            current_medications=current_meds
        )
        
        # Update medication validation in memory
        self.memory.update_medication_validation(
            med_info.get("name", ""),
            validation["validation_status"],
            validation["warnings"]
        )
        
        # Generate alerts if needed
        alerts = []
        if validation["validation_status"] == "critical":
            alert = self.memory.add_alert(
                alert_type="medication_validation",
                severity="critical",
                message=f"⚠️ ALERTA CRÍTICA: {med_info.get('name')}",
                details="\n".join(validation["warnings"]),
                action_required=True
            )
            alerts.append(alert.to_dict())
        elif validation["validation_status"] == "warning":
            alert = self.memory.add_alert(
                alert_type="medication_validation",
                severity="warning",
                message=f"⚠️ Advertencia: {med_info.get('name')}",
                details="\n".join(validation["warnings"]),
                action_required=False
            )
            alerts.append(alert.to_dict())
        
        return {"alerts": alerts, "validation": validation}
    
    async def _generate_contextual_suggestions(self) -> List[Dict[str, Any]]:
        """Generate contextual clinical suggestions based on current state with evidence."""
        context = self.memory.get_context_summary()
        
        # Don't generate suggestions if no clinical data yet
        if not context.get("symptoms") and not context.get("diagnoses"):
            return []
        
        # 1. Generate initial suggestions with LLM
        prompt = f"""Basándote en el contexto clínico actual, genera sugerencias útiles para el médico.

Contexto:
- Síntomas: {', '.join(context.get('symptoms', []))}
- Diagnósticos: {', '.join(context.get('diagnoses', []))}
- Edad: {context.get('age', 'desconocida')}
- Alergias: {', '.join(context.get('allergies', []))}
- Medicamentos actuales: {len(context.get('current_medications', []))}

Genera máximo 3 sugerencias clínicas relevantes (estudios, tratamientos, precauciones) y para cada una incluye un término de búsqueda para validar con evidencia.

Responde en JSON:
{{
  "suggestions": [
    {{
      "type": "diagnostic/treatment/precaution",
      "message": "sugerencia clara y concisa",
      "rationale": "justificación breve",
      "search_term": "término de búsqueda para PubMed (ej: 'migraine treatment guidelines')"
    }}
  ]
}}"""
        
        response = await self.llm.chat(
            messages=[
                {"role": "system", "content": "Eres un asistente clínico experto. Genera sugerencias basadas en evidencia. Responde en JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=600
        )
        
        suggestions = []
        try:
            data = json.loads(response)
            raw_suggestions = data.get("suggestions", [])
            
            # 2. Validate/Augment with PubMed Evidence
            for sugg in raw_suggestions:
                search_term = sugg.get("search_term")
                evidence_link = None
                
                if search_term:
                    try:
                        # Quick search in PubMed (limit 1 for speed)
                        pubmed_results = await pubmed_search(search_term, retmax=1)
                        if pubmed_results.get("ids"):
                            pmid = pubmed_results["ids"][0]
                            evidence_link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                            sugg["evidence_source"] = "PubMed"
                            sugg["evidence_link"] = evidence_link
                    except Exception:
                        pass
                
                suggestions.append(sugg)
                
        except Exception:
            return []
            
        return suggestions
    
    async def get_clinical_reasoning(self, query: str, use_pubmed: bool = True) -> Dict[str, Any]:
        """
        Get clinical reasoning for a specific query with evidence.
        
        Args:
            query: Clinical question or scenario
            use_pubmed: Whether to search PubMed for evidence
            
        Returns:
            Reasoning with evidence and recommendations
        """
        context = self.memory.get_context_summary()
        
        # Build comprehensive prompt
        prompt = f"""Contexto clínico:
- Paciente: {context.get('age', 'edad desconocida')} años
- Síntomas: {', '.join(context.get('symptoms', [])) or 'ninguno registrado'}
- Diagnósticos: {', '.join(context.get('diagnoses', [])) or 'ninguno registrado'}
- Alergias: {', '.join(context.get('allergies', [])) or 'ninguna conocida'}

Pregunta clínica: {query}

Proporciona razonamiento clínico estructurado:
1. Análisis del caso
2. Diagnósticos diferenciales (si aplica)
3. Recomendaciones basadas en evidencia
4. Términos de búsqueda para PubMed (si se necesita evidencia adicional)

Responde en JSON:
{{
  "analysis": "análisis del caso",
  "differential_diagnoses": ["lista de diagnósticos diferenciales"],
  "recommendations": ["recomendaciones específicas"],
  "pubmed_search_terms": ["términos para buscar evidencia"],
  "confidence": "high/medium/low"
}}"""
        
        reasoning_response = await self.llm.chat(
            messages=[
                {"role": "system", "content": "Eres un médico clínico experto. Proporciona razonamiento clínico basado en evidencia. Responde en JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=1200
        )
        
        try:
            reasoning = json.loads(reasoning_response)
        except Exception:
            reasoning = {"analysis": reasoning_response, "recommendations": []}
        
        # Search PubMed for evidence if requested
        evidence = []
        if use_pubmed and reasoning.get("pubmed_search_terms"):
            for search_term in reasoning["pubmed_search_terms"][:2]:  # Limit to 2 searches
                try:
                    # Try local first
                    if local_has_db():
                        local_results = local_search_terms(search_term, limit=3)
                        evidence.extend(local_results)
                    else:
                        # Search PubMed
                        pubmed_results = await pubmed_search(search_term, retmax=3)
                        if pubmed_results.get("ids"):
                            # Note: In production, fetch summaries for these IDs
                            evidence.extend([
                                {"pmid": pmid, "search_term": search_term}
                                for pmid in pubmed_results["ids"][:3]
                            ])
                except Exception:
                    pass
        
        # Store reasoning in memory
        self.memory.add_reasoning(
            step="clinical_reasoning",
            input_data={"query": query, "context": context},
            output_data=reasoning,
            model_used=self.llm.model
        )
        
        return {
            "reasoning": reasoning,
            "evidence": evidence,
            "query": query
        }
    
    async def validate_complete_prescription(
        self,
        medications: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Validate a complete prescription with all medications.
        
        Args:
            medications: List of medications to prescribe
            
        Returns:
            Complete validation report
        """
        patient_context = self.memory.patient_context
        validation_results = []
        critical_issues = []
        warnings = []
        
        for med in medications:
            # Get current medications (excluding the one being validated)
            current_meds = [
                {"name": m.name, "dose": m.dose, "frequency": m.frequency}
                for m in self.memory.get_current_medications()
                if m.name.lower() != med.get("name", "").lower()
            ]
            
            validation = await self.medication_validator.validate_prescription(
                medication=med,
                patient_context=patient_context,
                current_medications=current_meds
            )
            
            validation_results.append({
                "medication": med,
                "validation": validation
            })
            
            if validation["validation_status"] == "critical":
                critical_issues.extend(validation["warnings"])
            elif validation["validation_status"] == "warning":
                warnings.extend(validation["warnings"])
        
        return {
            "safe_to_prescribe": len(critical_issues) == 0,
            "critical_issues": critical_issues,
            "warnings": warnings,
            "validations": validation_results
        }
    
    async def suggest_next_steps(self) -> Dict[str, Any]:
        """
        Suggest next clinical steps based on current consultation state.
        
        Returns:
            Suggested next steps with rationale
        """
        context = self.memory.get_context_summary()
        
        prompt = f"""Basándote en el estado actual de la consulta, sugiere los próximos pasos clínicos.

Estado actual:
- Síntomas documentados: {len(context.get('symptoms', []))}
- Diagnósticos: {', '.join(context.get('diagnoses', [])) or 'ninguno aún'}
- Medicamentos propuestos: {len(context.get('current_medications', []))}
- Alertas activas: {len(context.get('active_alerts', []))}

Sugiere los 3-5 próximos pasos más importantes (examen físico, estudios, tratamiento, educación al paciente, etc.).

Responde en JSON:
{{
  "next_steps": [
    {{
      "step": "descripción del paso",
      "priority": "high/medium/low",
      "rationale": "justificación"
    }}
  ]
}}"""
        
        response = await self.llm.chat(
            messages=[
                {"role": "system", "content": "Eres un médico clínico experto. Sugiere próximos pasos clínicos apropiados. Responde en JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=800
        )
        
        try:
            return json.loads(response)
        except Exception:
            return {"next_steps": []}
    
    def get_conversation_summary(self) -> Dict[str, Any]:
        """Get complete conversation summary."""
        return self.memory.get_context_summary()
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get all active (unacknowledged) alerts."""
        return [alert.to_dict() for alert in self.memory.get_active_alerts()]
    
    def acknowledge_alert(self, alert_index: int) -> None:
        """Acknowledge an alert."""
        self.memory.acknowledge_alert(alert_index)
    
    def export_memory(self) -> Dict[str, Any]:
        """Export complete memory for persistence."""
        return self.memory.to_dict()


# Convenience functions

async def create_clinical_agent(encounter_id: str, patient_id: Optional[str] = None, patient_context: Optional[Dict[str, Any]] = None) -> ClinicalAgent:
    """
    Create a new clinical agent for an encounter.
    
    Args:
        encounter_id: Unique encounter ID
        patient_id: Patient ID
        patient_context: Initial patient context (age, allergies, etc.)
        
    Returns:
        Initialized ClinicalAgent
    """
    agent = ClinicalAgent(encounter_id, patient_id)
    if patient_context:
        agent.memory.set_patient_context(patient_context)
    return agent


def get_clinical_agent(encounter_id: str) -> Optional[ClinicalAgent]:
    """
    Get existing clinical agent for an encounter.
    
    Args:
        encounter_id: Encounter ID
        
    Returns:
        ClinicalAgent if exists, None otherwise
    """
    memory = get_memory(encounter_id)
    if memory:
        return ClinicalAgent(encounter_id)
    return None
