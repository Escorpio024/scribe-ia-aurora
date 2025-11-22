# -*- coding: utf-8 -*-
"""Services module for Scribe-IA API."""

from api.services.asr_service import transcribe_audio
from api.services.nlp_service import generate_clinical_json
from api.services.fhir_service import create_fhir_bundle, push_to_fhir_server
from api.services.cds_service import get_cds_suggestions, build_cds_context
from api.services.knowledge_service import search_pubmed, augment_with_evidence
from api.services.clinical_agent_service import ClinicalAgent, create_clinical_agent, get_clinical_agent
from api.services.conversation_memory import ConversationMemory, get_or_create_memory, get_memory
from api.services.medication_validator import MedicationValidator, validate_medication

__all__ = [
    "transcribe_audio",
    "generate_clinical_json",
    "create_fhir_bundle",
    "push_to_fhir_server",
    "get_cds_suggestions",
    "build_cds_context",
    "search_pubmed",
    "augment_with_evidence",
    "ClinicalAgent",
    "create_clinical_agent",
    "get_clinical_agent",
    "ConversationMemory",
    "get_or_create_memory",
    "get_memory",
    "MedicationValidator",
    "validate_medication",
]
