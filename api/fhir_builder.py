from datetime import datetime, timezone
import re
from typing import Dict, Any, Optional, List

def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _put_patient(patient_id: str):
    return {
        "request": {"method": "PUT", "url": f"Patient/{patient_id}"},
        "resource": {"resourceType": "Patient","id": patient_id,"name":[{"family":"Prueba","given":["Paciente"]}]}
    }

def _put_practitioner(practitioner_id: str):
    return {
        "request": {"method": "PUT", "url": f"Practitioner/{practitioner_id}"},
        "resource": {"resourceType": "Practitioner","id": practitioner_id,"name":[{"family":"Prueba","given":["Doctor"]}]}
    }

def _post_encounter(patient_id: str, practitioner_id: str):
    return {
        "request": {"method": "POST", "url": "Encounter"},
        "resource": {
            "resourceType": "Encounter",
            "status": "finished",
            "class": {"system":"http://terminology.hl7.org/CodeSystem/v3-ActCode","code":"AMB","display":"Ambulatory"},
            "subject": {"reference": f"Patient/{patient_id}"},
            "participant": [{"individual": {"reference": f"Practitioner/{practitioner_id}"}}],
            "period": {"start": _now_iso(), "end": _now_iso()}
        }
    }

# --- TA parsing ---
def parse_blood_pressure(text: str):
    if not text: return None
    t = str(text).lower().strip()
    t = t.replace("sobre", "/").replace("x","/").replace("-","/")
    t = re.sub(r"\s+", " ", t)
    m = re.search(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", t) or re.search(r"(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)", t)
    if not m: return None
    try:
        return float(m.group(1)), float(m.group(2))
    except: return None

def make_bp_observation(ta_text: str, patient_id: str):
    bp = parse_blood_pressure(ta_text)
    if not bp: return None
    sys, dia = bp
    return {
        "request": {"method": "POST", "url": "Observation"},
        "resource": {
            "resourceType": "Observation",
            "status": "final",
            "category": [{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/observation-category","code":"vital-signs","display":"Vital Signs"}]}],
            "code": {"coding":[{"system":"http://loinc.org","code":"85354-9","display":"Blood pressure panel"}],"text":"Blood Pressure"},
            "subject": {"reference": f"Patient/{patient_id}"},
            "effectiveDateTime": _now_iso(),
            "component": [
                {"code":{"coding":[{"system":"http://loinc.org","code":"8480-6","display":"Systolic"}]},"valueQuantity":{"value": sys,"unit":"mmHg"}},
                {"code":{"coding":[{"system":"http://loinc.org","code":"8462-4","display":"Diastolic"}]},"valueQuantity":{"value": dia,"unit":"mmHg"}},
            ]
        }
    }

def _try_observation_vital(display: str, value: Any, unit: str, patient_id: str):
    if value in (None, ""): return None
    try:
        v = float(str(value).replace(",", ".").split()[0])
    except: return None
    return {
        "request": {"method": "POST", "url": "Observation"},
        "resource": {
            "resourceType": "Observation",
            "status": "final",
            "category": [{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/observation-category","code":"vital-signs","display":"Vital Signs"}]}],
            "code": {"text": display},
            "subject": {"reference": f"Patient/{patient_id}"},
            "effectiveDateTime": _now_iso(),
            "valueQuantity": {"value": v, "unit": unit}
        }
    }

def _condition_from_dx(text: str, patient_id: str):
    if not text: return None
    return {
        "request": {"method":"POST","url":"Condition"},
        "resource": {
            "resourceType": "Condition",
            "clinicalStatus": {"coding":[{"system":"http://terminology.hl7.org/CodeSystem/condition-clinical","code":"active"}]},
            "verificationStatus": {"coding":[{"system":"http://terminology.hl7.org/CodeSystem/condition-ver-status","code":"unconfirmed"}]},
            "subject": {"reference": f"Patient/{patient_id}"},
            "recordedDate": _now_iso(),
            "code": {"text": text}
        }
    }

def _med_request_from_text(text: str, patient_id: str, practitioner_id: str):
    if not text: return None
    return {
        "request": {"method":"POST","url":"MedicationRequest"},
        "resource": {
            "resourceType": "MedicationRequest",
            "status": "active", "intent":"order", "authoredOn": _now_iso(),
            "subject": {"reference": f"Patient/{patient_id}"},
            "requester": {"reference": f"Practitioner/{practitioner_id}"},
            "medicationCodeableConcept": {"text": text},
            "dosageInstruction": [{"text": text}]
        }
    }

def build_bundle(encounter_id: str, patient_id: str, practitioner_id: str, json_clinico: Dict[str, Any]):
    entries: List[Dict[str, Any]] = []
    entries += [_put_patient(patient_id), _put_practitioner(practitioner_id), _post_encounter(patient_id, practitioner_id)]

    ef = (json_clinico or {}).get("examen_fisico", {}) or {}
    if ef.get("TA"): entries.append(make_bp_observation(ef.get("TA"), patient_id))
    for label,unit,key in [("Heart rate","beats/min","FC"),("Respiratory rate","breaths/min","FR"),("Body temperature","°C","Temp"),("Oxygen saturation","%","SatO2")]:
        ob = _try_observation_vital(label, ef.get(key), unit, patient_id)
        if ob: entries.append(ob)

    for dx in (json_clinico or {}).get("impresion_dx", []) or []:
        cond = _condition_from_dx(dx, patient_id)
        if cond: entries.append(cond)

    for rec in (json_clinico or {}).get("recetas", []) or []:
        mr = _med_request_from_text(rec.get("detalle",""), patient_id, practitioner_id)
        if mr: entries.append(mr)
    for ordn in (json_clinico or {}).get("ordenes", []) or []:
        mr = _med_request_from_text(ordn.get("detalle",""), patient_id, practitioner_id)
        if mr: entries.append(mr)

    return {"resourceType":"Bundle","type":"transaction","entry":[e for e in entries if e]}