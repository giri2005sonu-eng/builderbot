import os
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Cookie, HTTPException, Response
from typing import Optional

from core import picker, pipeline
from core.recommendation_catalog import (
    PROJECT_CATALOG,
    PROJECT_FACTOR_CATALOG,
    RECOMMENDATION_PROJECT_KEYS,
    STAR_PROJECTS,
)
from core.recommender_config import RECOMMENDER_VERSION
from server.schemas import (
    CareerResearchRequest,
    SurveyAnswerRequest,
    SurveyFeedbackRequest,
    SurveyRankRequest,
)
from server.state import store

router = APIRouter(prefix="/api/survey", tags=["survey"])
FEEDBACK_PATH = Path(__file__).resolve().parents[2] / "core" / "project_data" / "recommender_feedback.jsonl"
FEEDBACK_LOCK = threading.Lock()


def _factor_chart_payload(project_key, profile, overall):
    meta = PROJECT_FACTOR_CATALOG[project_key]
    fit = picker.factor_breakdown(project_key, profile)
    chart_svg = picker.chart_html(
        fit,
        overall=round(overall * 100) if overall <= 1 else overall,
        title="12-FACTOR FIT PROFILE",
        axes=picker.RADAR_AXES,
    )
    themed_svg = (
        chart_svg
        .replace("#06B6D4", "#FF7A1A")
        .replace("#67E8F9", "#FFB347")
        .replace("#4C1D95", "#832407")
        .replace("#0A0F1E", "#0B0D14")
        .replace("#1E2A4A", "rgba(255,255,255,0.12)")
        .replace("#111A30", "#161922")
    )
    rated_keys = {key for _, key in picker.AXES}
    fit_breakdown = [
        {
            "factor": label,
            "rating": f"{meta.get(key, 3)}/5" if key in rated_keys else "—",
            "fit": f"{fit[key]}%",
            "fit_score": fit[key],
        }
        for label, key in picker.RADAR_AXES
    ]
    return {"fit_breakdown": fit_breakdown, "chart_svg": themed_svg}


def _serialize_star_goal(goal):
    if not goal:
        return None
    project = PROJECT_CATALOG[goal["key"]]
    star = next((item for item in STAR_PROJECTS if item["key"] == goal["key"]), {})
    meta = PROJECT_FACTOR_CATALOG[goal["key"]]
    return {
        **goal,
        "label": project.get("label", goal["key"]),
        "desc": project.get("desc", ""),
        "cost_inr": star.get("cost_inr", meta.get("cost_inr")),
        "price_status": star.get("price_status", meta.get("price_status", "unverified_estimate")),
        "step_labels": [
            PROJECT_CATALOG.get(key, {}).get("label", key)
            for key in goal["steps"]
        ],
    }


@router.get("/questions")
def get_questions():
    return [
        {
            "index": i,
            "key": q[0],
            "question": q[1],
            "options": list(q[2]) if q[2] else [],
            "multi": bool(q[2]),
        }
        for i, q in enumerate(picker.QUESTIONS)
    ]


@router.post("/answers")
def save_answers(req: SurveyAnswerRequest, forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    session.survey_answers.update(req.answers)
    if req.step is not None:
        session.survey_step = req.step
    session.profile = picker.normalize_survey_answers(session.survey_answers)
    return {"status": "ok", "answers": session.survey_answers, "step": session.survey_step}


@router.post("/rank")
def rank_projects(req: SurveyRankRequest, forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    if req.answers:
        session.survey_answers.update(req.answers)
        session.profile = picker.normalize_survey_answers(session.survey_answers)

    profile = dict(session.profile) if session.profile else picker.normalize_survey_answers(session.survey_answers)
    resume_factors = session.resume or dict(skills=[], languages=[], tools=[], projects=[])
    profile["experience"] = list(dict.fromkeys(profile.get("experience", []) + [item["id"] for item in resume_factors.get("skills", []) if item.get("confirmed")]))
    profile["languages"] = list(dict.fromkeys(profile.get("languages", []) + [item["id"] for item in resume_factors.get("languages", []) if item.get("confirmed")]))
    profile["tools"] = list(dict.fromkeys(profile.get("tools", []) + [item["id"] for item in resume_factors.get("tools", []) if item.get("confirmed")]))
    profile["resume"] = resume_factors
    if req.hours_per_week is not None or req.deadline_weeks is not None:
        existing_schedule = profile.get("schedule") or {}
        profile["schedule"] = {
            "hours_per_week": req.hours_per_week if req.hours_per_week is not None else existing_schedule.get("hours_per_week"),
            "deadline_weeks": req.deadline_weeks if req.deadline_weeks is not None else existing_schedule.get("deadline_weeks"),
        }
    profile["completed_project_ids"] = sorted(set(req.completed_project_ids) if req.completed_project_ids is not None else set(profile.get("completed_project_ids", [])))
    if session.career_research:
        profile["career_research"] = session.career_research

    if RECOMMENDER_VERSION == "v2":
        ranked = picker.rank_factor_projects_v2(profile, limit=req.limit)
        results = []
        for item in ranked["results"]:
            proj = PROJECT_CATALOG[item.key]
            meta = PROJECT_FACTOR_CATALOG[item.key]
            factor_payload = _factor_chart_payload(item.key, profile, item.final)
            results.append({
                "key": item.key,
                "label": proj.get("label", item.key),
                "desc": proj.get("desc", ""),
                "domain": meta.get("domain", ""),
                "build_hours": meta.get("build_hours", 0),
                "cost_inr": meta.get("cost_inr"),
                "price_status": (
                    meta.get("price_status")
                    or next((p.get("price_status") for p in STAR_PROJECTS if p["key"] == item.key), None)
                    or ("unverified_estimate" if meta.get("cost_inr") is not None else "pending_verification")
                ),
                "parts_availability_india": meta.get("parts_availability_india", 3),
                "tier": item.tier,
                "reasons": item.reasons,
                "learn_skills": item.learn_skills,
                "unlocks": item.unlocks,
                "flags": item.flags,
                "breakdown": {
                    "interest": item.interest,
                    "level": item.level,
                    "feasibility": item.feasibility,
                    "impact": item.impact,
                },
                "readiness": item.readiness,
                "debug_score": item.final,
                "bom_supported": proj.get("bom_supported", False),
                "is_star": item.is_star,
                **factor_payload,
            })

        goal_result = _serialize_star_goal(ranked["goal"])
        if not ranked["needs_more_info"]:
            session.stage = "results"
        return {
            "recommender_version": "v2",
            "results": results,
            "goal": goal_result,
            "needs_more_info": ranked["needs_more_info"],
            "missing": ranked["missing"],
            "total_available": len(RECOMMENDATION_PROJECT_KEYS),
        }

    ranked = picker.rank_factor_projects(profile, limit=req.limit)
    results = []
    for key, score in ranked:
        proj = PROJECT_CATALOG.get(key, {})
        meta = PROJECT_FACTOR_CATALOG.get(key, {})
        factor_payload = _factor_chart_payload(key, profile, score)

        results.append({
            "key": key,
            "label": proj.get("label", key),
            "desc": proj.get("desc", ""),
            "domain": meta.get("domain", ""),
            "build_hours": meta.get("build_hours", 0),
            "cost_inr": meta.get("cost_inr", 0),
            "parts_availability_india": meta.get("parts_availability_india", 3),
            "score": score,
            "bom_supported": proj.get("bom_supported", False),
            "tools_required": sorted(meta.get("tools_required", [])),
            "required_skills": sorted(meta.get("required_skills", [])),
            "prerequisites": sorted(meta.get("prerequisites", [])),
            "safety": sorted(meta.get("safety", [])) if meta.get("safety") else [],
            "constraints": meta.get("constraints", ""),
            "competition_event": meta.get("competition_event", ""),
            **factor_payload,
        })

    goal = picker.select_star_project_goal(profile, (key for key, _ in ranked))
    excluded = []
    for key in RECOMMENDATION_PROJECT_KEYS:
        el = picker.eligibility(key, profile)
        if not el["eligible"]:
            excluded.append({
                "key": key,
                "label": PROJECT_CATALOG[key]["label"],
                "reasons": el["reasons"],
            })

    session.stage = "results"
    return {
        "recommender_version": "v1",
        "results": results,
        "goal": _serialize_star_goal(goal),
        "excluded": excluded,
        "total_available": len(RECOMMENDATION_PROJECT_KEYS),
        "survey_answer_count": sum(bool(profile.get(k)) for k in ("career", "experience", "languages", "tools", "hardware", "goal", "interests"))
    }


@router.post("/feedback")
def record_recommendation_feedback(req: SurveyFeedbackRequest):
    from core.recommendation_catalog import PROJECT_CATALOG

    if req.project_id not in PROJECT_CATALOG:
        raise HTTPException(status_code=404, detail="Unknown project ID")
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "project_id": req.project_id,
        "signal": req.signal,
        "context": req.context.model_dump(exclude_none=True),
    }
    with FEEDBACK_LOCK:
        with FEEDBACK_PATH.open("a", encoding="utf-8") as feedback_file:
            feedback_file.write(json.dumps(event, separators=(",", ":")) + "\n")
    return {"status": "recorded"}


@router.post("/career-research")
def research_career(req: CareerResearchRequest, forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    tinyfish_enabled = bool(os.getenv("TINYFISH_API_KEY"))
    if not tinyfish_enabled:
        return {"error": "TinyFish API key not configured", "signals": [], "sources": []}
    try:
        res = pipeline.research_career_target(query)
        session.career_research = res
        return res
    except Exception as e:
        err_res = {"query": query, "signals": [], "sources": [], "error": str(e)[:180]}
        session.career_research = err_res
        return err_res
