# -*- coding: utf-8 -*-
"""NLP processing routes."""

import re
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Body
from api.core.models import GenerateBody
from api.services.nlp_service import generate_clinical_json
from api.services.fhir_service import create_fhir_bundle
from api.services.cds_service import get_cds_suggestions, build_cds_context
from api.services.knowledge_service import augment_with_evidence
from api.utils.rule_extraction import extract_from_transcript
from api.utils.text_processing import normalize_transcript_turns
from api.template_router import pick_schema_from_transcript
from api.fast_engine import fast_generate, hash_transcript

router = APIRouter()

# Cache for fast_generate
CACHE: Dict[str, Dict[str, Any]] = {}


def _join_texts(turns: List[Dict[str, Any]]) -> str:
    """Join all turn texts into a single string."""
    return " ".join([
        (t.get("text") or "").strip()
        for t in (turns or [])
        if (t.get("text") or "").strip()
    ])


def _guess_schema_from_text(txt: str) -> str:
    """Heuristic schema detection from text."""
    low = (txt or "").lower()
    if any(k in low for k in ["diarrea", "vómit", "vomit", "gastroenter", "heces", "deshidrat"]):
        return "gastroenteritis_aguda"
    if any(k in low for k in ["tos", "disnea", "fiebre", "neumon", "saturación", "sato2"]):
        return "respiratoria_aguda"
    if any(k in low for k in ["dolor en el pecho", "dolor torácico", "opresión torácica"]):
        return "dolor_toracico"
    return "consulta_general"


def _merge_obj(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge two dictionaries."""
    out = dict(dst or {})
    for k, v in (src or {}).items():
        if isinstance(v, dict):
            out[k] = _merge_obj(out.get(k, {}), v)
        else:
            out[k] = v if k not in out or not out[k] else out[k]
    return out


def _normalize_suggestions(sugs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize CDS suggestions to consistent format."""
    out: List[Dict[str, Any]] = []
    for s in (sugs or []):
        if not isinstance(s, dict):
            continue
        typ = s.get("type") or "info"
        msg = (s.get("message") or s.get("proposed") or s.get("text") or s.get("guideline") or "").strip()
        if s.get("medication") and s.get("instructions"):
            msg = f"{s.get('medication')}: {s.get('instructions')}".strip(": ")
            typ = "medication"
        if msg:
            pmids = s.get("pmids") or []
            if not pmids and isinstance(s.get("evidence"), list):
                pmids = [str(e.get("pmid")) for e in s["evidence"] if isinstance(e, dict) and e.get("pmid")]
            out.append({
                "id": s.get("id") or s.get("code") or "",
                "type": typ,
                "message": msg,
                "proposed": s.get("proposed") or s.get("medication") or "",
                "current": s.get("current") or "",
                "actions": s.get("actions") or [],
                "rationale": s.get("rationale") or "",
                "pmids": pmids,
                "safety_notes": s.get("safety_notes", [])
            })
    return out


@router.post("/nlp/generate")
async def generate_clinical_history(body: GenerateBody):
    """
    Generate complete clinical history from transcript.
    
    Includes:
    - Clinical JSON generation
    - FHIR bundle creation
    - CDS suggestions
    - PubMed augmentation
    """
    result: Dict[str, Any] = {
        "json_clinico": {},
        "fhir_bundle": {},
        "schema_used": None,
        "router_debug": None,
        "cds_suggestions": [],
        "augment": {},
        "_debug": {},
    }

    try:
        payload = body.model_dump()
        transcript = payload.get("transcript") or []
    except Exception as e:
        raise HTTPException(400, f"generate failed (input-invalid): {e}")

    # 1) Normalize transcript
    try:
        transcript = normalize_transcript_turns(transcript)
        result["_debug"]["transcript_len"] = len(transcript)
    except Exception as e:
        result["_debug"]["warn_norm_transcript"] = f"{type(e).__name__}: {e}"

    # 2) Determine schema
    try:
        schema_used = payload.get("schema_id") or "auto"
        if schema_used == "auto":
            try:
                pick = await pick_schema_from_transcript(transcript)
            except Exception:
                pick = None
            if not pick or not pick.get("schema_id"):
                pick = {"schema_id": _guess_schema_from_text(_join_texts(transcript))}
            result["router_debug"] = pick
            schema_used = (pick or {}).get("schema_id", "consulta_general")
        result["schema_used"] = schema_used
    except Exception as e:
        result["_debug"]["warn_router"] = f"{type(e).__name__}: {e}"
        schema_used = _guess_schema_from_text(_join_texts(transcript)) or "consulta_general"
        result["schema_used"] = schema_used

    # 3) Generate clinical JSON with LLM
    try:
        json_clinico = await generate_clinical_json(
            schema_used,
            transcript,
            extra_context="Detecta también alertas clínicas, signos de alarma, criterios de urgencia y recomendaciones específicas al paciente. Incluye antecedentes (personales, farmacológicos, alergias) y revisión por sistemas."
        )
        if not isinstance(json_clinico, dict) or not json_clinico or len(json_clinico.keys()) < 2:
            raise ValueError("LLM devolvió vacío/insuficiente")
        result["json_clinico"] = json_clinico
    except Exception as e:
        result["_debug"]["err_llm"] = f"{type(e).__name__}: {e}"
        # Fallback heuristic would go here
        result["json_clinico"] = {}

    # 4) Enrich with rule extraction
    try:
        heur = extract_from_transcript(transcript)
        jc = result["json_clinico"] = result.get("json_clinico") or {}

        jc["antecedentes"] = _merge_obj(jc.get("antecedentes", {}), heur.get("antecedentes", {}))
        jc["revision_sistemas"] = _merge_obj(jc.get("revision_sistemas", {}), heur.get("revision_sistemas", {}))
        jc["examen_fisico"] = _merge_obj(jc.get("examen_fisico", {}), heur.get("examen_fisico", {}))
        if heur.get("alertas"):
            jc["alertas"] = sorted(list(set((jc.get("alertas") or []) + heur["alertas"])))
    except Exception as e:
        result["_debug"]["warn_rules_enrich"] = f"{type(e).__name__}: {e}"

    # 5) Augment with PubMed
    try:
        result["augment"] = augment_with_evidence(
            result["json_clinico"], schema_used=schema_used, top_k=12
        )
    except Exception as e:
        result["_debug"]["warn_augment"] = f"{type(e).__name__}: {e}"

    # 6) Build FHIR bundle
    try:
        result["fhir_bundle"] = create_fhir_bundle(
            encounter_id=payload["encounter_id"],
            patient_id=payload["patient_id"],
            practitioner_id=payload["practitioner_id"],
            json_clinico=result["json_clinico"],
        )
    except Exception as e:
        result["_debug"]["warn_fhir_bundle"] = f"{type(e).__name__}: {e}"
        result["fhir_bundle"] = {}

    # 7) Get CDS suggestions
    try:
        ctx = build_cds_context(result["json_clinico"])
        ctx["_schema"] = schema_used
        raw_sugs = await get_cds_suggestions(ctx, use_pubmed=True, pubmed_max=5)
        result["cds_suggestions"] = _normalize_suggestions(raw_sugs or [])
    except Exception as e:
        result["_debug"]["warn_cds"] = f"{type(e).__name__}: {e}"
        result["cds_suggestions"] = []

    return result


@router.post("/nlp/augment")
async def augment_clinical_json(payload: Dict[str, Any] = Body(...)):
    """Augment clinical JSON with PubMed evidence."""
    try:
        j = payload.get("json_clinico") or payload
        schema_used = payload.get("schema_used")
        return augment_with_evidence(j, schema_used=schema_used, top_k=12)
    except Exception as e:
        raise HTTPException(500, f"augment failed: {e}")


@router.post("/nlp/fast_generate")
async def fast_generate_clinical_history(body: GenerateBody):
    """
    Fast path for generating clinical history using cached heuristics.
    
    Bypasses LLM for speed.
    """
    tx = [t.model_dump() if hasattr(t, "model_dump") else dict(t) for t in body.transcript]
    key = hash_transcript(tx)
    
    if key in CACHE:
        return {"json_clinico": CACHE[key], "schema_used": "fastpath"}
    
    jc = fast_generate(tx)
    CACHE[key] = jc
    
    bundle = create_fhir_bundle(
        body.encounter_id,
        body.patient_id,
        body.practitioner_id,
        jc
    )
    
    return {"json_clinico": jc, "fhir_bundle": bundle, "schema_used": "fastpath"}
