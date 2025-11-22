# api/augment.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import os, json, re, math, unicodedata
from typing import List, Dict, Any, Iterable, Tuple, Optional, Set

from api.config import KNOWLEDGE_DIR

PUBMED_DIR   = os.path.join(KNOWLEDGE_DIR, "pubmed")
PUBMED_JSONL = os.path.join(PUBMED_DIR, "pubmed.jsonl")

# ------------------ utilidades de texto ------------------
_SPLIT = re.compile(r"[^\wáéíóúñü]+", re.IGNORECASE)

def _strip_accents(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    # mapear ñ -> n explícito para búsquedas robustas
    s = s.replace("ñ", "n").replace("Ñ", "N")
    return s

def _norm(s: str) -> str:
    return _strip_accents((s or "").lower()).strip()

def _toks(s: str, stop: Set[str]) -> List[str]:
    return [t for t in _SPLIT.split(_norm(s)) if t and t not in stop]

def _contains_any(text: str, kws: List[str]) -> bool:
    t = _norm(text)
    return any(kw in t for kw in kws)

# ------------------ stopwords ------------------
STOP = {
    # ES/EN comunes
    "de","la","el","y","o","en","para","con","sin","por","del","al","los","las","un","una","que","como","es","son",
    "the","of","and","or","in","to","for","by","on","from","at","an","a","is","are","was","were","be","being",
    # clínicas genéricas
    "patient","patients","study","trial","randomized","review","case","report","series","cohort","clinic","hospital",
    "adult","adults","child","children","pediatric","male","female","year","years","aged","data","analysis",
}

# dominios que suelen ser ruido si el caso es respiratorio
NEGATIVE_DOMAINS = {
    "dementia","alzheimer","bariatric","dermatology","psoriasis","atopic","ophthalmology","glaucoma",
    "orthopedic","arthro","urology","prostate","erectile","psychiatry","obsessive","trichotillomania",
    "toxic oil","toxic-oil","gastrojejunostomy","bypass","biliary","colorectal","breast cancer","prostate cancer",
}

# ------------------ diales/constantes ------------------
DEFAULT_MIN_SCORE = 0.30          # umbral global de evidencia (puedes subirlo si quieres más precisión)
STRICT_INFLUENZA_FACTOR = 0.75     # influenza solo si >= 75% del mejor score o si se menciona en texto

# semillas/required por plantilla (ordenadas para favorecer CAP)
SCHEMA_SEEDS = {
    "respiratoria_aguda": [
        # Favorece CAP / neumonía y respiratorio general
        "community acquired pneumonia", "pneumonia", "cap",
        "respiratory infection", "bronchitis", "bronchi", "tos", "disnea",
        "saturacion", "hipoxemia", "pulmon", "respiratoria", "crepitantes", "rales",
        "auscultacion", "o2",
        # Etiologías virales al final (menor prioridad)
        "covid", "influenza", "rsv",
    ],
    "dolor_toracico": ["chest pain","dolor toracico","infarto","acs","troponina","ecg","timi","heart score"],
    "consulta_general": ["fiebre","dolor","cefalea","gastroenteritis","vomito","diarrea","resfriado"],
}

REQUIRED_BY_SCHEMA = {
    # al menos una de estas raíces debe aparecer en título/abstract/mesh cuando respiratoria
    "respiratoria_aguda": ["neumon", "bronqui", "respir", "tos", "disnea", "cap", "pulmon", "o2", "satur"],
}

# ------------------ lectura corpus ------------------
def _iter_pubmed() -> Iterable[Dict[str, Any]]:
    if not os.path.exists(PUBMED_JSONL):
        return []
    with open(PUBMED_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue

def _rec_text(rec: Dict[str, Any]) -> str:
    return " ".join([
        str(rec.get("title") or ""),
        str(rec.get("abstract") or ""),
        " ".join(rec.get("mesh", []) or []),
        " ".join(rec.get("keywords", []) or []),
    ])

# ------------------ BM25-lite ------------------
def _idf(N: int, df: int) -> float:
    return math.log(1 + (N - df + 0.5) / (df + 0.5))

def _bm25(q: List[str], d: List[str], df_map: Dict[str, int], N: int, k1=1.2, b=0.75) -> float:
    if not q or not d:
        return 0.0
    dl = len(d)
    avgdl = 200.0
    tf: Dict[str, int] = {}
    for t in d:
        tf[t] = tf.get(t, 0) + 1
    score = 0.0
    for t in set(q):
        f = tf.get(t, 0)
        if f == 0:
            continue
        idf = _idf(N, df_map.get(t, 1))
        score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
    return score

# ------------------ query builder ------------------
def build_query_from_json(j: Dict[str, Any], schema_used: Optional[str] = None) -> str:
    j = j or {}
    motivo = str(j.get("motivo_consulta") or "")
    ea = j.get("enfermedad_actual")
    ea_text = " ".join(v for v in ea.values()) if isinstance(ea, dict) else str(ea or "")
    imp = " ".join([str(d) for d in (j.get("impresion_dx") or [])])
    ef = j.get("examen_fisico") or {}
    vitals = " ".join(str(ef.get(k) or "") for k in ("TA","Temp","FC","FR","SatO2"))
    rx = " ".join((o.get("detalle") or "") for o in (j.get("ordenes") or []))
    base = " ".join([motivo, ea_text, imp, vitals, rx]).strip()

    seeds = SCHEMA_SEEDS.get(schema_used or "", [])
    return (base + " " + " ".join(seeds)).strip()

# ------------------ retrieval con filtros duros ------------------
def retrieve_similar_cases(j: Dict[str, Any], schema_used: Optional[str] = None, k: int = 10) -> List[Dict[str, Any]]:
    query = build_query_from_json(j, schema_used=schema_used)
    qtoks = _toks(query, STOP)
    if not qtoks:
        return []

    req_roots = REQUIRED_BY_SCHEMA.get(schema_used or "", [])
    req_rx = re.compile("|".join(re.escape(r) for r in req_roots), re.IGNORECASE) if req_roots else None

    pmid_seen: Set[str] = set()
    docs: List[Tuple[List[str], Dict[str, Any], int]] = []  # (tokens, rec, respir_hits)
    df: Dict[str, int] = {}
    N = 0

    for rec in _iter_pubmed():
        pmid = str(rec.get("pmid") or rec.get("id") or "")
        if not pmid or pmid in pmid_seen:
            continue
        pmid_seen.add(pmid)

        raw = _rec_text(rec)
        raw_norm = _norm(raw)

        edad = j.get("edad") or j.get("age")
        is_adult = isinstance(edad, (int, float)) and edad >= 18
        is_child = isinstance(edad, (int, float)) and edad < 18
        title_norm = (rec.get("title") or "").lower()

        if is_adult and ("pediatric" in title_norm or "child" in title_norm or "children" in title_norm):
            continue  # descartar artículos pediátricos en pacientes adultos
        if is_child and ("adult" in title_norm or "elderly" in title_norm):
            continue

        # filtro duro por dominio respiratorio cuando aplica
        respir_hits = 0
        if req_rx:
            respir_hits = len(req_rx.findall(raw_norm))
            if respir_hits == 0:
                # fuera de foco, saltar
                continue

        # penalizar dominios negativos (si aparecen y NO están en query)
        neg_hit = any(nd in raw_norm for nd in (n.lower() for n in NEGATIVE_DOMAINS))
        query_norm = _norm(query)
        neg_in_query = any(nd in query_norm for nd in (n.lower() for n in NEGATIVE_DOMAINS))
        if neg_hit and not neg_in_query:
            # si el artículo pertenece a dominios ajenos, lo descartamos aquí mismo
            continue

        dtoks = _toks(raw_norm, STOP)
        if not dtoks:
            continue

        N += 1
        docs.append((dtoks, rec, respir_hits))
        for t in set(dtoks):
            df[t] = df.get(t, 0) + 1

    if not docs:
        return []

    # scoring
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for dtoks, rec, respir_hits in docs:
        s = _bm25(qtoks, dtoks, df, N)

        # boost por matches respiratorios
        if respir_hits:
            s *= (1.0 + min(0.5, 0.15 * respir_hits))  # máximo +50%

        if s > 0.05:
            scored.append((s, rec))

    scored.sort(key=lambda x: x[0], reverse=True)

    # umbral más alto si schema es respiratorio para asegurar relevancia
    MIN_SCORE = 0.33 if (schema_used or "").startswith("respiratoria") else 0.2

    out = []
    for sc, rec in scored:
        if sc < MIN_SCORE:
            continue
        pmid = str(rec.get("pmid") or rec.get("id") or "")
        out.append({
            "pmid": pmid,
            "title": rec.get("title") or "",
            "year": rec.get("year"),
            "abstract": rec.get("abstract") or "",
            "score": round(sc, 3),
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None
        })
        if len(out) >= k:
            break
    return out

# ------------------ helpers de bias/evidencia ------------------
def _age_filter_provenance(prov: List[Dict[str, Any]], edad: Any) -> List[Dict[str, Any]]:
    if not prov:
        return []
    try:
        e = float(edad)
    except Exception:
        return prov
    is_adult = e >= 16
    out = []
    for p in prov:
        title = _norm(p.get("title") or "")
        if is_adult and _contains_any(title, ["pediatric","children","child","infant","adolescent","paediatric"]):
            continue
        if not is_adult and _contains_any(title, ["adult","elderly","geriatric"]):
            continue
        out.append(p)
    return out

def _apply_min_score_filter(provenance: List[Dict[str, Any]], min_score: float | None) -> List[Dict[str, Any]]:
    if not provenance or min_score is None:
        return provenance or []
    try:
        ms = float(min_score)
    except Exception:
        ms = DEFAULT_MIN_SCORE
    return [p for p in (provenance or []) if float(p.get("score") or 0.0) >= ms]

def _allow_influenza_bias(json_clinico: Dict[str, Any], provenance: List[Dict[str, Any]]) -> bool:
    """
    Regla conservadora: sólo permitir 'influenza' si:
      - El texto clínico menciona influenza/gripe, o
      - La evidencia top la sugiere fuertemente (título con 'influenza' y score cercano al top).
    """
    texto = _norm(
        " ".join([
            str(json_clinico.get("motivo_consulta") or ""),
            str(json_clinico.get("enfermedad_actual") or ""),
            " ".join([str(x) for x in (json_clinico.get("impresion_dx") or [])]),
        ])
    )
    if _contains_any(texto, ["influenza", "gripe"]):
        return True

    if not provenance:
        return False

    best = max((p.get("score") or 0.0) for p in provenance) or 0.0
    threshold = best * STRICT_INFLUENZA_FACTOR

    for p in provenance[:5]:  # mira top-5
        title = _norm(p.get("title") or "")
        score = float(p.get("score") or 0.0)
        if "influenza" in title and score >= threshold:
            return True

    return False

def _postprocess_bias_cap_only(
    sugerencias: Dict[str, Any],
    provenance: List[Dict[str, Any]],
    json_clinico: Dict[str, Any],
    cap_only: bool
) -> Dict[str, Any]:
    """
    Si cap_only=True, elimina 'influenza' de impresion_dx salvo que _allow_influenza_bias(...) lo permita.
    """
    if not cap_only:
        return sugerencias or {}

    out = dict(sugerencias or {})
    dx = out.get("impresion_dx") or []
    if not dx:
        return out

    if not _allow_influenza_bias(json_clinico, provenance):
        dx = [d for d in dx if _norm(d) != "influenza"]
        out["impresion_dx"] = dx

    return out

# ------------------ proponer autocompletado ------------------
def _first_sentence(txt: str) -> str:
    txt = (txt or "").strip()
    if not txt:
        return ""
    m = re.split(r"(?<=[\.\!\?])\s+", txt)
    return (m[0] if m else txt)[:300]

def propose_fills(json_clinico: Dict[str, Any], cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    j = (json_clinico or {}).copy()
    suggests: Dict[str, Any] = {}

    # Mantener solo casos "fuertes"
    strong = [c for c in cases if c.get("score", 0) >= 0.33][:5]

    # 1) Enfermedad actual
    if not j.get("enfermedad_actual") and strong:
        s = _first_sentence(strong[0].get("abstract") or "") or _first_sentence(strong[0].get("title") or "")
        if len(s) > 24:
            suggests["enfermedad_actual"] = s + " (sugerido por casos respiratorios similares)"

    # 2) Impresión diagnóstica
    if not j.get("impresion_dx"):
        titles = " ".join(c.get("title") or "" for c in strong).lower()
        dx = []
        for kw in ["neumonia","asma","epoc","infeccion respiratoria","bronquitis","covid-19","influenza"]:
            if kw in _norm(titles):
                dx.append(kw)
        if dx:
            # normaliza y limita
            suggests["impresion_dx"] = list(dict.fromkeys(dx))[:3]

    # 3) Órdenes
    if not j.get("ordenes"):
        for c in strong:
            t = (c.get("title") or "").lower()
            if any(x in t for x in ["guideline","consensus","recommendation","randomized","trial"]):
                suggests["ordenes"] = [{"detalle": "Seguir recomendaciones de guía (ver evidencia vinculada)."}]
                break

    # 4) Alertas
    if not j.get("alertas"):
        suggests["alertas"] = ["Revisar signos de alarma y reevaluar si empeora. (sugerido)"]

    provenance = [
        {"pmid": c["pmid"], "title": c["title"], "score": c["score"], "url": c["url"]}
        for c in cases[:10]
    ]

    return {
        "sugerencias_autocompletado": suggests,
        "provenance": provenance,
    }

# ------------------ API principal ------------------
def augment_with_pubmed(
    json_clinico: Dict[str, Any],
    schema_used: Optional[str] = None,
    top_k: int = 12,
    augment_bias: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Genera autocompletados basados en PubMed JSONL.
    Diales en augment_bias:
      - cap_only: bool (default True) -> prioriza CAP (neumonía) y solo sugiere 'influenza' si hay evidencia fuerte o se menciona.
      - min_score: float (default DEFAULT_MIN_SCORE) -> filtra evidencia (provenance) por score mínimo.
    """
    cases = retrieve_similar_cases(json_clinico, schema_used=schema_used, k=top_k)
    out = propose_fills(json_clinico, cases)

    # Lee bias
    bias = augment_bias or {}
    cap_only = bool(bias.get("cap_only", True))
    min_score = bias.get("min_score", DEFAULT_MIN_SCORE)

    # Filtros a la evidencia
    prov = out.get("provenance") or []
    prov = _age_filter_provenance(prov, json_clinico.get("edad") or json_clinico.get("age"))
    prov = _apply_min_score_filter(prov, min_score)

    # Aplica sesgo a CAP sobre las sugerencias
    sugs = out.get("sugerencias_autocompletado") or {}
    sugs = _postprocess_bias_cap_only(sugs, prov, json_clinico, cap_only)

    return {
        "sugerencias_autocompletado": sugs,
        "provenance": prov,
    }

def clean_transcript_text(text: str) -> str:
    if not text:
        return ""
    # Quita repeticiones como "s s s s"
    text = re.sub(r'\b(?:s\s+){2,}', '', text, flags=re.IGNORECASE)
    # Quita cadenas de "sss..."
    text = re.sub(r'\bs+\b', '', text, flags=re.IGNORECASE)
    return text.strip()