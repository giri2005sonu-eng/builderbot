from fastapi import APIRouter

from core.recommendation_catalog import STAR_PROJECTS
from core import project_store

router = APIRouter(prefix="/api/stars", tags=["star projects"])


@router.get("")
def list_star_projects():
    projects = [
        {
            **project,
            "bom_supported": project_store.key_for_id(project["key"]) is not None,
        }
        for project in STAR_PROJECTS
    ]
    return {"projects": projects, "count": len(projects)}
