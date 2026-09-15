from fastapi import APIRouter, Response, status

from app.services.dependencies import probe_dependencies

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/dependencies")
def health_dependencies(response: Response) -> dict[str, str]:
    report = probe_dependencies()
    body = {
        "postgres": "ok" if report.postgres else "error",
        "redis": "ok" if report.redis else "error",
    }
    if not report.ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return body
