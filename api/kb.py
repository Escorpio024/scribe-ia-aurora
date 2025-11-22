# api/kb.py
import json, os, re
from typing import Dict, Any

KB_DIR = os.path.join(os.path.dirname(__file__), "kb_data")

def _load(name: str) -> Dict[str,Any]:
    with open(os.path.join(KB_DIR, f"{name}.json"), "r", encoding="utf-8") as f:
        return json.load(f)

def suggest_dx_plan_meds(text_low: str, tag: str="general", pediatric: bool=False) -> Dict[str,Any]:
    data = _load("gastro") if tag=="gastro" else _load("general")
    res = {"dx": data[tag]["dx"], "ordenes": list(data[tag]["ordenes"]), "recetas": [], "alertas": list(data[tag]["alertas"])}

    # selecciona adulto/ped
    bucket = "pediatrico" if pediatric else "adulto"
    recs = data[tag]["recetas"].get(bucket, [])
    # Contraindicaciones simples:
    if "qt prolong" in text_low:
        recs = [r for r in recs if "ondansetrón" not in r.lower()]
    res["recetas"] = recs
    return res