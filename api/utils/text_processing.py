# -*- coding: utf-8 -*-
"""Text processing utilities - consolidates text_normalizer.py and clinical_cleanup.py"""

import re
from typing import List, Dict, Any


# ========= Text Normalization =========

def normalize_transcript_turns(transcript: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normaliza los turnos del transcript:
    - Limpia espacios
    - Normaliza speakers
    - Elimina turnos vacíos
    """
    normalized = []
    for turn in transcript:
        text = (turn.get("text") or "").strip()
        if not text:
            continue
        
        speaker = (turn.get("speaker") or "").strip().upper()
        if not speaker:
            speaker = "UNKNOWN"
        
        normalized.append({
            "speaker": speaker,
            "text": text,
            "t0": turn.get("t0"),
            "t1": turn.get("t1"),
            "clinical": turn.get("clinical", True)
        })
    
    return normalized


# ========= Clinical Cleanup =========

def cleanup_json(json_clinico: Dict[str, Any]) -> Dict[str, Any]:
    """
    Limpia y normaliza el JSON clínico:
    - Elimina campos vacíos
    - Normaliza estructuras
    - Limpia texto repetitivo
    """
    if not isinstance(json_clinico, dict):
        return {}
    
    cleaned = {}
    
    for key, value in json_clinico.items():
        # Skip empty values
        if value is None or value == "" or value == [] or value == {}:
            continue
        
        # Clean strings
        if isinstance(value, str):
            # Remove excessive whitespace
            value = re.sub(r'\s+', ' ', value).strip()
            # Remove repetitive tokens like "s s s s"
            value = re.sub(r'\b(\w)\s+\1(\s+\1)+\b', r'\1', value)
        
        # Clean lists
        elif isinstance(value, list):
            value = [
                cleanup_json(item) if isinstance(item, dict) else item
                for item in value
                if item not in (None, "", {}, [])
            ]
            if not value:
                continue
        
        # Clean dicts
        elif isinstance(value, dict):
            value = cleanup_json(value)
            if not value:
                continue
        
        cleaned[key] = value
    
    return cleaned


def normalize_vitals(examen_fisico: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normaliza signos vitales añadiendo unidades si faltan.
    """
    if not isinstance(examen_fisico, dict):
        return {}
    
    normalized = dict(examen_fisico)
    
    # TA debe tener formato XXX/YY
    if "TA" in normalized and normalized["TA"]:
        ta = str(normalized["TA"]).replace(" ", "")
        if "/" in ta and not ta.endswith("mmHg"):
            normalized["TA"] = f"{ta} mmHg"
    
    # FC debe estar en lpm
    if "FC" in normalized and normalized["FC"]:
        fc = str(normalized["FC"]).replace(" ", "")
        if fc.isdigit() and not fc.endswith("lpm"):
            normalized["FC"] = f"{fc} lpm"
    
    # FR debe estar en rpm
    if "FR" in normalized and normalized["FR"]:
        fr = str(normalized["FR"]).replace(" ", "")
        if fr.isdigit() and not fr.endswith("rpm"):
            normalized["FR"] = f"{fr} rpm"
    
    # Temp debe estar en °C
    if "Temp" in normalized and normalized["Temp"]:
        temp = str(normalized["Temp"]).replace(",", ".")
        if not ("°C" in temp or "C" in temp):
            normalized["Temp"] = f"{temp} °C"
    
    # SatO2 debe estar en %
    if "SatO2" in normalized and normalized["SatO2"]:
        sat = str(normalized["SatO2"]).replace(" ", "")
        if sat.replace(".", "").isdigit() and not sat.endswith("%"):
            normalized["SatO2"] = f"{sat}%"
    
    return normalized
