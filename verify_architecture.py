#!/usr/bin/env python3
"""
Verification script for scribe-ia architecture reorganization.
Tests that all new modules can be imported correctly.
"""

import sys

def test_imports():
    """Test all new module imports."""
    tests = []
    
    # Config
    try:
        from api.config import settings
        from api.config import VITALS_REGEX, MAX_ENFERMEDAD_ACTUAL_LENGTH
        tests.append(("✅ Config module", True))
    except Exception as e:
        tests.append(("❌ Config module", False, str(e)))
    
    # Core
    try:
        from api.core.models import Turn, GenerateBody
        from api.core.dependencies import transcribe_file
        tests.append(("✅ Core module", True))
    except Exception as e:
        tests.append(("❌ Core module", False, str(e)))
    
    # Services
    try:
        from api.services.asr_service import transcribe_audio
        from api.services.nlp_service import generate_clinical_json
        from api.services.fhir_service import create_fhir_bundle
        from api.services.cds_service import get_cds_suggestions
        from api.services.knowledge_service import list_knowledge_files
        tests.append(("✅ Services module", True))
    except Exception as e:
        tests.append(("❌ Services module", False, str(e)))
    
    # Routes
    try:
        from api.routes import health, ingest, nlp, fhir, knowledge, pubmed, cds
        tests.append(("✅ Routes module", True))
    except Exception as e:
        tests.append(("❌ Routes module", False, str(e)))
    
    # Utils
    try:
        from api.utils.text_processing import normalize_transcript_turns, cleanup_json
        from api.utils.rule_extraction import extract_from_transcript
        tests.append(("✅ Utils module", True))
    except Exception as e:
        tests.append(("❌ Utils module", False, str(e)))
    
    # Main
    try:
        from api.main import app
        tests.append(("✅ Main module", True))
    except Exception as e:
        tests.append(("❌ Main module", False, str(e)))
    
    return tests

if __name__ == "__main__":
    print("🔍 Verificando nueva arquitectura de scribe-ia...\n")
    
    results = test_imports()
    
    for result in results:
        if len(result) == 2:
            print(result[0])
        else:
            print(f"{result[0]}: {result[2]}")
    
    all_passed = all(r[1] for r in results)
    
    print("\n" + "="*50)
    if all_passed:
        print("✅ TODAS LAS VERIFICACIONES PASARON")
        print("La nueva arquitectura está funcionando correctamente.")
        sys.exit(0)
    else:
        print("❌ ALGUNAS VERIFICACIONES FALLARON")
        print("Revisa los errores arriba.")
        sys.exit(1)
