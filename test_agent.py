# Clinical Agent - Quick Test Script

import asyncio
import json
from api.services.clinical_agent_service import create_clinical_agent

async def test_agent():
    """Test the clinical agent with a simple scenario."""
    
    print("🤖 Testing Clinical Agent\n")
    
    # Create agent
    print("1. Creating agent...")
    agent = await create_clinical_agent(
        encounter_id="test_001",
        patient_id="pat_test",
        patient_context={
            "age": 45,
            "allergies": ["penicilina"],
            "weight": 70
        }
    )
    print("✓ Agent created\n")
    
    # Test conversation turn
    print("2. Processing conversation turn...")
    result = await agent.process_conversation_turn(
        speaker="PACIENTE",
        text="Tengo dolor de cabeza desde hace 3 días y un poco de fiebre",
        auto_extract=True
    )
    print(f"✓ Extracted info: {json.dumps(result['extracted_info'], indent=2, ensure_ascii=False)}")
    print(f"✓ Suggestions: {len(result.get('suggestions', []))} suggestions")
    print(f"✓ Alerts: {len(result.get('alerts', []))} alerts\n")
    
    # Test clinical reasoning
    print("3. Getting clinical reasoning...")
    reasoning = await agent.get_clinical_reasoning(
        query="¿Qué diagnósticos diferenciales debo considerar para este dolor de cabeza con fiebre?",
        use_pubmed=False  # Set to True if you have PubMed configured
    )
    print(f"✓ Reasoning: {json.dumps(reasoning['reasoning'], indent=2, ensure_ascii=False)}\n")
    
    # Test medication validation
    print("4. Validating prescription...")
    validation = await agent.validate_complete_prescription([
        {
            "name": "paracetamol",
            "dose": "500mg",
            "frequency": "cada 8 horas",
            "route": "oral"
        }
    ])
    print(f"✓ Safe to prescribe: {validation['safe_to_prescribe']}")
    print(f"✓ Warnings: {validation['warnings']}")
    print(f"✓ Critical issues: {validation['critical_issues']}\n")
    
    # Test next steps
    print("5. Getting next steps...")
    next_steps = await agent.suggest_next_steps()
    if next_steps.get('next_steps'):
        for i, step in enumerate(next_steps['next_steps'][:3], 1):
            print(f"   {i}. [{step.get('priority', 'N/A')}] {step.get('step', 'N/A')}")
    print()
    
    # Get summary
    print("6. Getting conversation summary...")
    summary = agent.get_conversation_summary()
    print(f"✓ Encounter ID: {summary['encounter_id']}")
    print(f"✓ Symptoms: {summary.get('symptoms', [])}")
    print(f"✓ Diagnoses: {summary.get('diagnoses', [])}")
    print(f"✓ Medications: {len(summary.get('current_medications', []))}")
    print(f"✓ Active alerts: {len(summary.get('active_alerts', []))}\n")
    
    print("✅ All tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_agent())
