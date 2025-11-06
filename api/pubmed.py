# -*- coding: utf-8 -*-
from __future__ import annotations
import os, json
from typing import List, Dict, Any, Optional, Tuple
import httpx

from api.config import KNOWLEDGE_DIR

NCBI_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# ---------- Búsqueda remota ----------
async def pubmed_search(q: str, retmax: int = 5, retstart: int = 0) -> Dict[str, Any]:
    url = f"{NCBI_EUTILS}/esearch.fcgi"
    params = {
        "db": "pubmed", "term": q, "retmode": "json",
        "retmax": str(retmax), "retstart": str(retstart)
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
    ids = data.get("esearchresult", {}).get("idlist", []) or []
    count = int(data.get("esearchresult", {}).get("count", 0))
    return {"ids": ids, "count": count, "q": q, "retstart": retstart, "retmax": retmax}

# ---------- Índice local JSONL ----------
_LOCAL_PATH = os.path.join(KNOWLEDGE_DIR, "pubmed", "pubmed.jsonl")
_LOCAL_IDX: Optional[Dict[str, Dict[str, Any]]] = None  # pmid -> registro

def _normalize_row(raw: Dict[str, Any]) -> Dict[str, Any]:
    pmid = str(raw.get("pmid") or raw.get("PMID") or "").strip()
    title = raw.get("title") or raw.get("TI") or raw.get("article_title") or ""
    abstract = raw.get("abstract") or raw.get("AB") or raw.get("abstract_text") or ""
    year = raw.get("year") or raw.get("DP") or raw.get("pub_year") or ""
    y = None
    if isinstance(year, int):
        y = year
    elif isinstance(year, str) and year[:4].isdigit():
        y = int(year[:4])
    url = raw.get("url") or (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None)
    return {"pmid": pmid, "title": str(title).strip(), "abstract": str(abstract).strip(), "year": y, "url": url}

def _ensure_local_index() -> None:
    global _LOCAL_IDX
    if _LOCAL_IDX is not None:
        return
    _LOCAL_IDX = {}
    try:
        with open(_LOCAL_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    row = _normalize_row(obj)
                    if row["pmid"]:
                        _LOCAL_IDX[row["pmid"]] = row
                except Exception:
                    continue
    except FileNotFoundError:
        _LOCAL_IDX = {}

def local_has_db() -> bool:
    _ensure_local_index()
    return bool(_LOCAL_IDX)

def local_lookup_pmids(pmids: List[str]) -> List[Dict[str, Any]]:
    _ensure_local_index()
    out: List[Dict[str, Any]] = []
    for p in pmids:
        r = _LOCAL_IDX.get(str(p), {})
        if r:
            out.append({"pmid": r["pmid"], "title": r["title"], "year": r["year"], "url": r["url"]})
    return out

def local_search_terms(q: str, limit: int = 5) -> List[Dict[str, Any]]:
    _ensure_local_index()
    if not _LOCAL_IDX:
        return []
    qs = str(q or "").casefold()
    hits: List[Tuple[int, Dict[str, Any]]] = []
    for r in _LOCAL_IDX.values():
        hay = (r["title"] or "").casefold() + " " + (r["abstract"] or "").casefold()
        score = hay.count(qs)
        if score > 0:
            hits.append((score, r))
    hits.sort(key=lambda x: x[0], reverse=True)
    out = []
    for _, r in hits[:limit]:
        out.append({"pmid": r["pmid"], "title": r["title"], "year": r["year"], "url": r["url"]})
    return out

# ---------- Bootstrap (compatibilidad) ----------
async def pubmed_ingest_to_files(q: str, total: int, out_dir: str) -> Dict[str, Any]:
    os.makedirs(out_dir, exist_ok=True)
    count = 0
    try:
        with open(os.path.join(out_dir, "pubmed.jsonl"), "r", encoding="utf-8") as f:
            for _ in f:
                count += 1
    except FileNotFoundError:
        pass
    return {
        "query": q, "count": count, "requested": total, "fetched": min(total, count),
        "file": os.path.join(out_dir, "pubmed.jsonl")
    }