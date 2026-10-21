import os
from fastapi import APIRouter, Cookie, HTTPException
from typing import Optional

from core import browser_cart, custom_bom, part_specs, research, tf
from server.schemas import CartCheckRequest, GuidesResearchRequest, SpecsCompareRequest
from server.state import store

router = APIRouter(prefix="/api/research", tags=["research"])


@router.post("/guides")
def research_guides(req: GuidesResearchRequest, forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    label = req.project_label or session.get_build_label()
    tinyfish_enabled = bool(os.getenv("TINYFISH_API_KEY"))
    gemini_enabled = bool(os.getenv("GEMINI_API_KEY"))

    if not (tinyfish_enabled and gemini_enabled):
        raise HTTPException(status_code=400, detail="Both TINYFISH_API_KEY and GEMINI_API_KEY are required")

    log_entries = []
    res = research.research(label, log=log_entries.append)
    session.research[label] = res
    return {"result": res, "log": log_entries}


@router.get("/specs")
def get_specs_for_build(forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    parts = session.get_active_parts()
    for p in parts.values():
        if not p.get("specs") and not p.get("none"):
            sp = part_specs.find_specs_in_dataset(p.get("name"))
            if sp:
                p["specs"] = sp

    spec_parts = {p["name"]: p["specs"] for p in parts.values() if not p.get("none") and p.get("specs")}
    without = [p["name"] for p in parts.values() if not p.get("none") and not p.get("specs")]
    return {"spec_parts": spec_parts, "without_specs": without}


@router.post("/specs/compare")
def compare_specs(req: SpecsCompareRequest, forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    parts = session.get_active_parts()
    part = next((p for p in parts.values() if p.get("name") == req.part_name), None)
    if not part or not part.get("specs"):
        raise HTTPException(status_code=404, detail=f"No typed specs found for '{req.part_name}'")

    items = [(req.part_name, part["specs"])]
    if req.compare_with:
        pool = part_specs.alternatives(part["role"], part["specs"], exclude_name=req.part_name, limit=60)
        names = {name: key for key, name, _ in pool}
        for n in req.compare_with:
            if n in names:
                items.append((n, part_specs.specs_for(names[n])))

    table = part_specs.compare(items)
    html = part_specs.compare_html(table)
    return {"table": table, "html": html}


@router.post("/specs/fetch-missing")
def fetch_missing_specs(forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    gemini_enabled = bool(os.getenv("GEMINI_API_KEY"))
    if not gemini_enabled:
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY required")

    parts = session.get_active_parts()
    missing = [p for p in parts.values() if not p.get("none") and not p.get("specs")]
    if not missing:
        return {"status": "ok", "message": "No parts missing specs"}

    custom_bom.fetch_and_apply_missing_specs(missing)
    return {"status": "ok", "fetched_count": len(missing)}


@router.post("/cart-check")
def run_cart_check(req: CartCheckRequest, forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    tinyfish_enabled = bool(os.getenv("TINYFISH_API_KEY"))
    if not tinyfish_enabled:
        raise HTTPException(status_code=400, detail="TINYFISH_API_KEY required for cart check")

    def run_agent(u):
        return tf.agent(u, max_steps=12)

    try:
        res = browser_cart.check(req.url, agent=run_agent)
        session.agent[req.url] = res
        return res
    except Exception as e:
        err = {"status": "ERROR", "error": str(e)[:200]}
        session.agent[req.url] = err
        return err
