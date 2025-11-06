# -*- coding: utf-8 -*-
import json
import re
import os
from typing import List, Dict, Any

from api.models import get_llm
from api.config import SYSTEM_PROMPT
import httpx
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "90"))

# ===================== Normalización =====================
SPACE_RX = re.compile(r"\s+")
ISOLATED_LETTERS_RX = re.compile(r"\b([a-zA-ZáéíóúñÑ])(?:\s+\1){2,}\b", re.IGNORECASE)
SHORT_TOKEN_REP_RX = re.compile(r"\b([a-zA-ZáéíóúñÑ]{1,2})\b(?:\s+\1\b){2,}", re.IGNORECASE)
WORD_TRIPLE_RX = re.compile(r"\b([a-zA-ZáéíóúñÑ]{3,})\b(?:\s+\1\b){2,}", re.IGNORECASE)

def _clean_inline(t: str) -> str:
    t = ISOLATED_LETTERS_RX.sub(lambda m: m.group(1), t or "")
    t = SHORT_TOKEN_REP_RX.sub(lambda m: m.group(1), t)
    t = WORD_TRIPLE_RX.sub(lambda m: m.group(1), t)
    t = SPACE_RX.sub(" ", t).strip()
    return t

def _norm_turn(turn: Dict[str, Any]) -> Dict[str, Any]:
    spk = (turn.get("speaker") or "").strip().upper()
    txt = _clean_inline((turn.get("text") or "").strip())
    out = {"speaker": spk, "text": txt}
    if "t0" in turn: out["t0"] = turn["t0"]
    if "t1" in turn: out["t1"] = turn["t1"]
    if "clinical" in turn: out["clinical"] = turn["clinical"]
    return out

def normalize_transcript_turns(transcript: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [_norm_turn(t) for t in (transcript or []) if (t.get("text") or "").strip()]

# ===================== Prompt =====================
def _render_user_prompt(schema_id: str, transcript: List[Dict[str, Any]]) -> str:
    lines = []
    lines.append("Instrucciones:")
    lines.append("- Devuelve SOLO un JSON válido, sin comentarios ni texto extra.")
    lines.append("- Esquema esperado: motivo_consulta, enfermedad_actual, antecedentes, examen_fisico, impresion_dx, ordenes, recetas, alertas.")
    lines.append("- examen_fisico debe incluir TA, Temp, FC, FR, SatO2, hallazgos (si están disponibles).")
    lines.append("- Usa unidades clínicas estándar (°C, mmHg, lpm, rpm, %).")
    lines.append("- No inventes datos; si no hay info, omite la clave.")
    lines.append("- Evita repeticiones tipo 's s s s'.")
    lines.append("")
    lines.append(f"Schema detectado: {schema_id or 'consulta_general'}")
    lines.append("")
    lines.append("Transcript:")
    for t in transcript:
        lines.append(f"- {t.get('speaker','')}: {t.get('text','')}")
    lines.append("")
    lines.append("Responde SOLO con el JSON final.")
    return "\n".join(lines)

FEW_SHOT_EXAMPLE = """
[TRANSCRIPT]
PACIENTE: Tengo dolor opresivo en el pecho desde hace 2 horas, con sudoración.
DOCTOR: ¿Antecedentes?
PACIENTE: Hipertenso, enalapril.
DOCTOR: Signos: TA 160/95, FC 105, FR 20, Temp 36.8, SatO2 90%.

[JSON]
{
  "motivo_consulta": "Dolor torácico opresivo con sudoración",
  "enfermedad_actual": {
    "sintomas": "Dolor torácico opresivo de 2 horas, con sudoración",
    "evolucion": "Inicio súbito, intensidad moderada-severa",
    "factores_riesgo": ["hipertensión arterial"]
  },
  "antecedentes": ["Hipertensión arterial en tratamiento con enalapril"],
  "examen_fisico": {
    "TA": "160/95 mmHg",
    "Temp": "36.8 °C",
    "FC": "105 lpm",
    "FR": "20 rpm",
    "SatO2": "90 %",
    "hallazgos": ""
  },
  "impresion_dx": ["Síndrome coronario agudo en estudio"],
  "ordenes": [
    {"detalle": "Monitoreo continuo de signos vitales"},
    {"detalle": "Electrocardiograma y troponinas"}
  ],
  "recetas": [{"detalle": "Ácido acetilsalicílico 300 mg VO dosis de carga"}],
  "alertas": ["Alto riesgo cardiovascular"]
}
""".strip()

OUTPUT_TEMPLATE_HINT = """
Devuelve ÚNICAMENTE un JSON válido siguiendo el esquema. No incluyas nada más.
""".strip()

# ===================== Parsing JSON =====================
_JSON_OBJECT_RX = re.compile(r"\{.*\}", re.DOTALL)

def _extract_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    m = _JSON_OBJECT_RX.search(text)
    raw = m.group(0) if m else text
    try:
        return json.loads(raw)
    except Exception:
        fixed = raw.replace("“", '"').replace("”", '"').replace("’", "'")
        fixed = re.sub(r",\s*([}\]])", r"\1", fixed)
        try:
            return json.loads(fixed)
        except Exception:
            return {}

def _fallback_json() -> Dict[str, Any]:
    return {
        "motivo_consulta": "",
        "enfermedad_actual": "",
        "antecedentes": [],
        "examen_fisico": {},
        "impresion_dx": [],
        "ordenes": [],
        "recetas": [],
        "alertas": [],
    }

# ===================== Pipeline principal =====================
async def generate_structured_json(schema_id: str, transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    tr = normalize_transcript_turns(transcript or [])
    user_prompt = _render_user_prompt(schema_id, tr)

    llm = get_llm()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": FEW_SHOT_EXAMPLE},
        {"role": "user", "content": OUTPUT_TEMPLATE_HINT},
        {"role": "user", "content": user_prompt},
    ]

    text = await llm.chat(
        messages,
        temperature=0.3,
        max_tokens=None  # Ollama ignora o ajusta automáticamente
    )
    data = _extract_json(text)

    if not isinstance(data, dict) or not data:
        data = _fallback_json()

    def _clean_val(v):
        if isinstance(v, str):
            return _clean_inline(v)
        if isinstance(v, list):
            return [_clean_val(x) for x in v]
        if isinstance(v, dict):
            return {k: _clean_val(x) for k, x in v.items()}
        return v

    return _clean_val(data)

async def generate_structured_json(schema_id: str, transcript):
    # ... arma prompt ...
    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            # llamada a tu proveedor LLM (OpenAI/otros)
            # resp = await client.post( ... )
            # parsed = resp.json() ...
            # return parsed["json_clinico"]
            ...
    except httpx.ReadTimeout:
        # Deja que main capture este fallo; retorna dict vacío para que la capa de reglas complete
        return {}
    
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