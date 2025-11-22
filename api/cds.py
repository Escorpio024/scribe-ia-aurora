# api/cds.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import re
from typing import Dict, Any, List, Optional

from api.pubmed import pubmed_search
from api.models import get_llm

__all__ = ["build_context_from_json", "suggest_cds"]

# --------- Helpers de texto ---------
def _lower(s: Optional[str]) -> str:
    return (s or "").strip().lower()

def _as_text(x: Any) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        # concatena valores simples
        return " ".join(str(v) for v in x.values() if isinstance(v, (str, int, float)))
    if isinstance(x, list):
        return " ".join(_as_text(v) for v in x)
    return str(x) if x is not None else ""

# --------- Contexto desde JSON clínico ---------
def build_context_from_json(j: Dict[str, Any]) -> Dict[str, Any]:
    j = j or {}
    texto = " ".join([
        _as_text(j.get("motivo_consulta")),
        _as_text(j.get("enfermedad_actual")),
        " ".join(j.get("impresion_dx") or []),
    ]).strip()

    ef = j.get("examen_fisico") or {}
    vitals_text = " ".join([
        str(ef.get("TA") or ""),
        str(ef.get("Temp") or ""),
        str(ef.get("FC") or ""),
        str(ef.get("FR") or ""),
        str(ef.get("SatO2") or ""),
        str(ef.get("hallazgos") or ""),
    ])

    dx_list = j.get("impresion_dx") or []
    dx_list = [str(d).strip().lower() for d in dx_list if str(d).strip()]

    ctx = {
        "chief_complaint": j.get("motivo_consulta") or "",
        "diagnosis": (dx_list[0] if dx_list else ""),
        "dx": dx_list,
        "texto": (texto + " " + vitals_text).strip().lower(),
        "age": j.get("edad") or j.get("age"),
        "alergias": j.get("alergias") or [],
        "vitals": {
            "TA": ef.get("TA"),
            "Temp": ef.get("Temp"),
            "FC": ef.get("FC"),
            "FR": ef.get("FR"),
            "SatO2": ef.get("SatO2"),
        }
    }
    return ctx

# --------- Reglas básicas según escenario ---------
def _is_pediatric(ctx: Dict[str, Any]) -> bool:
    try:
        return int(ctx.get("age") or 0) < 18
    except Exception:
        return False

def _has_term(ctx: Dict[str, Any], *terms: str) -> bool:
    t = ctx.get("texto", "")
    return any(term.lower() in t for term in terms)

def _has_dx(ctx: Dict[str, Any], *terms: str) -> bool:
    dx = ctx.get("dx") or []
    s = " ".join(dx)
    return any(term.lower() in s for term in terms)

def _low_saturation(ctx: Dict[str, Any]) -> bool:
    s = ctx.get("vitals", {}).get("SatO2")
    if not s: return False
    m = re.search(r"(\d{2,3})", str(s))
    if not m: return False
    try:
        return int(m.group(1)) < 93
    except Exception:
        return False

def _fever(ctx: Dict[str, Any]) -> bool:
    text = ctx.get("texto", "")
    if "fiebre" in text: 
        return True
    temp = ctx.get("vitals", {}).get("Temp")
    if temp and re.search(r"\b(38(\.|,)\d|3[89])\b", str(temp)):
        return True
    return False

# --------- PubMed util ---------
async def _pubmed_for(query: str, k: int = 3) -> List[Dict[str, Any]]:
    try:
        res = await pubmed_search(query, retmax=k)
        items = []
        for r in (res.get("results") or [])[:k]:
            items.append({
                "pmid": str(r.get("pmid") or r.get("id") or ""),
                "title": r.get("title") or f"PubMed record {r.get('pmid')}",
                "year": r.get("year"),
            })
        return items
    except Exception:
        return []

# --------- Rerank con LLaMA ---------
async def _rerank_with_llm(ctx: Dict[str, Any], candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """ Reordena/filtra propuestas con LLM para que no repita siempre lo mismo. """
    if not candidates:
        return candidates
    llm = get_llm()
    # preparamos un prompt muy acotado para ranking
    user = (
        "Contexto clínico breve:\n"
        f"- CC: {ctx.get('chief_complaint')}\n"
        f"- DX: {', '.join(ctx.get('dx') or [])}\n"
        f"- Edad: {ctx.get('age')}\n"
        f"- Vitals: {ctx.get('vitals')}\n\n"
        "Candidatos (elige los 3 mejores como lista JSON, con igual formato):\n"
        + "\n".join([f"{i+1}. {c.get('type','info')}: {c.get('message') or c.get('proposed')}" for i,c in enumerate(candidates)])
        + "\n\nResponde SOLO un array JSON con los mejores candidatos (máximo 3)."
    )
    text = await llm.chat(
        messages=[
            {"role": "system", "content": "Eres un asistente clínico. No inventes. Mantén formato JSON."},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=None,
    )
    import json
    try:
        arr = json.loads(text)
        if isinstance(arr, list) and arr:
            # Intentamos mapear por texto para conservar pmids/safety_notes
            m = { (c.get("message") or c.get("proposed") or "").strip(): c for c in candidates }
            out = []
            for it in arr:
                key = (it.get("message") or it.get("proposed") or "").strip()
                out.append(m.get(key, it))
            return out[:3]
    except Exception:
        pass
    return candidates[:3]

# --------- Motor de sugerencias ---------
async def suggest_cds(ctx: Dict[str, Any], use_pubmed: bool = True, pubmed_max: int = 3) -> List[Dict[str, Any]]:
    """
    Devuelve sugerencias contextuales. Evita el 'paracetamol por defecto'.
    Formato:
      {
        "type": "guideline" | "medication" | "order" | "info",
        "message": "...",         # texto legible (también se usa para añadir a órdenes/recetas)
        "proposed": "...",        # opcional, versión más ‘estructura/posología’
        "pmids": ["..."],         # opcional
        "evidence": [{pmid,title,year}],
        "safety_notes": [...]
      }
    """
    suggestions: List[Dict[str, Any]] = []

    # ===== 1) DOLOR TORÁCICO =====
    if _has_dx(ctx, "dolor torácico") or _has_term(ctx, "dolor torácico", "opresivo en el pecho"):
        msg = "Dolor torácico: priorizar protocolo de SCA — ECG y troponinas, monitorización y derivación si inestabilidad."
        item = {
            "type": "guideline",
            "message": msg,
            "safety_notes": ["No retrasar evaluación de SCA por analgesia."],
        }
        if use_pubmed:
            ev = await _pubmed_for("chest pain emergency guideline troponin ECG", k=pubmed_max)
            item["evidence"] = ev
            item["pmids"] = [e["pmid"] for e in ev if e.get("pmid")]
        suggestions.append(item)

        # No sugerimos paracetamol aquí — enfoque diagnóstico primero
        return await _rerank_with_llm(ctx, suggestions)

    # ===== 2) ASMA PEDIÁTRICA =====
    if _is_pediatric(ctx) and (_has_dx(ctx, "asma") or _has_term(ctx, "sibilancias", "asma pediátrica", "tos nocturna")):
        saba = "Salbutamol (SABA) 100 mcg inhalado: 2–4 inhalaciones con cámara, repetir cada 20 min × 1 h si síntomas; luego según respuesta."
        sug1 = {
            "type": "medication",
            "message": saba,
            "proposed": saba,
            "safety_notes": ["Revisar técnica de inhalación y uso de cámara espaciadora."],
        }
        if use_pubmed:
            ev = await _pubmed_for("pediatric asthma acute exacerbation SABA guideline", k=pubmed_max)
            sug1["evidence"] = ev
            sug1["pmids"] = [e["pmid"] for e in ev if e.get("pmid")]
        suggestions.append(sug1)

        sug2 = {
            "type": "order",
            "message": "Educar a cuidadores: plan de acción para asma, disparadores, técnica de inhalador.",
            "safety_notes": [],
        }
        suggestions.append(sug2)

        return await _rerank_with_llm(ctx, suggestions)

    # ===== 3) NEUMONÍA ADQUIRIDA EN LA COMUNIDAD (adulto) =====
    if _has_dx(ctx, "neumonía", "neumonia", "nac") or (_fever(ctx) and _has_term(ctx, "tos", "esputo")):
        base = "En NAC ambulatoria sin criterios de gravedad: control sintomático, hidratación, signos de alarma y reevaluación si empeora."
        sug = {
            "type": "guideline",
            "message": base,
            "safety_notes": ["Derivar si SatO2 baja, taquipnea marcada, hipotensión o alteración del estado mental."],
        }
        if use_pubmed:
            ev = await _pubmed_for("community acquired pneumonia outpatient guideline adult", k=pubmed_max)
            sug["evidence"] = ev
            sug["pmids"] = [e["pmid"] for e in ev if e.get("pmid")]
        suggestions.append(sug)

        # evitar meter siempre un analgésico; solo si hay dolor/fiebre y NO hay contraindicaciones
        if _fever(ctx) and not _has_term(ctx, "alergia a paracetamol", "hepatopatía"):
            par = "Antitérmico/analgésico: paracetamol 500–1000 mg VO cada 8 h según necesidad (máx. 3 g/día en adulto)."
            suggestions.append({
                "type": "medication",
                "message": par,
                "proposed": par,
                "safety_notes": ["Ajustar en hepatopatía, embarazo, o consumo crónico de alcohol."],
            })

        return await _rerank_with_llm(ctx, suggestions)

    # ===== 4) DEFAULT (si nada cuadra) =====
    suggestions.append({
        "type": "info",
        "message": "Sin sugerencias automáticas para este caso.",
        "safety_notes": [],
    })
    return suggestions