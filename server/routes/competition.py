from fastapi import APIRouter, Cookie, Query
from typing import List, Optional

from core.recommendation_catalog import (
    COMPETITION_EVENT_COUNTS,
    COMPETITION_EVENTS,
    PROJECT_CATALOG,
    PROJECT_FACTOR_CATALOG,
    competition_projects_for_event,
)
from server.state import store

router = APIRouter(prefix="/api/competition", tags=["competition"])


@router.get("/events")
def list_events():
    return [
        {"name": ev, "mentions": COMPETITION_EVENT_COUNTS.get(ev, 0)}
        for ev in COMPETITION_EVENTS
    ]


@router.get("/projects")
def list_event_projects(event: str = Query(...), forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    keys = competition_projects_for_event(event)
    previous_selected = session.competition_selected_by_event.get(event, [])

    projects = []
    for k in keys:
        proj = PROJECT_CATALOG.get(k, {})
        meta = PROJECT_FACTOR_CATALOG.get(k, {})
        projects.append({
            "key": k,
            "label": proj.get("label", k),
            "desc": proj.get("desc", ""),
            "domain": meta.get("domain", ""),
            "build_hours": meta.get("build_hours", 0),
            "cost_inr": meta.get("cost_inr", 0),
            "parts_availability_india": meta.get("parts_availability_india", 3),
            "constraints": meta.get("constraints", ""),
            "required_skills": sorted(meta.get("required_skills", [])),
            "safety": sorted(meta.get("safety", [])) if meta.get("safety") else [],
            "selected": k in previous_selected,
        })

    return {
        "event": event,
        "projects": projects,
        "selected_keys": previous_selected,
    }
