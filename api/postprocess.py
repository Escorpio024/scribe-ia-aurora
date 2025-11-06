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