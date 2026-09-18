from fastapi import APIRouter

from app import models

router = APIRouter()


@router.get("/health")
def health() -> dict:
    status = {"status": "ok", "app": "qkd-backend", "version": "0.1.0"}

    db_status = models.check_db()
    status["database"] = db_status
    if db_status != "ok":
        status["status"] = "degraded"

    return status
