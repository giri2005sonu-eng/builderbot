from fastapi import APIRouter, Query

from core.recommendation_catalog import PROJECT_CATALOG, PROJECT_FACTOR_CATALOG

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("/search")
def search_projects(q: str = Query(default="", max_length=120)):
    query = q.casefold().strip()
    results = []
    for key, project in PROJECT_CATALOG.items():
        label = project["label"]
        if query and query not in key.casefold() and query not in label.casefold():
            continue
        results.append({
            "key": key,
            "label": label,
            "domain": PROJECT_FACTOR_CATALOG.get(key, {}).get("domain", ""),
            "is_star": project.get("is_star", False),
        })
    results.sort(key=lambda project: (project["label"].casefold(), project["key"]))
    return {"projects": results[:20]}
