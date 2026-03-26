from __future__ import annotations

from fastapi import APIRouter, Depends

from app.metrics import metrics
from app.auth.deps import require_read_only

router = APIRouter(prefix="/metrics")


@router.get("/traffic")
async def traffic(_user: dict = Depends(require_read_only)):
    return await metrics.snapshot()
