"""Routes for signing in with Keycloak. Fork only, see FORK.md "Signing in with Keycloak"."""
from fastapi import APIRouter, Depends, Request

from app.auth.service import require_admin
from app.oidc import service

router = APIRouter()


@router.get("/api/auth/oidc/config")
def oidc_config():
    return service.public_config()


@router.get("/api/auth/oidc/start")
def oidc_start(request: Request):
    return service.start(request)


@router.get("/api/auth/oidc/callback")
def oidc_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    return service.callback(request, code=code, state=state, error=error)


@router.get("/api/auth/oidc/links")
def oidc_links(_admin: dict = Depends(require_admin)):
    return service.linked_accounts()


@router.delete("/api/auth/oidc/links/{username}")
def oidc_unlink(username: str, _admin: dict = Depends(require_admin)):
    return service.unlink(username)
