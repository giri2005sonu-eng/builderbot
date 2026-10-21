from fastapi import APIRouter, Cookie, HTTPException
from typing import Optional

from core import pipeline
from core.recommendation_catalog import PROJECT_CATALOG
from server.schemas import IdeaMatchRequest
from server.state import store

router = APIRouter(prefix="/api/idea", tags=["idea"])


@router.post("/match")
def match_idea(req: IdeaMatchRequest, forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Idea text cannot be empty")

    res = pipeline.map_idea(text)
    session.idea = res
    project_key = res.get("project")
    label = PROJECT_CATALOG[project_key]["label"] if project_key and project_key in PROJECT_CATALOG else None

    return {
        "project": project_key,
        "label": label,
        "reason": res.get("reason", ""),
        "supported": bool(project_key),
    }
