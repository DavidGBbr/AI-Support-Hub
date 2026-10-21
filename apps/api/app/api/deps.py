import hmac
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

bearer_scheme = HTTPBearer(auto_error=False)


def _parse_uuid(raw: str) -> UUID | None:
    try:
        return UUID(raw)
    except (TypeError, ValueError):
        return None


def require_billing_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> UUID:
    """Resolve the workspace the caller is allowed to administer.

    Temporary seam. It binds one bearer token to one workspace and stands in
    for the server side membership resolution described in ADR 0001, which
    arrives with the authentication and workspace cards. It fails closed: with
    no token configured the billing endpoints answer 503.
    """
    settings = get_settings()
    if not settings.billing_admin_token or not settings.billing_admin_workspace_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing administration is not configured",
        )
    if credentials is None or not hmac.compare_digest(
        credentials.credentials.encode(), settings.billing_admin_token.encode()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing credentials",
        )
    workspace_id = _parse_uuid(settings.billing_admin_workspace_id)
    if workspace_id is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing administration is not configured",
        )
    return workspace_id


def require_workspace_access(workspace_id: str, allowed: UUID) -> UUID:
    """Check that the caller may act on the requested workspace.

    A workspace the caller cannot reach answers 404, the same answer given for
    a workspace that does not exist.
    """
    requested = _parse_uuid(workspace_id)
    if requested is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid workspace_id",
        )
    if requested != allowed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return requested
