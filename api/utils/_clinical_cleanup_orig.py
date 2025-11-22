# -*- coding: utf-8 -*-
"""
clinical_cleanup.py
Limpia y normaliza el JSON clínico producido por la IA/ASR para uso en HC y FHIR.

Sin dependencias externas (solo stdlib).
"""

import re
from typing import Dict, Any, Optional, Tuple, List, Union

from api.text_normalizer import clean_text

# =========================================================
# 1) Reglas de normalización (errores ASR -> forma canónica)
#    Se aplican de forma recursiva y segura (límites/rangos).
# =========================================================

NORMALIZATION_MAP = {
    # Síntomas / términos clínicos frecuentes
    r"\btoseca\b": "tos seca",
    r"\btos\s*seca\b": "tos seca",
    r"\basculpaci(o|ó)n\b": "auscultación",
    r"\b(respiratorial(?:es)?)\b": "respiratoria",
    r"\bdisney(a|e)\b": "disnea",
    r"\bensamen\b": "examen",
    r"\bensana\b": "examen",
    r"\b(para)?c(e|i)tamo+l\b": "paracetamol",
    r"\btamol\b": "paracetamol",
    r"\bpar\s*de\s*tamol\b": "paracetamol",
    r"\bneumoni(a|á)\b": "neumonía",
    r"\b(?<!d)olor\b": "dolor",  # corrige 'olor'->'dolor' sin tocar 'dolor'
    r"\bhemogram(as|os|a|o)\b": "hemograma",
    r"\b(d|t)oras\b": "tórax",
    r"\btorax\b": "tórax",
    r"\bsibilanci(a|as)|civilancias|c?vilancias\b": "sibilancias",
    r"\bojens(es)?\b": "urgencias",
    r"\b(b|v)aso\b": "base",
    r"\bder(e)?cha\b": "derecha",
    r"\bizq(u)?ierda\b": "izquierda",
    r"\bhebre\b": "fiebre",

    # Presión / Frecuencia / Temperatura
    r"\bpreci(o|ó)n\b": "presión",
    r"\bprecion\b": "presión",
    r"\bperaci[oó]n\b": "presión",
    r"\b(p|f)?recuen(c|s)ia\b": "frecuencia",
    r"\bcardeac(a|o)\b": "cardíaca",
    r"\bcard[ií]aco\b": "cardíaco",

    # Estudios
    r"\bradi(o|ó)rica\b": "radiografía",
    r"\bradi(o|ó)graf(í|i)a\s+de\s+toda(s)?\b": "radiografía de tórax",
    r"\bradi(o|ó)graf(í|i)a\s+de\s+tor(a|á)x\b": "radiografía de tórax",
    r"\bradi(o|ó)graf(í|i)a\s+de\s+t[óo]rax\b": "radiografía de tórax",

    # Mishear críticos
    r"\bfalta\s+de\s+alegr[ií]a\b": "falta de aire",
    r"\bd[ei]snea\s+intensa?\b": "disnea intensa",
}

# Órdenes/estudios canonizados
CANON_ORDERS = {
    r"radiograf(í|i)a.*t(ó|o)rax": "Radiografía de tórax",
    r"\bhemograma\b": "Hemograma",
}

# Medicamentos canonizados (prescripción estándar si detectado)
CANON_MEDS = {
    r"\bparacetamol\b": "Paracetamol 1 g cada 8 horas por 5 días",
}

# Pistas para enriquecer motivo de consulta en base a EA
MOTIVO_HINTS = {
    "dolor en el pecho": [r"dolor\s*(en|del)?\s*(el)?\s*(pecho|t(ó|o)rax)"],
    "tos seca": [r"\btos\s*seca\b"],
    "fiebre": [r"\bfiebre\b", r"\b38(\.|,)?\s*(°|grados|c)\b"],
    "falta de aire": [r"\bdisnea\b", r"falta\s*de\s*aire"],
}

# =========================================================
# 2) Utilidades de texto
# =========================================================

def _normalize_text_recursively(text: Optional[str]) -> Optional[str]:
    """Aplica NORMALIZATION_MAP en pasadas sucesivas hasta estabilizar."""
    if not text:
        return text
    cur = f" {str(text).lower().strip()} "
    prev = None
    for _ in range(5):  # límite de seguridad
        if cur == prev:
            break
        prev = cur
        for pat, repl in NORMALIZATION_MAP.items():
            cur = re.sub(pat, f" {repl} ", cur, flags=re.IGNORECASE)
    cur = re.sub(r"\s+", " ", cur).strip()
    if cur:
        cur = cur[0].upper() + cur[1:]
    return cur or None

# =========================================================
# 3) Signos vitales
# =========================================================

def parse_blood_pressure(text: str) -> Optional[Tuple[float, float]]:
    """Parsea TA desde “130/85”, “130 sobre 85”, “130 85”, etc.; valida rangos razonables."""
    if not text:
        return None
    t = str(text).lower()
    t = t.replace("sobre", "/").replace("x", "/").replace("-", "/")
    t = re.sub(r"\s+", " ", t)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)", t)
    if not m:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s+(\d+(?:[.,]\d+)?)", t)
    if not m:
        return None
    try:
        s = float(m.group(1).replace(",", "."))
        d = float(m.group(2).replace(",", "."))
        if 50 <= s <= 260 and 30 <= d <= 160:
            return (s, d)
    except Exception:
        pass
    return None

def parse_number(text: Optional[str]) -> Optional[float]:
    """Extrae primer número (con . o ,) de una cadena."""
    if not text:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)", str(text))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except Exception:
        return None

def normalize_vitals(ef: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza TA/FC/FR/Temp/SatO2 con validación de rangos y corrige hallazgos."""
    ef = dict(ef or {})

    # TA
    bp = parse_blood_pressure(ef.get("TA"))
    ef["TA"] = f"{int(round(bp[0]))}/{int(round(bp[1]))}" if bp else None

    # FC
    fc = parse_number(ef.get("FC"))
    ef["FC"] = str(int(round(fc))) if fc is not None and 20 <= fc <= 220 else None

    # FR
    fr = parse_number(ef.get("FR"))
    ef["FR"] = str(int(round(fr))) if fr is not None and 6 <= fr <= 60 else None

    # Temp
    tp = parse_number(ef.get("Temp"))
    if tp is not None and 30.0 <= tp <= 43.0:
        s = f"{tp:.1f}"
        ef["Temp"] = s.rstrip("0").rstrip(".")
    else:
        ef["Temp"] = None

    # SatO2
    sat = parse_number(ef.get("SatO2"))
    ef["SatO2"] = str(int(round(sat))) if sat is not None and 50 <= sat <= 100 else None

    # Hallazgos / Otros textos
    if ef.get("hallazgos"):
        ef["hallazgos"] = _normalize_text_recursively(ef["hallazgos"])
    if ef.get("otros"):
        ef["otros"] = _normalize_text_recursively(ef["otros"])

    # Remueve claves None
    return {k: v for k, v in ef.items() if v is not None}

# =========================================================
# 4) Limpieza de listas (órdenes / recetas / dx)
# =========================================================

def _cleanup_list_of_strings(items: List[str]) -> List[str]:
    """Limpia y deduplica listas de strings libres."""
    out, seen = [], set()
    for text in items or []:
        t = _normalize_text_recursively(str(text))
        if not t:
            continue
        key = t.lower()
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out

def _canon_text(text: Optional[str], mapping: Dict[str, str]) -> Optional[str]:
    """Aplica la primera coincidencia regex del mapeo y devuelve el target canonizado."""
    if not text:
        return None
    for pat, target in mapping.items():
        if re.search(pat, text, flags=re.IGNORECASE):
            return target
    return text

def _cleanup_orders(orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normaliza órdenes/estudios y deduplica."""
    out, seen = [], set()
    for o in orders or []:
        det = _normalize_text_recursively(o.get("detalle") or "")
        if not det:
            continue
        det = _canon_text(det, CANON_ORDERS) or det
        key = det.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"codigo": o.get("codigo"), "detalle": det})
    return out

def _cleanup_recipes(recetas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normaliza prescripciones; mapea a formulaciones estándar si aplica y deduplica."""
    out, seen = [], set()
    for r in recetas or []:
        det = _normalize_text_recursively(r.get("detalle") or "")
        if not det:
            continue
        det = _canon_text(det, CANON_MEDS) or det
        key = det.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"detalle": det})
    return out

def _cleanup_dx(dx_list: List[str]) -> List[str]:
    """Normaliza impresiones diagnósticas y deduplica."""
    out, seen = [], set()
    for d in dx_list or []:
        t = _normalize_text_recursively(d)
        if not t:
            continue
        t = t[0].upper() + t[1:]
        key = t.lower()
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out

# =========================================================
# 5) Enriquecimiento Motivo / Enfermedad Actual
# =========================================================

def _enrich_motivo_enfermedad(motivo: Optional[str], ea: Optional[Union[str, Dict]]) -> Tuple[Optional[str], Optional[Union[str, Dict]]]:
    """Si el motivo es vago, lo enriquece con pistas detectadas en EA."""
    motivo_clean = _normalize_text_recursively(motivo) if motivo else ""

    if isinstance(ea, dict):
        ea_text = " ".join([_normalize_text_recursively(str(v)) or "" for v in ea.values()])
    else:
        ea_text = _normalize_text_recursively(ea) or ""

    if not motivo_clean or len(motivo_clean) < 8:
        pieces, full = [], f"{motivo_clean} {ea_text}".lower()
        for canon, pats in MOTIVO_HINTS.items():
            if any(re.search(p, full) for p in pats):
                pieces.append(canon)
        if pieces:
            motivo_clean = ", ".join(dict.fromkeys(pieces)).capitalize()  # elimina duplicados preservando orden

    return (motivo_clean or None, ea)

# =========================================================
# 6) Movimiento de medicamentos mal ubicados (órdenes -> recetas)
# =========================================================

def _move_meds_from_orders_to_recipes(orders: List[Dict[str, Any]], recetas: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    new_orders, new_recetas = [], list(recetas or [])
    for o in orders or []:
        det = _normalize_text_recursively(o.get("detalle") or "")
        if not det:
            continue
        # Si detecto medicamento, lo paso a recetas con formulación canónica si procede
        med = _canon_text(det, CANON_MEDS)
        if med and re.search(r"\bparacetamol\b", det, flags=re.IGNORECASE):
            new_recetas.append({"detalle": med})
        else:
            new_orders.append(o)
    return new_orders, new_recetas

# =========================================================
# 7) Punto de entrada
# =========================================================

def cleanup_json(j: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normaliza el JSON clínico antes de generar FHIR/HC:
    - Arregla mishear de ASR (español clínico)
    - Normaliza signos vitales
    - Canonicaliza órdenes y recetas; mueve fármacos desde órdenes a recetas
    - Enriquecer motivo con pistas de EA
    - Deduplica y elimina campos vacíos
    """
    j = dict(j or {})

    # Motivo / Enfermedad Actual (acepta dict o string)
    motivo = j.get("motivo_consulta")
    ea = j.get("enfermedad_actual")
    if isinstance(ea, dict):
        ea_norm = {k: _normalize_text_recursively(v) for k, v in ea.items() if isinstance(v, str)}
        ea_norm = {k: v for k, v in ea_norm.items() if v}
        ea = ea_norm or None
    else:
        ea = _normalize_text_recursively(ea) if ea else None

    motivo, ea = _enrich_motivo_enfermedad(motivo, ea)
    j["motivo_consulta"] = motivo
    j["enfermedad_actual"] = ea

    # Examen físico
    j["examen_fisico"] = normalize_vitals(j.get("examen_fisico") or {})

    # Diagnósticos
    j["impresion_dx"] = _cleanup_dx(j.get("impresion_dx") or [])

    # Plan (texto libre)
    j["plan"] = _normalize_text_recursively(j.get("plan"))

    # Órdenes / Recetas
    orders_clean = _cleanup_orders(j.get("ordenes") or [])
    recipes_clean = _cleanup_recipes(j.get("recetas") or [])
    orders_clean, recipes_clean = _move_meds_from_orders_to_recipes(orders_clean, recipes_clean)
    j["ordenes"] = _cleanup_orders(orders_clean)   # re-limpia por si cambió algo
    j["recetas"] = _cleanup_recipes(recipes_clean)

    # Alertas / Texto legible
    j["alertas"] = _cleanup_list_of_strings(j.get("alertas") or [])
    j["texto_legible"] = _normalize_text_recursively(j.get("texto_legible"))

    # Elimina claves vacías
    def _nonempty(v: Any) -> bool:
        if v is None:
            return False
        if isinstance(v, str):
            return v.strip() != ""
        if isinstance(v, (list, dict)):
            return len(v) > 0
        return True

    return {k: v for k, v in j.items() if _nonempty(v)}

