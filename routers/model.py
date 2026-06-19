"""
routers/model.py
----------------
Two endpoints used by the Pi model watcher:

  GET /model/latest   → returns version + sha256 + download_url
  GET /model/download → streams the actual .eim file
"""

import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from database import get_db
from models.model_version import ModelVersion
from schemas import ModelLatestOut, ModelVersionOut
from services.auth import require_pi, require_owner
from sqlalchemy.orm import Session

router = APIRouter(prefix="/model", tags=["model"])


@router.get("/latest", response_model=ModelLatestOut)
def get_latest_model(
    db: Session = Depends(get_db),
    _:  None    = Depends(require_pi),
):
    """
    Pi calls this every POLL_INTERVAL_SEC.
    Returns sha256 of the latest approved+deployed model.
    If sha256 differs from what's installed, Pi downloads the new .eim.
    """
    mv = (
        db.query(ModelVersion)
        .filter(ModelVersion.approved == True, ModelVersion.deployed == True)
        .order_by(ModelVersion.version.desc())
        .first()
    )
    if not mv:
        raise HTTPException(status_code=404, detail="No deployed model yet")

    return ModelLatestOut(
        version=mv.version,
        sha256=mv.sha256,
        download_url=f"/model/download",
    )


@router.get("/download")
async def download_model(
    db: Session = Depends(get_db),
    _:  None    = Depends(require_pi),
):
    """Stream .eim directly from Edge Impulse to Pi."""
    mv = (
        db.query(ModelVersion)
        .filter(ModelVersion.approved == True, ModelVersion.deployed == True)
        .order_by(ModelVersion.version.desc())
        .first()
    )
    if not mv:
        raise HTTPException(status_code=404, detail="No deployed model")

    # Stream directly from Edge Impulse
    import httpx
    from fastapi.responses import StreamingResponse
    from services.edge_impulse import EI_HEADERS, BASE, PID

    url = f"{BASE}/api/{PID}/deployment/download?type=runner-linux-armv7"

    async def stream():
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream("GET", url, headers=EI_HEADERS) as resp:
                async for chunk in resp.aiter_bytes(65536):
                    yield chunk

    return StreamingResponse(
        stream(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=current.eim"}
    )


# ── Owner: list all model versions ───────────────────────────────────────────

@router.get("/versions", response_model=list[ModelVersionOut])
def list_versions(
    db: Session = Depends(get_db),
    owner_id: int = Depends(require_owner),
):
    return (
        db.query(ModelVersion)
        .order_by(ModelVersion.version.desc())
        .all()
    )
