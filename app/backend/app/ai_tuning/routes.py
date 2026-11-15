"""Routes for AI tuning (admin only). Fork only, see FORK.md "AI tuning"."""
from fastapi import APIRouter, Body, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from app.ai_tuning import service
from app.auth.service import require_admin

router = APIRouter()


@router.get("/api/fork/ai/tuning")
async def get_tuning(model: str = "", base_url: str = "", _admin: dict = Depends(require_admin)):
    """The saved efforts, and the facts about `model` (the one selected on the page, saved or not)."""
    saved = await run_in_threadpool(service.ai_page_settings)
    model = (model or saved.get("ai_model", "")).strip()[:200]
    base_url = (base_url or saved.get("ai_base_url", "")).strip()[:500]
    openrouter = service.is_openrouter(base_url)
    info = await run_in_threadpool(service.model_info, model) if openrouter and model else None
    listed = openrouter and (await run_in_threadpool(service.catalogue)) is not None
    return {
        "settings": await run_in_threadpool(service.get_settings),
        "defaults": service.DEFAULTS,
        "features": list(service.FEATURES),
        "openrouter": openrouter,
        "catalogue_ok": listed,
        "model": model,
        "info": info,
        "prompts": service.prompts(),
    }


@router.put("/api/fork/ai/tuning")
async def put_tuning(data: dict = Body(...), _admin: dict = Depends(require_admin)):
    try:
        saved = await run_in_threadpool(service.set_settings, data.get("settings") or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"settings": saved}
