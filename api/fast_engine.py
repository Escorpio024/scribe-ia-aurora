# api/fast_engine.py
# -*- coding: utf-8 -*-
import hashlib, re
from typing import List, Dict, Any

def hash_transcript(transcript: List[Dict[str,Any]]) -> str:
    s = " ".join([ (t.get("speaker","")+": "+t.get("text","")) for t in (transcript or []) ])
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:12]

def _first_patient_text(tx: List[Dict[str,Any]]) -> str:
    for t in tx:
        if (t.get("speaker","") or "").upper().startswith("PAC"):
            return (t.get("text") or "").strip()
    return (tx[0].get("text") or "").strip() if tx else ""

def fast_generate(transcript: List[Dict[str,Any]]) -> Dict[str,Any]:
    low = " ".join((t.get("text") or "").lower() for t in transcript)
    motivo = _first_patient_text(transcript)

    # Diagnósticos y plan rápidos (GI demo)
    dx = []
    ordenes = []
    recetas = []
    alertas = []

    if any(k in low for k in ["diarrea","vómit","vomit","heces","deshidrat"]):
        dx = ["Gastroenteritis aguda"]
        if re.search(r"\borino poco|mucosas secas|pliegue\s+cut[aá]neo", low):
            dx.append("Deshidratación (sospecha)")
        ordenes = [
            "Hidratación oral con SRO en tomas fraccionadas",
            "Dieta blanda; evitar lácteos/grasas 24–48 h",
            "Coprológico/electrolitos si >72 h o sangre en heces"
        ]
        recetas = [
            "Ondansetrón 4 mg VO c/8h si náuseas (máx 3/día)",
            "S. boulardii 250 mg VO c/12h por 5 días"
        ]
        alertas = [
            "Anuria >8 h, vómitos incoercibles, sangre en heces o somnolencia → urgencias"
        ]

    return {
        "motivo_consulta": motivo or "Motivo no especificado",
        "enfermedad_actual": " ".join((t.get("text") or "").strip() for t in transcript if (t.get("text") or "").strip()),
        "examen_fisico": {},
        "impresion_dx": dx or ["Síndrome inespecífico"],
        "ordenes": [{"detalle": x} for x in ordenes],
        "recetas": [{"detalle": x} for x in recetas],
        "alertas": alertas
    }