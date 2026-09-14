from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.diagnostics import router as diagnostics_router
from app.api.health import router as health_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title="AI Support Hub API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(diagnostics_router)
