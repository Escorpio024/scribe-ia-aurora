# -*- coding: utf-8 -*-
"""CDS (Clinical Decision Support) routes."""

import re
from typing import Dict, Any, List
from fastapi import APIRouter, Body, HTTPException
from api.services.cds_service import get_cds_suggestions

router = APIRouter()


@router.post("/cds/suggest")
async def suggest_clinical_decisions(payload: Dict[str, Any] = Body(...)):
    """
    Get clinical decision support suggestions.
    
    Args:
        payload: Context with clinical data
        
    Returns:
        CDS suggestions with evidence
    """
    try:
        ctx_in = payload.get("context") or {}
        use_pubmed = bool(payload.get("use_pubmed", True))
        pubmed_max = int(payload.get("pubmed_max", 5))

        ctx = dict(ctx_in or {})
        texto = (ctx.get("texto") or " ".join([
            str(ctx.get("chief_complaint", "")),
            str(ctx.get("symptoms", "")),
            str(ctx.get("notes", "")),
            str(ctx.get("diagnosis", "")),
        ])).strip().lower()
        if texto:
            ctx["texto"] = texto

        dx = ctx.get("diagnosis")
        if "dx" not in ctx:
            if isinstance(dx, str) and dx.strip():
                ctx["dx"] = [dx.lower()]
            elif isinstance(dx, list):
                ctx["dx"] = [str(d).lower() for d in dx]
            else:
                ctx["dx"] = []

        if "alergias" in ctx and isinstance(ctx["alergias"], list):
            ctx["alergias"] = [str(a).lower() for a in ctx["alergias"]]
        else:
            ctx.setdefault("alergias", [])

        raw = await get_cds_suggestions(ctx, use_pubmed=use_pubmed, pubmed_max=pubmed_max)

        sugs: List[Dict[str, Any]] = []
        for s in (raw or []):
            if not isinstance(s, dict):
                continue
            sug = {
                "id": s.get("id") or s.get("code") or "",
                "type": s.get("type") or "info",
                "message": (s.get("message") or s.get("text") or s.get("guideline") or "").strip(),
                "proposed": s.get("proposed") or s.get("medication") or "",
                "current": s.get("current") or "",
                "actions": s.get("actions") or [],
                "rationale": s.get("rationale") or "",
                "pmids": s.get("pmids") or [],
                "safety_notes": s.get("safety_notes") or []
            }
            if s.get("medication") and s.get("instructions") and not sug["message"]:
                sug["message"] = f"{s.get('medication')}: {s.get('instructions')}".strip(": ")
                if not sug["proposed"]:
                    sug["proposed"] = s.get("medication")
                if "add" not in sug["actions"]:
                    sug["actions"].append("add")
                if sug["type"] == "info":
                    sug["type"] = "medication"

            if not sug["pmids"] and isinstance(s.get("evidence"), list):
                sug["pmids"] = [str(e.get("pmid")) for e in s["evidence"] if isinstance(e, dict) and e.get("pmid")]
            sugs.append(sug)

        # Fallback: Paracetamol suggestion if AAS and GI risk
        try:
            riesgo_gi = bool(re.search(r"ulcer|sangrado|gastritis|anticoagul|warfarin|acenocumar", ctx.get("texto", ""), re.I))
            prescribio_aas = bool(re.search(r"\b(aspirina|aas|ácido\s+acetilsalicílico)\b", ctx.get("texto", ""), re.I))
            if prescribio_aas:
                sugs.append({
                    "id": "SUG-analgesic-001",
                    "type": "medication-alternative",
                    "message": "Paracetamol (acetaminofén) (actual: Aspirina / AAS)",
                    "proposed": "Paracetamol (acetaminofén)",
                    "current": "Aspirina (ácido acetilsalicílico)",
                    "actions": ["add", "replace"],
                    "rationale": "Menor riesgo GI / anticoagulación / <18a.",
                    "pmids": ["23336517", "31562798"],
                    "safety_notes": ["500–1000 mg c/6–8 h (máx. 3–4 g/día). Ajustar en hepatopatía."]
                })
            elif ("fiebre" in ctx.get("texto", "") or "dolor" in ctx.get("texto", "")) and riesgo_gi:
                sugs.append({
                    "id": "SUG-analgesic-002",
                    "type": "medication",
                    "message": "Paracetamol como analgésico/antipirético seguro en riesgo GI",
                    "proposed": "Paracetamol (acetaminofén)",
                    "current": "",
                    "actions": ["add"],
                    "rationale": "Menor riesgo GI que AINEs/AAS.",
                    "pmids": ["23336517"],
                    "safety_notes": ["500–1000 mg c/6–8 h (máx. 3–4 g/día)."]
                })
        except Exception:
            pass

        return {"suggestions": sugs, "ctx_used": ctx}
    except Exception as e:
        raise HTTPException(400, detail=f"cds failed: {e}")
