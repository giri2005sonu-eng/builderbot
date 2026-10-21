from fastapi import APIRouter, Cookie, HTTPException
from typing import Optional

from core import component_catalog as cat, optimizer as opt
from core.data import PROJECTS
from server.schemas import OptimizerSwapRequest
from server.state import store

router = APIRouter(prefix="/api/optimizer", tags=["optimizer"])


def _active_parts(session):
    parts = session.get_active_parts()
    if not parts:
        raise HTTPException(status_code=400, detail="Generate a BOM before using the Project Optimizer")
    return parts


def _candidates(parts, role):
    current = parts.get(role)
    if not isinstance(current, dict) or current.get("none"):
        raise HTTPException(status_code=404, detail=f"Component role '{role}' not found in the active BOM")
    sensor_kind = current.get("kind") if current.get("role") == "sensor" else None
    return opt.candidates(parts, current.get("role", role), sensor_kind)


def _find_candidate(parts, role, part_id):
    candidate = next((part for part in _candidates(parts, role) if part["id"] == part_id), None)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"Part '{part_id}' is not a valid replacement for '{role}'")
    return candidate


def _evaluate(session, parts, role, part_id):
    candidate = _find_candidate(parts, role, part_id)
    proposed = opt.replace(parts, role, candidate)
    evaluation = opt.compare_builds(
        original=parts,
        proposed=proposed,
        changed={role},
        records=cat.load(),
        live=session.live,
        needs_bt=session.bluetooth or PROJECTS.get(session.project, {}).get("bt", False),
    )
    return candidate, evaluation


@router.get("/candidates")
def get_swap_candidates(role: str, forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    parts = _active_parts(session)
    candidates = _candidates(parts, role)
    return [{"id": c["id"], "name": c["name"], "price": c.get("seed_price")} for c in candidates]


@router.post("/evaluate")
def evaluate_swap(req: OptimizerSwapRequest, forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    parts = _active_parts(session)
    _, eval_res = _evaluate(session, parts, req.role, req.swap_part_id)
    summary = eval_res["summary_proposed"]
    return {"evaluation": eval_res, "summary": summary}


@router.post("/apply")
def apply_swap(req: OptimizerSwapRequest, forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    parts = _active_parts(session)
    candidate, evaluation = _evaluate(session, parts, req.role, req.swap_part_id)
    summary = evaluation["summary_proposed"]
    if not summary["ready"]:
        raise HTTPException(status_code=409, detail="Replacement fails compatibility checks and cannot be applied")
    session.opt_swaps[req.role] = candidate
    return {"status": "ok", "swaps": {role: part.get("id") for role, part in session.opt_swaps.items()}}


@router.post("/reset")
def reset_swaps(forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    session.opt_swaps.clear()
    return {"status": "ok"}
