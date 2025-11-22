# -*- coding: utf-8 -*-
import re
from typing import Any, Dict, List

def dedupe_letters(s: str) -> str:
    # “s s s s s” → “s”
    return re.sub(r'(\b\w)\s+(?:\1\s+){2,}', r'\1 ', s or "")

def _join_text(turns: List[Dict[str, Any]]) -> str:
    return " . ".join([(t.get("text") or "").strip() for t in (turns or []) if (t.get("text") or "").strip()]).lower()

def extract_from_transcript(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    T = _join_text(transcript)

    def has(*words) -> bool:
        return any(w in T for w in words)

    antecedentes: Dict[str, Any] = {}
    # Farmacológicos
    meds = []
    if "losart" in T: meds.append("Losartán (en curso)")
    if "furosemida" in T: meds.append("Furosemida (en curso)")
    if "ibuprofeno" in T: meds.append("Ibuprofeno (reciente)")
    if meds: antecedentes["farmacologicos"] = meds

    # Personales / patológicos
    pers = []
    if "hipertens" in T: pers.append("Hipertensión arterial")
    if "cardiopat" in T: pers.append("Cardiopatía conocida")
    if pers: antecedentes["personales"] = pers

    if has("sin alerg", "no alerg"): antecedentes["alergias"] = ["Sin alergias conocidas"]

    # Revisión por sistemas
    ros: Dict[str, Any] = {}
    resp = []
    if has("tos seca", "tos"): resp.append("Tos")
    if has("disnea", "falta de aire", "ahog", "dificultad para respirar"): resp.append("Disnea de esfuerzo")
    if "crepitantes" in T: resp.append("Ruidos crepitantes")
    if resp: ros["respiratorio"] = resp

    cardio = []
    if has("palpitaciones", "corazón muy rápido", "taquicardia"): cardio.append("Palpitaciones")
    if has("edema", "hinchazón", "tobillos"): cardio.append("Edema maleolar")
    if cardio: ros["cardiovascular"] = cardio

    gen = []
    if has("fiebre"): gen.append("Fiebre (niega en esta consulta)")
    if gen: ros["general"] = gen

    gu = []
    if has("orino menos", "orino poco", "diuresis"): gu.append("Diuresis disminuida")
    if gu: ros["genitourinario"] = gu

    if "neurologico" not in ros: ros["neurologico"] = "Sin cefalea intensa ni déficit"
    if "dermatologico" not in ros: ros["dermatologico"] = "Sin exantemas"

    # Signos vitales / hallazgos
    ef: Dict[str, Any] = {}
    m = re.search(r"ta\s*(\d{2,3}\s*\/\s*\d{2,3})", T, re.I)
    if m: ef["TA"] = m.group(1).replace(" ", "")
    m = re.search(r"fc\s*(\d{2,3})", T, re.I)
    if m: ef["FC"] = m.group(1)
    m = re.search(r"fr\s*(\d{2,3})", T, re.I)
    if m: ef["FR"] = m.group(1)
    m = re.search(r"(\b3[5-9](?:[.,]\d+)?)\s*°?c", T, re.I)
    if m: ef["Temp"] = m.group(1).replace(",", ".")
    m = re.search(r"sato2\s*(\d{2,3})", T, re.I)
    if m: ef["SatO2"] = m.group(1)

    if "crepitantes" in T:
        ef["hallazgos"] = (ef.get("hallazgos","") + " Crepitantes bibasales.").strip()

    # Alertas de seguridad básicas
    alertas: List[str] = []
    if has("labios morados", "cianosis"): alertas.append("Cianosis")
    if has("síncope", "sincope", "confusión", "confusion"): alertas.append("Síncope/Confusión")
    if re.search(r"sato2\s*(\d{2})", T) and int(re.search(r"sato2\s*(\d{2})", T).group(1)) < 90:
        alertas.append("SatO2 < 90%")

    return {
        "antecedentes": antecedentes,
        "revision_sistemas": ros,
        "examen_fisico": ef,
        "alertas": alertas
    }