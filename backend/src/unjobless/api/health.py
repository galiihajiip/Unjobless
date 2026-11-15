from fastapi import APIRouter
from fastapi.responses import JSONResponse

from unjobless.db.session import db_ping

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready() -> JSONResponse:
    ok = db_ping()
    return JSONResponse(
        {"status": "ok" if ok else "unavailable", "database": ok}, status_code=200 if ok else 503
    )
