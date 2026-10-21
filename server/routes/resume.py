import os
from fastapi import APIRouter, Cookie, File, HTTPException, UploadFile
from typing import Optional

from core import pipeline, resume
from server.schemas import ResumeConfirmRequest
from server.state import store

router = APIRouter(prefix="/api/resume", tags=["resume"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@router.post("/upload")
async def upload_resume(file: UploadFile = File(...), forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    gemini_enabled = bool(os.getenv("GEMINI_API_KEY"))
    if not gemini_enabled:
        raise HTTPException(status_code=400, detail="Gemini API key is not configured on the server")

    filename = file.filename or "resume.pdf"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".pdf", ".docx", ".txt"):
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, and TXT files are supported")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (maximum 10MB)")

    try:
        text = resume.extract_text(filename, content)
        factors = pipeline.extract_resume_factors(text)
        session.resume = dict(factors, name=filename)
        return {
            "status": "ok",
            "name": filename,
            "skills": session.resume.get("skills", []),
            "languages": session.resume.get("languages", []),
            "tools": session.resume.get("tools", []),
            "projects": session.resume.get("projects", []),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Resume extraction failed: {type(e).__name__}")


@router.post("/confirm")
def confirm_factor(req: ResumeConfirmRequest, forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    if not session.resume:
        raise HTTPException(status_code=404, detail="No resume uploaded in current session")

    items = session.resume.get(req.group, [])
    if req.index < 0 or req.index >= len(items):
        raise HTTPException(status_code=400, detail="Invalid factor index")

    items[req.index]["confirmed"] = req.confirmed
    return {"status": "ok", "group": req.group, "index": req.index, "confirmed": req.confirmed}


@router.delete("")
def delete_resume(forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    session.resume = None
    return {"status": "ok"}
