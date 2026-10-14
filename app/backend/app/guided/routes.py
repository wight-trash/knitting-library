"""API for guided knitting, under /api/guided. Fork-only (see FORK.md)."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException

from app.auth.service import get_current_user, require_admin
from app.fork_migrations import ensure_fork_schema
from app.guided import jobs, settings

router = APIRouter()


def _guarded(fn, *args):
    try:
        return fn(*args)
    except jobs.GuideError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from None


def status(current_user: dict = Depends(get_current_user)) -> dict:
    """What the page needs to know before showing the Guided tab."""
    cfg = settings.ai_connection()
    return {"enabled": settings.guides_enabled(), "configured": bool(cfg["base_url"] and cfg["api_key"]),
            "model": cfg["model"], "can_change_settings": bool(current_user.get("is_admin"))}


def get_settings(current_user: dict = Depends(require_admin)) -> dict:
    s = settings.get_all()
    return {"enabled": settings.guides_enabled(), "model": s["fork_guide_model"]}


def put_settings(data: dict = Body(...), current_user: dict = Depends(require_admin)) -> dict:
    values = {}
    if "enabled" in data:
        values["fork_feature_guides"] = "true" if data["enabled"] else "false"
    if "model" in data:
        model = str(data["model"] or "").strip()
        if not model or len(model) > 120:
            raise HTTPException(status_code=400, detail="Give a model name, e.g. anthropic/claude-haiku-5.5")
        values["fork_guide_model"] = model
    settings.set_values(values)
    return get_settings(current_user)


def recipe_guide(recipe_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    """The guide for a pattern (if built) and its latest build, with progress. The page polls this."""
    return {"enabled": settings.guides_enabled(), "guide": jobs.get_guide(recipe_id), "job": jobs.latest_job(recipe_id)}


def start_build(recipe_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    return {"job": _guarded(jobs.start, recipe_id, current_user)}


def cancel_build(job_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    return {"job": _guarded(jobs.request_cancel, job_id)}


def on_startup() -> None:
    ensure_fork_schema()
    jobs.resume_on_startup()


router.add_api_route("/api/guided/status", status, methods=["GET"])
router.add_api_route("/api/guided/settings", get_settings, methods=["GET"])
router.add_api_route("/api/guided/settings", put_settings, methods=["PUT"])
router.add_api_route("/api/guided/recipes/{recipe_id}", recipe_guide, methods=["GET"])
router.add_api_route("/api/guided/recipes/{recipe_id}/build", start_build, methods=["POST"])
router.add_api_route("/api/guided/jobs/{job_id}/cancel", cancel_build, methods=["POST"])
