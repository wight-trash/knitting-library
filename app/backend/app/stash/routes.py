"""API for the stash in grams, under /api/stash, and the fork's combined settings, /api/fork/settings.
Fork-only (FORK.md, docs/guided-knitting/PHASE2-STASH.md).

Everything under /api/stash except /status answers 403 while the switch is off.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from app.auth.service import get_current_user, require_admin
from app.core.foundation import MAX_IMAGE_BYTES
from app.fork_migrations import ensure_fork_schema
from app.guided import settings as guided_settings
from app.stash import ballband, imagefetch, ledger, settings
from app.stash.ledger import StashError

router = APIRouter()


def _guarded(fn, *args):
    try:
        return fn(*args)
    except StashError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from None


def status(current_user: dict = Depends(get_current_user)) -> dict:
    """What the page needs before showing grams, the camera button and the server-side picture fetch."""
    ensure_fork_schema()
    enabled = settings.stash_enabled()
    return {"enabled": enabled, "ballband_available": enabled and ballband.available(),
            "can_change_settings": bool(current_user.get("is_admin"))}


def get_spec(yarn_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    return _guarded(ledger.get_spec, yarn_id)


def put_spec(yarn_id: str, data: dict = Body(...), current_user: dict = Depends(get_current_user)) -> dict:
    return _guarded(ledger.save_spec, yarn_id, data, current_user)


def list_items(current_user: dict = Depends(get_current_user)) -> dict:
    return _guarded(ledger.list_items, current_user)


def get_item(item_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    return _guarded(ledger.item_detail, item_id, current_user)


def purchase(item_id: str, data: dict = Body(default={}), current_user: dict = Depends(get_current_user)) -> dict:
    return _guarded(ledger.purchase, item_id, data, current_user)


def correct(item_id: str, data: dict = Body(default={}), current_user: dict = Depends(get_current_user)) -> dict:
    return _guarded(ledger.correct, item_id, data, current_user)


async def read_ballband(image: UploadFile = File(...), current_user: dict = Depends(get_current_user)) -> dict:
    _guarded(ledger.require_enabled)
    data = await image.read(MAX_IMAGE_BYTES + 1)
    return await run_in_threadpool(_guarded, ballband.read_ball_band, data)


async def fetch_image(url: str = "", current_user: dict = Depends(get_current_user)) -> Response:
    _guarded(ledger.require_enabled)
    try:
        data, kind = await imagefetch.fetch_image(url)
    except StashError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from None
    return Response(content=data, media_type=kind,
                    headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff",
                             "Content-Disposition": "inline"})


# ---------------------------------------------------------------- the fork's settings (admin)
def get_fork_settings(current_user: dict = Depends(require_admin)) -> dict:
    ensure_fork_schema()
    return {"stash_enabled": settings.stash_enabled(), "guides_enabled": guided_settings.guides_enabled(),
            "guide_model": guided_settings.get_all()["fork_guide_model"]}


def put_fork_settings(data: dict = Body(...), current_user: dict = Depends(require_admin)) -> dict:
    values = {}
    if "guides_enabled" in data:
        values["fork_feature_guides"] = "true" if data["guides_enabled"] else "false"
    if "guide_model" in data:
        model = str(data["guide_model"] or "").strip()
        if not model or len(model) > 120:
            raise HTTPException(status_code=400, detail="Give a model name, e.g. anthropic/claude-haiku-5.5")
        values["fork_guide_model"] = model
    if values:
        guided_settings.set_values(values)
    if "stash_enabled" in data:
        settings.set_enabled(bool(data["stash_enabled"]))
    return get_fork_settings(current_user)


router.add_api_route("/api/stash/status", status, methods=["GET"])
router.add_api_route("/api/stash/yarns/{yarn_id}/spec", get_spec, methods=["GET"])
router.add_api_route("/api/stash/yarns/{yarn_id}/spec", put_spec, methods=["PUT"])
router.add_api_route("/api/stash/items", list_items, methods=["GET"])
router.add_api_route("/api/stash/items/{item_id}", get_item, methods=["GET"])
router.add_api_route("/api/stash/items/{item_id}/purchase", purchase, methods=["POST"])
router.add_api_route("/api/stash/items/{item_id}/correct", correct, methods=["POST"])
router.add_api_route("/api/stash/ballband", read_ballband, methods=["POST"])
router.add_api_route("/api/stash/image", fetch_image, methods=["GET"])
router.add_api_route("/api/fork/settings", get_fork_settings, methods=["GET"])
router.add_api_route("/api/fork/settings", put_fork_settings, methods=["PUT"])
