# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import List, Dict, Any, Tuple
import re
import os

# PubMed booster (nuestro propio módulo)
from api.pubmed import pubmed_search  # async

# ------------------------------------------------------------------------------
# Toggle por ENV
# ------------------------------------------------------------------------------
PUBMED_ROUTER_BOOST = os.getenv("PUBMED_ROUTER_BOOST", "true").lower() == "true"
PUBMED_MAX_PER_DOMAIN = int(os.getenv("PUBMED_MAX_PER_DOMAIN", "25"))  # consulta rápida para enrutado

# Boost máximo a sumar por evidencia PubMed (ligero para no “dominar” la señal clínica)
PUBMED_MAX_BOOST = float(os.getenv("PUBMED_MAX_BOOST", "0.35"))

# ------------------------------------------------------------------------------
# Normalización ligera para compensar errores de ASR (ES)
# ------------------------------------------------------------------------------
_NORMALIZE = [
    (r"\btoseca\b", "tos seca"),
    (r"\btos\s*seca\b", "tos seca"),
    (r"\basculpaci[oó]n\b", "auscultación"),
    (r"\brespiratoriales?\b", "respiratoria"),
    (r"\bdisne[ae]\b", "disnea"),
    (r"\btoras\b", "tórax"),
    (r"\btorats\b", "tórax"),
    (r"\bneumoni[áa]\b", "neumonía"),
    (r"\bsibilanci[ae]s?\b", "sibilancias"),
    (r"\bcrepitantes?\b", "crepitantes"),
    (r"\b(ecg|electrocardiograma)\b", "ecg"),
    (r"\b(troponinas?)\b", "troponina"),
    (r"\b(opresi[oó]n)\s+(tor[áa]cica|pecho)\b", "opresión torácica"),
    (r"\bpresi[oó]n\b", "presión"),
    (r"\bangor\b", "angina"),
    (r"\bhba1c\b", "hbA1c"),
    (r"\b3\s*d[ií]as\b", "tres días"),
]

def _normalize_text(text: str) -> str:
    if not text:
        return ""
    s = " " + text.lower().strip() + " "
    for pat, rep in _NORMALIZE:
        s = re.sub(pat, f" {rep} ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
    return s

# ------------------------------------------------------------------------------
# Reglas por dominio
# ------------------------------------------------------------------------------
_RULES: List[Dict[str, Any]] = [
    {
        "id": "consulta_general",
        "weight": 1.0,
        "any": [
            r"\bconsulta\b", r"\bcontrol\b", r"\bchequeo\b",
            r"\bmalestar\b", r"\bfiebre\b", r"\bdolor\b"
        ],
        "bonus": [
            r"\bcefale[ao]s?\b", r"\bdiarrea\b", r"\bv[oó]mito[s]?\b",
            r"\bresfriado\b", r"\banorexia\b", r"\bastenia\b"
        ],
        "strong": [],
        "pubmed_q": "primary care general symptoms fever pain"
    },
    {
        "id": "respiratoria_aguda",
        "weight": 1.35,
        "any": [
            r"\btos\b", r"\btos seca\b", r"\bdisnea\b", r"\bsaturaci[oó]n\b",
            r"\brespirar\b", r"\bneumon[ií]a\b", r"\bt[óo]rax\b"
        ],
        "bonus": [
            r"\bcrepitantes?\b", r"\bsibilancias?\b", r"\bauscultaci[oó]n\b",
            r"\brales?\b", r"\b(base|l[óo]bulo)\s+(derecha|izquierda)\b",
            r"\bradiograf[ií]a\s+de\s+t[óo]rax\b", r"\bhemograma\b"
        ],
        "strong": [
            r"\bneumon[ií]a\b", r"\bsat(?:uraci[oó]n)?\s*\d{2}\s*%?\b"
        ],
        "pubmed_q": "community acquired pneumonia acute cough dyspnea guideline"
    },
    {
        "id": "dolor_toracico",
        "weight": 1.45,
        "any": [
            r"\bdolor\s+(en\s+)?(el\s+)?pecho\b",
            r"\bopresi[oó]n\s+tor[áa]cica\b",
            r"\bangina\b", r"\btaquicardia\b",
            r"\bdisnea\s+de\s+esfuerzo\b"
        ],
        "bonus": [
            r"\becg\b", r"\btroponina\b", r"\btimi\b", r"\bheart\b",
            r"\birradia(?:do)?\s+(a\s+)?(brazo|mand[ií]bula)\b"
        ],
        "strong": [
            r"\bdolor\s+tor[áa]cico\s+opresivo\b", r"\becg\b", r"\btroponina\b"
        ],
        "pubmed_q": "chest pain risk stratification troponin HEART TIMI"
    },
    {
        "id": "diabetes_control",
        "weight": 1.25,
        "any": [
            r"\bglucosa\b", r"\bhiperglic?emia\b", r"\bmetformina\b",
            r"\binsulina\b", r"\bhb ?a1c\b", r"\bhemoglobina\s+glicosilada\b"
        ],
        "bonus": [
            r"\bretinopat[ií]a\b", r"\bnefropat[ií]a\b", r"\bneuropat[ií]a\b",
            r"\bada\b", r"\bpie\s+diab[eé]tico\b"
        ],
        "strong": [
            r"\bhb ?a1c\s*\d", r"\buso\s+de\s+insulina\b"
        ],
        "pubmed_q": "type 2 diabetes outpatient control A1c guideline ADA"
    }
]

_MIN_SCORE = 1.2  # umbral mínimo

def _score_domain(text: str, rule: Dict[str, Any]) -> Tuple[float, Dict[str, int]]:
    base = sum(1 for pat in rule["any"]   if re.search(pat, text, flags=re.IGNORECASE))
    bonus = sum(1 for pat in rule["bonus"] if re.search(pat, text, flags=re.IGNORECASE))
    strong = sum(1 for pat in rule.get("strong", []) if re.search(pat, text, flags=re.IGNORECASE))
    score = (base + 0.5 * bonus + 1.5 * strong) * rule["weight"]
    return score, {"base": base, "bonus": bonus, "strong": strong}

def _concat_transcript(transcript: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for t in (transcript or []):
        txt = (t.get("text") or "").strip()
        if not txt:
            continue
        spk = (t.get("speaker") or "").strip().upper()
        # Pequeño sesgo a DOCTOR: duplicamos 10% del texto para anclar términos clínicos
        if spk == "DOCTOR":
            parts.append(txt)
            parts.append(txt[: int(len(txt) * 0.1)])
        else:
            parts.append(txt)
    return " ".join(parts)

async def _pubmed_boost(candidates: List[Dict[str, Any]]) -> None:
    """
    Añade un ligero 'boost' a los mejores candidatos consultando PubMed.
    Modifica in-place: cada item del ranking puede recibir 'pmid_count' y 'pmid_boost'.
    """
    if not PUBMED_ROUTER_BOOST:
        return
    # Consultamos rápido solo los 2 mejores por score bruto
    top = candidates[:2]
    for c in top:
        q = c.get("pubmed_q") or ""
        if not q:
            c["pmid_count"] = 0
            c["pmid_boost"] = 0.0
            continue
        try:
            res = await pubmed_search(q=q, retmax=PUBMED_MAX_PER_DOMAIN)
            count = int(res.get("count", 0))
            # booster: saturación suave → más de 200 cuenta como “suficiente”
            ratio = min(count / 200.0, 1.0)
            boost = round(ratio * PUBMED_MAX_BOOST, 3)
            c["pmid_count"] = count
            c["pmid_boost"] = boost
            c["score"] = round(c["score"] + boost, 3)
        except Exception:
            c["pmid_count"] = 0
            c["pmid_boost"] = 0.0
    # Reordenar tras boost
    candidates.sort(key=lambda x: x["score"], reverse=True)

# ------------------------------------------------------------------------------
# API principal
# ------------------------------------------------------------------------------
async def pick_schema_from_transcript(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Decide la plantilla (schema_id) a partir del transcript (con refuerzo PubMed opcional).
    Retorna:
      {
        "schema_id": "...",
        "reason": "explicación breve",
        "score": float,
        "ranking": [...],     # top dominios con contadores y boosts
        "pubmed_boosted": bool
      }
    """
    raw_text = _concat_transcript(transcript)
    text = _normalize_text(raw_text)

    ranking = []
    for r in _RULES:
        score, counters = _score_domain(text, r)
        ranking.append({
            "id": r["id"],
            "score": round(score, 3),
            "counters": counters,
            "weight": r["weight"],
            "pubmed_q": r.get("pubmed_q", "")
        })

    # Orden preliminar
    ranking.sort(key=lambda x: x["score"], reverse=True)

    # Boost por PubMed (opcional)
    boosted = False
    if PUBMED_ROUTER_BOOST:
        await _pubmed_boost(ranking)
        boosted = True

    # Selección final con umbral
    best = ranking[0] if ranking else {"id": "consulta_general", "score": 0.0}
    if best["score"] < _MIN_SCORE:
        best = {"id": "consulta_general", "score": best["score"]}

    return {
        "schema_id": best["id"],
        "reason": f"score={best['score']}, threshold={_MIN_SCORE}",
        "score": best["score"],
        "ranking": ranking[:6],
        "pubmed_boosted": boosted
    }

