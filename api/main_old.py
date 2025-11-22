# api/main.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import re
from typing import Dict, Any, List, Optional

from api.rule_extract import extract_from_transcript, dedupe_letters
from api.fast_engine import fast_generate, hash_transcript

import httpx
from fastapi import FastAPI, UploadFile, File, Query, Body, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator

from api.config import (
    API_HOST, API_PORT, TMP_DIR, FHIR_BASE_URL, CORS_ALLOWED, KNOWLEDGE_DIR
)
from api.deps_asr import transcribe_file
from api.template_router import pick_schema_from_transcript  # async
from api.text_normalizer import normalize_transcript_turns
from api.nlp_pipeline import generate_structured_json
from api.clinical_cleanup import cleanup_json
from api.fhir_builder import build_bundle
from api.augment import augment_with_pubmed
from api.pubmed import pubmed_search, pubmed_ingest_to_files

# Intentar cargar CDS nuevo
try:
    from api.cds import suggest_cds, build_context_from_json
    _CDS_ENTRY = "suggest_cds"
except Exception:
    from api.cds import suggest_analgesic as suggest_cds, build_context_from_json  # type: ignore
    _CDS_ENTRY = "suggest_analgesic"

app = FastAPI(title="Scribe IA API", version="2.3.0")

allow_origins = CORS_ALLOWED if isinstance(CORS_ALLOWED, list) else [CORS_ALLOWED]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Turn(BaseModel):
    speaker: str = Field(..., description="DOCTOR/PACIENTE/u otro")
    text: str = Field(..., min_length=1)
    t0: Optional[float] = None
    t1: Optional[float] = None
    clinical: Optional[bool] = None

    @validator("speaker", pre=True, always=True)
    def _norm_speaker(cls, v):
        return (v or "").strip().upper()

class GenerateBody(BaseModel):
    encounter_id: str
    patient_id: str
    practitioner_id: str
    schema_id: str = "auto"
    transcript: List[Turn] = Field(..., min_items=1)

_VITALS_RX = re.compile(
    r"""
    (?:TA[:\s]*([\d]{2,3}\s*[\/]\s*[\d]{2,3}))?
    .*?(?:FC[:\s]*([\d]{2,3}))?
    .*?(?:FR[:\s]*([\d]{2,3}))?
    .*?(?:Temp(?:eratura)?[:\s]*([\d]{2}(?:[.,]\d{1})?))?
    .*?(?:SatO2?[:\s]*([\d]{2,3}))?
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE
)

def _join_texts(turns: List[Dict[str, Any]]) -> str:
    return " ".join([ (t.get("text") or "").strip() for t in (turns or []) if (t.get("text") or "").strip() ])

def _pick_first_text(turns: List[Dict[str, Any]], speaker="PACIENTE") -> str:
    for t in (turns or []):
        if (t.get("speaker","") or "").upper() == speaker and t.get("text"):
            return t["text"].strip()
    return ""

def _guess_schema_from_text(txt: str) -> str:
    low = (txt or "").lower()
    if any(k in low for k in ["diarrea", "vómit", "vomit", "gastroenter", "heces", "deshidrat"]):
        return "gastroenteritis_aguda"
    if any(k in low for k in ["tos", "disnea", "fiebre", "neumon", "saturación", "sato2"]):
        return "respiratoria_aguda"
    if any(k in low for k in ["dolor en el pecho", "dolor torácico", "opresión torácica"]):
        return "dolor_toracico"
    return "consulta_general"

def _extract_vitals(block_text: str):
    m = _VITALS_RX.search(block_text or "")
    if not m:
        return {}
    TA, FC, FR, Temp, Sat = m.groups()
    out: Dict[str, Any] = {}
    if TA:   out["TA"]   = TA.replace(" ", "")
    if FC:   out["FC"]   = FC
    if FR:   out["FR"]   = FR
    if Temp: out["Temp"] = Temp.replace(",", ".")
    if Sat:  out["SatO2"]= Sat
    return out

def _heuristic_json(transcript: list) -> dict:
    turns = transcript or []
    texto_total = _join_texts(turns)

    motivo = _pick_first_text(turns, "PACIENTE") or "Motivo no especificado."
    ea_lines = [ (t.get("text") or "").strip()
                 for t in turns if (t.get("speaker","").upper()=="PACIENTE" and (t.get("text") or "").strip()) ]
    enfermedad_actual = "\n".join(ea_lines) if ea_lines else motivo

    examen_block = ""
    for t in turns:
        tx = (t.get("text") or "")
        if re.search(r"(signos\s+vitales|signos:|examen[: ]|exploraci[oó]n)", tx, re.I):
            examen_block = tx
            break
    vitals = _extract_vitals(examen_block or texto_total)

    hall = None
    for t in turns:
        tx = (t.get("text") or "")
        if re.search(r"(mucosas|abdomen|crepitantes|edema|pliegue|yugular|hepatomegalia|ruidos)", tx, re.I):
            hall = tx if not hall else f"{hall}\n{tx}"

    imp: List[str] = []
    low = texto_total.lower()
    # Heurística IC
    ic_hits = 0
    for rx in [
        r"\b(ortopnea|dos almohadas|al\ acostarse|parox[ií]stica nocturna|me despert[eé] ahog[aá]ndome)\b",
        r"\b(edema|hinchaz[oó]n).*(piernas|tobillos|maleolar)\b",
        r"\bingurgitaci[oó]n yugular|\bIY\b",
        r"\bcrepitantes\b",
        r"\bS3\b",
        r"\bsubido\b.*\bkilo",
    ]:
        if re.search(rx, low): ic_hits += 1

    if ic_hits >= 2 and re.search(r"\bfalta de aire|disnea|me cuesta respirar\b", low):
        imp.append("Insuficiencia cardiaca aguda descompensada (probable)")
    elif any(k in low for k in ["tos","disnea","fiebre","neumon"]):
        imp.append("Infección respiratoria (evaluar)")
    elif any(k in low for k in ["dolor en el pecho","dolor torácico"]):
        imp.append("Dolor torácico (estratificar riesgo)")
    else:
        imp.append("Síndrome inespecífico, requiere aclaración diagnóstica")

    ordenes: List[Dict[str,str]] = []
    recetas: List[Dict[str,str]] = []
    alertas: List[str] = []

    if any("insuficiencia cardiaca" in d.lower() for d in imp):
        ordenes = [
            {"detalle": "Rx de tórax PA/L lateral"},
            {"detalle": "BNP/NT-proBNP, hemograma, perfil renal/electrolitos"},
            {"detalle": "EKG y troponina"},
            {"detalle": "Control de balance hídrico y diuresis"},
        ]
        recetas = [{"detalle": "Furosemida 20–40 mg VO (o IV según criterio) y ajuste según respuesta"}]
        alertas = [
            "Disnea en reposo o progresiva",
            "Dolor torácico",
            "SatO2 < 90% o cianosis",
            "Oliguria/anuria",
            "Síncope o confusión",
        ]
    elif any(k in " ".join(imp).lower() for k in ["respiratoria","neumon","disnea","tos"]):
        ordenes = [
            {"detalle": "Rx tórax + hemograma si fiebre alta/hipoxemia"},
            {"detalle": "SatO2 seriada / control de signos"},
        ]

    return {
        "motivo_consulta": motivo,
        "enfermedad_actual": enfermedad_actual,
        "examen_fisico": {**vitals, **({"hallazgos": hall} if hall else {})},
        "impresion_dx": imp,
        "ordenes": ordenes,
        "recetas": recetas,
        "alertas": alertas,
        # 👇 campos nuevos para que el front pueda mostrarlos siempre:
        "antecedentes": {},
        "revision_sistemas": {}
    }

@app.get("/health")
async def health():
    return {"status": "ok", "cds_entry": _CDS_ENTRY}

@app.post("/ingest/upload")
async def ingest_upload(
    encounter_id: str = Query(..., description="ID del encuentro"),
    wav: UploadFile = File(..., description="WAV mono 16k (o se re-muestrea en backend)")
):
    try:
        os.makedirs(TMP_DIR, exist_ok=True)
        path = os.path.join(TMP_DIR, f"{encounter_id}.wav")
        raw = await wav.read()
        with open(path, "wb") as f:
            f.write(raw)
        transcript = transcribe_file(path)  # -> List[dict]
        return {"encounter_id": encounter_id, "transcript": transcript, "stored_wav": path}
    except Exception as e:
        raise HTTPException(500, f"ingest failed: {e}")

@app.post("/nlp/generate")
async def nlp_generate(body: GenerateBody):
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

    # 1) normalizar transcript
    try:
        transcript = normalize_transcript_turns(transcript)
        result["_debug"]["transcript_len"] = len(transcript)
    except Exception as e:
        result["_debug"]["warn_norm_transcript"] = f"{type(e).__name__}: {e}"

    # 2) schema
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

    # 3) JSON clínico con LLM (+ fallback)
    try:
        json_clinico = await generate_structured_json(
            schema_used,
            transcript,
            extra_context="Detecta también alertas clínicas, signos de alarma, criterios de urgencia y recomendaciones específicas al paciente. Incluye antecedentes (personales, farmacológicos, alergias) y revisión por sistemas."
        )
        if not isinstance(json_clinico, dict) or not json_clinico or len(json_clinico.keys()) < 2:
            raise ValueError("LLM devolvió vacío/insuficiente")
        result["json_clinico"] = json_clinico
    except Exception as e:
        result["_debug"]["err_llm"] = f"{type(e).__name__}: {e}"
        result["json_clinico"] = _heuristic_json(transcript)

    # 4) limpieza clínica
    try:
        result["json_clinico"] = cleanup_json(result["json_clinico"])
    except Exception as e:
        result["_debug"]["warn_cleanup"] = f"{type(e).__name__}: {e}"

    # 4.1) enriquecer con reglas (antecedentes/ROS/EF/alertas) sin pisar
    try:
        heur = extract_from_transcript(transcript)
        jc = result["json_clinico"] = result.get("json_clinico") or {}

        def _merge_obj(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
            out = dict(dst or {})
            for k,v in (src or {}).items():
                if isinstance(v, dict):
                    out[k] = _merge_obj(out.get(k, {}), v)
                else:
                    out[k] = v if k not in out or not out[k] else out[k]
            return out

        jc["antecedentes"] = _merge_obj(jc.get("antecedentes", {}), heur.get("antecedentes", {}))
        jc["revision_sistemas"] = _merge_obj(jc.get("revision_sistemas", {}), heur.get("revision_sistemas", {}))
        jc["examen_fisico"] = _merge_obj(jc.get("examen_fisico", {}), heur.get("examen_fisico", {}))
        if heur.get("alertas"):
            jc["alertas"] = sorted(list(set((jc.get("alertas") or []) + heur["alertas"])))
    except Exception as e:
        result["_debug"]["warn_rules_enrich"] = f"{type(e).__name__}: {e}"

    # 5) augment (PubMed)
    try:
        result["augment"] = augment_with_pubmed(
            result["json_clinico"], schema_used=schema_used, top_k=12
        )
    except Exception as e:
        result["_debug"]["warn_augment"] = f"{type(e).__name__}: {e}"

    # 6) FHIR
    try:
        result["fhir_bundle"] = build_bundle(
            encounter_id=payload["encounter_id"],
            patient_id=payload["patient_id"],
            practitioner_id=payload["practitioner_id"],
            json_clinico=result["json_clinico"],
        )
    except Exception as e:
        result["_debug"]["warn_fhir_bundle"] = f"{type(e).__name__}: {e}"
        result["fhir_bundle"] = {}

    # 7) CDS
    try:
        ctx = build_context_from_json(result["json_clinico"])
        ctx["_schema"] = schema_used
        raw_sugs = await suggest_cds(ctx, use_pubmed=True, pubmed_max=5)

        def _normalize(sugs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            out: List[Dict[str, Any]] = []
            for s in (sugs or []):
                if not isinstance(s, dict): continue
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
        result["cds_suggestions"] = _normalize(raw_sugs or [])
    except Exception as e:
        result["_debug"]["warn_cds"] = f"{type(e).__name__}: {e}"
        result["cds_suggestions"] = []

    return result

@app.post("/nlp/augment")
async def nlp_augment(payload: Dict[str, Any] = Body(...)):
    try:
        j = payload.get("json_clinico") or payload
        schema_used = payload.get("schema_used")
        return augment_with_pubmed(j, schema_used=schema_used, top_k=12)
    except Exception as e:
        raise HTTPException(500, f"augment failed: {e}")

@app.post("/fhir/push")
async def fhir_push(bundle: Dict[str, Any] = Body(...)):
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                FHIR_BASE_URL,
                json=bundle,
                headers={"Content-Type": "application/fhir+json"},
            )
        if r.status_code >= 300:
            raise HTTPException(r.status_code, f"FHIR error: {r.text}")
        return {"status": "ok", "response": r.json()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"push failed: {e}")

@app.get("/knowledge/list")
async def knowledge_list():
    try:
        os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
        files = [f for f in os.listdir(KNOWLEDGE_DIR) if not f.startswith(".")]
        return {"count": len(files), "files": files}
    except Exception as e:
        raise HTTPException(500, f"knowledge list failed: {e}")

@app.post("/knowledge/upsert")
async def knowledge_upsert(
    name: str = Query(..., description="nombre del archivo en KNOWLEDGE_DIR"),
    content: str = Body(..., media_type="text/plain"),
):
    try:
        os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
        path = os.path.join(KNOWLEDGE_DIR, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"status": "ok", "path": path}
    except Exception as e:
        raise HTTPException(500, f"knowledge upsert failed: {e}")

@app.get("/pubmed/search")
async def pubmed_proxy(q: str, retmax: int = 5):
    try:
        return await pubmed_search(q, retmax=retmax)
    except Exception as e:
        raise HTTPException(502, f"PubMed error: {e}")

@app.post("/pubmed/bootstrap")
async def pubmed_bootstrap(
    q: str = Query(..., description="query PubMed"),
    total: int = Query(500, ge=1, le=5000),
):
    try:
        out_dir = os.path.join(KNOWLEDGE_DIR, "pubmed")
        res = await pubmed_ingest_to_files(q=q, total=total, out_dir=out_dir)
        return {"status": "ok", **res, "out_dir": out_dir}
    except Exception as e:
        raise HTTPException(500, f"bootstrap failed: {e}")

@app.post("/cds/suggest")
async def cds_suggest(payload: Dict[str, Any] = Body(...)):
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
        if texto: ctx["texto"] = texto

        dx = ctx.get("diagnosis")
        if "dx" not in ctx:
            if isinstance(dx, str) and dx.strip(): ctx["dx"] = [dx.lower()]
            elif isinstance(dx, list): ctx["dx"] = [str(d).lower() for d in dx]
            else: ctx["dx"] = []

        if "alergias" in ctx and isinstance(ctx["alergias"], list):
            ctx["alergias"] = [str(a).lower() for a in ctx["alergias"]]
        else:
            ctx.setdefault("alergias", [])

        raw = await suggest_cds(ctx, use_pubmed=use_pubmed, pubmed_max=pubmed_max)

        sugs: List[Dict[str, Any]] = []
        for s in (raw or []):
            if not isinstance(s, dict): continue
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
                if not sug["proposed"]: sug["proposed"] = s.get("medication")
                if "add" not in sug["actions"]: sug["actions"].append("add")
                if sug["type"] == "info": sug["type"] = "medication"

            if not sug["pmids"] and isinstance(s.get("evidence"), list):
                sug["pmids"] = [str(e.get("pmid")) for e in s["evidence"] if isinstance(e, dict) and e.get("pmid")]
            sugs.append(sug)

        # Fallback analgésico: Paracetamol si AAS y riesgo GI
        try:
            riesgo_gi = bool(re.search(r"ulcer|sangrado|gastritis|anticoagul|warfarin|acenocumar", ctx.get("texto",""), re.I))
            prescribio_aas = bool(re.search(r"\b(aspirina|aas|ácido\s+acetilsalicílico)\b", ctx.get("texto",""), re.I))
            if prescribio_aas:
                sugs.append({
                    "id": "SUG-analgesic-001",
                    "type": "medication-alternative",
                    "message": "Paracetamol (acetaminofén) (actual: Aspirina / AAS)",
                    "proposed": "Paracetamol (acetaminofén)",
                    "current": "Aspirina (ácido acetilsalicílico)",
                    "actions": ["add","replace"],
                    "rationale": "Menor riesgo GI / anticoagulación / <18a.",
                    "pmids": ["23336517","31562798"],
                    "safety_notes": ["500–1000 mg c/6–8 h (máx. 3–4 g/día). Ajustar en hepatopatía."]
                })
            elif ("fiebre" in ctx.get("texto","") or "dolor" in ctx.get("texto","")) and riesgo_gi:
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

# Print router (si usas /print/*)
from api.printouts import router as print_router
app.include_router(print_router, prefix="/print", tags=["print"])

CACHE: Dict[str, Dict[str,Any]] = {}

@app.post("/nlp/fast_generate")
async def nlp_fast_generate(body: GenerateBody):
    tx = [t.model_dump() if hasattr(t, "model_dump") else dict(t) for t in body.transcript]
    key = hash_transcript(tx)
    if key in CACHE:
        return {"json_clinico": CACHE[key], "schema_used": "fastpath"}
    jc = fast_generate(tx)
    CACHE[key] = jc
    bundle = build_bundle(body.encounter_id, body.patient_id, body.practitioner_id, jc)
    return {"json_clinico": jc, "fhir_bundle": bundle, "schema_used": "fastpath"}

# api/postprocess.py
import re
from datetime import datetime

MAX_EA = 380  # recorte de Enfermedad Actual si viene muy larga

def _lower(s): return (s or "").lower()

def compact_enfermedad_actual(ea):
    if not ea:
        return ea
    if isinstance(ea, dict):
        return ea
    s = re.sub(r"\s+", " ", str(ea)).strip()
    if len(s) <= MAX_EA:
        return s
    parts = re.split(r"(?<=\.)\s+", s)
    out = []
    for p in parts:
        out.append(p)
        if len(" ".join(out)) > MAX_EA:
            break
    clipped = " ".join(out).strip()
    return (clipped[:MAX_EA-1].rstrip() + "…") if len(clipped) > MAX_EA else clipped

def extract_rules_from_transcript(transcript):
    T = " . ".join([_lower(t.get("text","")) for t in (transcript or [])])

    ant = {
        "personales": [], "patologicos": [], "quirurgicos": [],
        "farmacologicos": [], "alergias": [], "gineco_obstetricos": [],
        "toxicos_habitos": [], "familiares": [], "psicosociales": []
    }
    ros = {
        "general": [], "respiratorio": [], "cardiovascular": [], "digestivo": [],
        "genitourinario": [], "neurologico": [], "dermatologico": [], "musculoesqueletico": []
    }
    ef = {}

    # antecedentes / fármacos / hábitos
    if "hipertens" in T:
        ant["personales"].append("Hipertensión arterial")
        ant["patologicos"].append("Hipertensión arterial")
    if "cardiopat" in T:
        ant["personales"].append("Cardiopatía")

    if "losart" in T:     ant["farmacologicos"].append("Losartán 50 mg/día")
    if "furosemida" in T: ant["farmacologicos"].append("Furosemida 20 mg mañana (olvidos esporádicos)")
    if "ibuprofeno" in T: ant["farmacologicos"].append("Ibuprofeno (reciente)")

    if "sin alerg" in T or "no alerg" in T:
        ant["alergias"].append("Sin alergias conocidas")

    if "no fumo" in T or "no fuma" in T:
        ant["toxicos_habitos"].append("No fuma")
    if "sal" in T and ("más" in T or "mas" in T or "alta" in T):
        ant["toxicos_habitos"].append("Ingesta de sal aumentada")

    # ROS
    if any(k in T for k in ["disnea","falta de aire","ahog"]):
        ros["respiratorio"].extend(["Disnea de esfuerzo","Ortopnea","Disnea paroxística nocturna"])
    if "tos" in T and "seca" in T:
        ros["respiratorio"].append("Tos seca")
    if any(k in T for k in ["palpitaciones","rápido","rapido"]):
        ros["cardiovascular"].append("Palpitaciones")
    if any(k in T for k in ["edema","hinchazón","hinchazon","tobillos"]):
        ros["musculoesqueletico"].append("Edema maleolar")
    if any(k in T for k in ["orino menos","orino poco","diuresis"]):
        ros["genitourinario"].append("Diuresis disminuida")
    if any(k in T for k in ["aumento de peso","subido","3 kilos"]):
        ros["general"].append("Aumento de peso reciente")

    # EF
    m = re.search(r"ta\s*(\d{2,3}\s*/\s*\d{2,3})", T, re.I)
    if m: ef["TA"] = m.group(1).replace(" ","")
    m = re.search(r"fc\s*(\d{2,3})", T, re.I)
    if m: ef["FC"] = m.group(1)
    m = re.search(r"fr\s*(\d{2,3})", T, re.I)
    if m: ef["FR"] = m.group(1)
    m = re.search(r"(\b3[5-9](?:[.,]\d+)?)\s*°?\s*c", T, re.I)
    if m: ef["Temp"] = m.group(1).replace(",","." )
    m = re.search(r"sato2\s*(\d{2,3})\s*%", T, re.I)
    if m: ef["SatO2"] = m.group(1)

    hall = []
    if "crepitantes" in T: hall.append("Crepitantes bibasales")
    if "ingurgit" in T:    hall.append("Ingurgitación yugular +")
    if "hepatomeg" in T:   hall.append("Hepatomegalia leve")
    if "edema" in T:       hall.append("Edema blando maleolar bilateral +/++")
    if "s3" in T:          hall.append("S3 audible")
    if "sin soplos" in T:  hall.append("Sin soplos evidentes")
    if hall:
        ef["hallazgos"] = ", ".join(hall) + "."

    # dedup/limpieza
    for k in ant:
        if isinstance(ant[k], list):
            ant[k] = sorted(list({x.strip() for x in ant[k] if x.strip()}))
    for k in ros:
        if isinstance(ros[k], list):
            ros[k] = sorted(list({x.strip() for x in ros[k] if x.strip()}))
    return ant, ros, ef

def merge_and_normalize(json_llm: dict, transcript: list) -> dict:
    out = {"json_clinico": {
        "identificacion": {},
        "motivo_consulta": "",
        "enfermedad_actual": {},
        "antecedentes": {},
        "revision_sistemas": {},
        "examen_fisico": {},
        "impresion_dx": [],
        "plan_manejo": {"ordenes": [], "recetas": [], "recomendaciones": []},
        "evolucion": []
    }}

    jc = (json_llm or {}).get("json_clinico", {})
    for k in out["json_clinico"].keys():
        if k in jc:
            out["json_clinico"][k] = jc[k]

    ant_r, ros_r, ef_r = extract_rules_from_transcript(transcript)

    out["json_clinico"]["antecedentes"] = { **ant_r, **(out["json_clinico"].get("antecedentes") or {}) }
    out["json_clinico"]["revision_sistemas"] = { **ros_r, **(out["json_clinico"].get("revision_sistemas") or {}) }
    out["json_clinico"]["examen_fisico"] = { **ef_r, **(out["json_clinico"].get("examen_fisico") or {}) }

    ea = out["json_clinico"].get("enfermedad_actual")
    out["json_clinico"]["enfermedad_actual"] = compact_enfermedad_actual(ea)

    ident = out["json_clinico"].get("identificacion") or {}
    ident.setdefault("fecha", datetime.now().strftime("%Y-%m-%d %H:%M"))
    ident.setdefault("servicio", "Consulta General")
    out["json_clinico"]["identificacion"] = ident

    plan = out["json_clinico"].get("plan_manejo") or {}
    plan.setdefault("ordenes", plan.get("ordenes") or [])
    plan.setdefault("recetas", plan.get("recetas") or [])
    plan.setdefault("recomendaciones", plan.get("recomendaciones") or [])
    out["json_clinico"]["plan_manejo"] = plan

    return out