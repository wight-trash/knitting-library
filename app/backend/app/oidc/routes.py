"""Routes for signing in with Keycloak. Fork only, see FORK.md "Signing in with Keycloak"."""
from fastapi import APIRouter, Depends, Request

from app.auth.service import require_admin
from app.oidc import service

router = APIRouter()
# FastAPI copies a router's start-up handlers into the app when the router is included.
router.add_event_handler("startup", service.sync_on_startup)


@router.get("/api/auth/oidc/config")
def oidc_config():
    return service.public_config()


@router.get("/api/auth/oidc/start")
def oidc_start(request: Request):
    return service.start(request)


@router.get("/api/auth/oidc/callback")
def oidc_callback(request: Request, code: str = "", state: str = "", error: str = "", iss: str = ""):
    return service.callback(request, code=code, state=state, error=error, iss=iss)


@router.get("/api/auth/oidc/links")
def oidc_links(_admin: dict = Depends(require_admin)):
    return service.linked_accounts()
