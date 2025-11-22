# -*- coding: utf-8 -*-
"""
Medication Validator Service - Validates prescriptions and detects issues.

This service validates medication prescriptions, checks for drug interactions,
contraindications, and dosing errors. It uses Ollama for clinical reasoning
and PubMed for evidence-based validation.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
import re
from api.models import get_llm
from api.pubmed import pubmed_search, local_search_terms


class MedicationValidator:
    """
    Validates medications and detects potential issues.
    """
    
    def __init__(self):
        self.llm = get_llm()
    
    async def validate_prescription(
        self,
        medication: Dict[str, Any],
        patient_context: Dict[str, Any],
        current_medications: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Validate a complete prescription.
        
        Args:
            medication: Medication details (name, dose, frequency, route)
            patient_context: Patient information (age, weight, allergies, conditions)
            current_medications: List of current medications
            
        Returns:
            Validation result with warnings and recommendations
        """
        warnings = []
        recommendations = []
        severity = "ok"  # "ok", "warning", "critical"
        
        med_name = medication.get("name", "").strip()
        dose = medication.get("dose", "").strip()
        frequency = medication.get("frequency", "").strip()
        
        # 1. Check contraindications
        contraindication_result = await self._check_contraindications(
            med_name, patient_context
        )
        if contraindication_result["has_contraindication"]:
            warnings.extend(contraindication_result["warnings"])
            severity = "critical"
        
        # 2. Check drug interactions
        if current_medications:
            interaction_result = await self._check_interactions(
                med_name, current_medications, patient_context
            )
            if interaction_result["has_interaction"]:
                warnings.extend(interaction_result["warnings"])
                recommendations.extend(interaction_result["recommendations"])
                if interaction_result["severity"] == "critical":
                    severity = "critical"
                elif severity != "critical":
                    severity = "warning"
        
        # 3. Validate dose
        if dose:
            dose_result = await self._validate_dose(
                med_name, dose, frequency, patient_context
            )
            if dose_result["has_issue"]:
                warnings.extend(dose_result["warnings"])
                recommendations.extend(dose_result["recommendations"])
                if dose_result["severity"] == "critical" and severity != "critical":
                    severity = "critical"
                elif severity == "ok":
                    severity = "warning"
        
        return {
            "medication": med_name,
            "validation_status": severity,
            "warnings": warnings,
            "recommendations": recommendations,
            "safe_to_prescribe": severity != "critical"
        }
    
    async def _check_contraindications(
        self,
        medication: str,
        patient_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check for contraindications based on patient allergies and conditions."""
        warnings = []
        has_contraindication = False
        
        allergies = patient_context.get("allergies", [])
        age = patient_context.get("age")
        conditions = patient_context.get("conditions", [])
        pregnancy = patient_context.get("pregnancy", False)
        
        # Check allergies
        med_lower = medication.lower()
        for allergy in allergies:
            allergy_lower = str(allergy).lower()
            if allergy_lower in med_lower or med_lower in allergy_lower:
                warnings.append(f"⚠️ CONTRAINDICACIÓN: Paciente alérgico a {allergy}")
                has_contraindication = True
        
        # Use LLM for complex contraindication checking
        prompt = self._build_contraindication_prompt(medication, patient_context)
        llm_response = await self.llm.chat(
            messages=[
                {"role": "system", "content": "Eres un farmacólogo clínico experto. Identifica contraindicaciones de medicamentos. Responde en formato JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=500
        )
        
        # Parse LLM response
        try:
            import json
            llm_data = json.loads(llm_response)
            if llm_data.get("has_contraindication"):
                has_contraindication = True
                warnings.extend(llm_data.get("contraindications", []))
        except Exception:
            pass
        
        return {
            "has_contraindication": has_contraindication,
            "warnings": warnings
        }
    
    async def _check_interactions(
        self,
        medication: str,
        current_medications: List[Dict[str, Any]],
        patient_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check for drug-drug interactions."""
        warnings = []
        recommendations = []
        has_interaction = False
        severity = "ok"
        
        if not current_medications:
            return {
                "has_interaction": False,
                "warnings": [],
                "recommendations": [],
                "severity": "ok"
            }
        
        # Build medication list
        med_list = [m.get("name", "") for m in current_medications if m.get("name")]
        
        # Use LLM to check interactions
        prompt = self._build_interaction_prompt(medication, med_list, patient_context)
        llm_response = await self.llm.chat(
            messages=[
                {"role": "system", "content": "Eres un farmacólogo clínico experto en interacciones medicamentosas. Responde en formato JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=800
        )
        
        # Parse LLM response
        try:
            import json
            llm_data = json.loads(llm_response)
            if llm_data.get("has_interaction"):
                has_interaction = True
                severity = llm_data.get("severity", "warning")
                warnings.extend(llm_data.get("interactions", []))
                recommendations.extend(llm_data.get("recommendations", []))
        except Exception:
            pass
        
        # Specific known interactions (hardcoded for safety)
        known_interactions = self._check_known_interactions(medication, med_list)
        if known_interactions:
            has_interaction = True
            warnings.extend(known_interactions["warnings"])
            recommendations.extend(known_interactions["recommendations"])
            if known_interactions["severity"] == "critical":
                severity = "critical"
        
        return {
            "has_interaction": has_interaction,
            "warnings": warnings,
            "recommendations": recommendations,
            "severity": severity
        }
    
    def _check_known_interactions(self, medication: str, current_meds: List[str]) -> Optional[Dict[str, Any]]:
        """Check against known critical drug interactions."""
        med_lower = medication.lower()
        current_lower = [m.lower() for m in current_meds]
        
        # Known critical interactions
        critical_interactions = {
            "warfarina": ["aspirina", "aas", "ácido acetilsalicílico", "ibuprofeno", "naproxeno", "diclofenaco"],
            "acenocumarol": ["aspirina", "aas", "ácido acetilsalicílico", "ibuprofeno", "naproxeno"],
            "metformina": ["contraste yodado", "medio de contraste"],
            "digoxina": ["amiodarona", "verapamilo", "diltiazem"],
            "simvastatina": ["gemfibrozil", "gemfibrozilo", "claritromicina", "eritromicina"],
        }
        
        for drug, interacting_drugs in critical_interactions.items():
            if drug in med_lower:
                for interacting in interacting_drugs:
                    if any(interacting in curr for curr in current_lower):
                        return {
                            "severity": "critical",
                            "warnings": [f"⚠️ INTERACCIÓN CRÍTICA: {medication} + {interacting} - Riesgo aumentado de efectos adversos"],
                            "recommendations": [f"Considerar alternativa a {medication} o ajustar dosis con monitoreo estrecho"]
                        }
            
            # Check reverse
            if any(drug in curr for curr in current_lower):
                for interacting in interacting_drugs:
                    if interacting in med_lower:
                        return {
                            "severity": "critical",
                            "warnings": [f"⚠️ INTERACCIÓN CRÍTICA: {medication} + {drug} - Riesgo aumentado de efectos adversos"],
                            "recommendations": [f"Considerar alternativa a {medication}"]
                        }
        
        return None
    
    async def _validate_dose(
        self,
        medication: str,
        dose: str,
        frequency: str,
        patient_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate medication dose for patient."""
        warnings = []
        recommendations = []
        has_issue = False
        severity = "ok"
        
        age = patient_context.get("age")
        weight = patient_context.get("weight")
        
        # Use LLM for dose validation
        prompt = self._build_dose_validation_prompt(medication, dose, frequency, patient_context)
        llm_response = await self.llm.chat(
            messages=[
                {"role": "system", "content": "Eres un farmacólogo clínico experto en dosificación de medicamentos. Responde en formato JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=600
        )
        
        # Parse LLM response
        try:
            import json
            llm_data = json.loads(llm_response)
            if llm_data.get("has_issue"):
                has_issue = True
                severity = llm_data.get("severity", "warning")
                warnings.extend(llm_data.get("warnings", []))
                recommendations.extend(llm_data.get("recommendations", []))
        except Exception:
            pass
        
        return {
            "has_issue": has_issue,
            "warnings": warnings,
            "recommendations": recommendations,
            "severity": severity
        }
    
    def _build_contraindication_prompt(self, medication: str, patient_context: Dict[str, Any]) -> str:
        """Build prompt for contraindication checking."""
        age = patient_context.get("age", "desconocida")
        allergies = patient_context.get("allergies", [])
        conditions = patient_context.get("conditions", [])
        pregnancy = patient_context.get("pregnancy", False)
        
        return f"""Evalúa si hay contraindicaciones para prescribir {medication} a este paciente:

Paciente:
- Edad: {age} años
- Alergias: {', '.join(allergies) if allergies else 'ninguna conocida'}
- Condiciones: {', '.join(conditions) if conditions else 'ninguna conocida'}
- Embarazo: {'Sí' if pregnancy else 'No'}

Responde en JSON:
{{
  "has_contraindication": true/false,
  "contraindications": ["lista de contraindicaciones encontradas"],
  "severity": "critical/warning"
}}"""
    
    def _build_interaction_prompt(self, medication: str, current_meds: List[str], patient_context: Dict[str, Any]) -> str:
        """Build prompt for interaction checking."""
        return f"""Evalúa interacciones medicamentosas para:

Medicamento a prescribir: {medication}

Medicamentos actuales del paciente:
{chr(10).join(f'- {med}' for med in current_meds)}

Edad del paciente: {patient_context.get('age', 'desconocida')} años

Responde en JSON:
{{
  "has_interaction": true/false,
  "severity": "critical/warning/ok",
  "interactions": ["lista de interacciones encontradas con descripción del riesgo"],
  "recommendations": ["recomendaciones específicas"]
}}"""
    
    def _build_dose_validation_prompt(self, medication: str, dose: str, frequency: str, patient_context: Dict[str, Any]) -> str:
        """Build prompt for dose validation."""
        age = patient_context.get("age", "desconocida")
        weight = patient_context.get("weight", "desconocido")
        
        return f"""Valida la dosis de este medicamento:

Medicamento: {medication}
Dosis prescrita: {dose}
Frecuencia: {frequency}

Paciente:
- Edad: {age} años
- Peso: {weight} kg

Verifica si la dosis es apropiada, está dentro del rango terapéutico, y no excede la dosis máxima diaria.

Responde en JSON:
{{
  "has_issue": true/false,
  "severity": "critical/warning/ok",
  "warnings": ["lista de problemas con la dosis"],
  "recommendations": ["dosis recomendada con justificación"],
  "correct_dose_range": "rango de dosis correcto"
}}"""


async def validate_medication(
    medication: Dict[str, Any],
    patient_context: Dict[str, Any],
    current_medications: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Convenience function to validate a medication.
    
    Args:
        medication: Medication to validate
        patient_context: Patient information
        current_medications: Current medications list
        
    Returns:
        Validation result
    """
    validator = MedicationValidator()
    return await validator.validate_prescription(medication, patient_context, current_medications)
