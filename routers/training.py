"""
routers/training.py
-------------------
Endpoints for the owner app training flow:

  POST /training/start       → upload images to EI + kick off training
  GET  /training/status/{id} → poll job progress
  POST /training/approve/{id}→ owner approves model → marks as deployable
"""

import os
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from database import get_db
from models.model_version import ModelVersion
from schemas import TrainingStartRequest, TrainingStatusOut, ModelVersionOut
from services.auth import require_owner
from services import edge_impulse as ei
from config import settings

router = APIRouter(prefix="/training", tags=["training"])
logger = logging.getLogger(__name__)
log    = logging.getLogger("training")

# In-memory job status cache so we don't hit EI on every poll
# { job_id: {"status": ..., "progress": ..., "accuracy": ...} }
_job_cache: dict[str, dict] = {}


# ── Start training ────────────────────────────────────────────────────────────

@router.post("/start")
async def start_training(
    body:             TrainingStartRequest,
    background_tasks: BackgroundTasks,
    db:               Session = Depends(get_db),
    owner_id:         int     = Depends(require_owner),
):
    """
    1. Find saved images for the label on disk
    2. Upload them to Edge Impulse
    3. Trigger training job
    4. Poll in background, save ModelVersion when done
    """
    logger.info("TRAINING API HIT")
    logger.info("Label: %s", body.label)
   
    label_dir = os.path.join(settings.IMAGES_DIR, body.label)
    print(f"[DEBUG] Training start called for label: {body.label}")
    print(f"[DEBUG] Looking for images in: {label_dir}")
    print(f"[DEBUG] Dir exists: {os.path.isdir(label_dir)}")
    if not os.path.isdir(label_dir):
        raise HTTPException(
            status_code=400,
            detail=f"No images found for label '{body.label}'. Upload images first.",
        )

    image_paths = [
        os.path.join(label_dir, f)
        for f in os.listdir(label_dir)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ]

    if len(image_paths) < 10:
        raise HTTPException(
            status_code=400,
            detail=f"Only {len(image_paths)} images found. Upload at least 10.",
        )

    # Upload images to EI
    logger.info("Uploading images to Edge Impulse...")
    logger.info("Label: %s", body.label)
    logger.info("Images found: %d", len(image_paths))
    uploaded = await ei.upload_images(body.label, image_paths)
    if uploaded == 0:
        raise HTTPException(status_code=502, detail="Failed to upload images to Edge Impulse")

    logger.info("Uploaded images: %d", uploaded)

    # Trigger training
    logger.info("Starting Edge Impulse training...")
    job_id = await ei.trigger_train()
    logger.info("Training Job ID: %s", job_id)
    _job_cache[job_id] = {"status": "queued", "progress": 0, "accuracy": None}

    # Poll in background
    background_tasks.add_task(_poll_until_done, job_id, db)

    return {"job_id": job_id, "uploaded_images": uploaded}


# ── Poll status ───────────────────────────────────────────────────────────────

@router.get("/status/{job_id}", response_model=TrainingStatusOut)
async def training_status(job_id: str, owner_id: int = Depends(require_owner)):
    if job_id not in _job_cache:
        # Fallback: ask EI directly if not in cache (e.g. after server restart)
        try:
            result = await ei.poll_status(job_id)
            _job_cache[job_id] = result
        except Exception:
            raise HTTPException(status_code=404, detail="Job not found")

    data = _job_cache[job_id]
    return TrainingStatusOut(job_id=job_id, **data)


# ── Approve model ─────────────────────────────────────────────────────────────

@router.post("/approve/{version_id}", response_model=ModelVersionOut)
async def approve_model(
    version_id: int,
    db:         Session = Depends(get_db),
    owner_id:   int     = Depends(require_owner),
):
    """
    Owner taps 'Approve' in the mobile app.
    Marks this ModelVersion as approved + deployed.
    The Pi will pick it up on its next poll cycle.
    """
    mv = db.query(ModelVersion).filter(ModelVersion.id == version_id).first()
    if not mv:
        raise HTTPException(status_code=404, detail="Model version not found")

    # Mark all previous versions as not deployed
    db.query(ModelVersion).filter(ModelVersion.deployed == True).update({"deployed": False})

    mv.approved    = True
    mv.deployed    = True
    mv.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(mv)

    log.info("Model version %d approved and set as active deployment", version_id)
    return mv


# ── Background poller ─────────────────────────────────────────────────────────

async def _poll_until_done(job_id: str, db: Session):
    """
    Poll Edge Impulse every 15s until the training job finishes.
    On completion, download the .eim and create a ModelVersion record.
    """
    log.info("Background poll started for job %s", job_id)

    for attempt in range(120):          # max ~30 minutes (120 × 15s)
        await asyncio.sleep(15)

        try:
            result = await ei.poll_status(job_id)
            _job_cache[job_id] = result
        except Exception as exc:
            log.warning("Poll attempt %d failed: %s", attempt, exc)
            continue

        if result["status"] == "failed":
            log.error("Training job %s failed", job_id)
            _job_cache[job_id] = {"status": "failed", "progress": 0, "accuracy": None}
            return

        if result["status"] == "completed":
            accuracy = result.get("accuracy")
            log.info("Training job %s completed (accuracy=%s)", job_id, accuracy)

            # Explicitly write accuracy back to cache so frontend sees it
            _job_cache[job_id] = {
                "status": "completed",
                "progress": 100,
                "accuracy": accuracy,
            }

            if accuracy is None:
                log.warning("Job %s completed but accuracy is None — check _fetch_accuracy_result", job_id)

            await _save_model_version(job_id, accuracy, db)
            return

    log.error("Gave up polling job %s after 30 minutes", job_id)
    _job_cache[job_id] = {"status": "failed", "progress": 0, "accuracy": None}

async def _save_model_version(job_id: str, accuracy: float | None, db: Session):
    """Save ModelVersion metadata — no file download needed."""
    last    = db.query(ModelVersion).order_by(ModelVersion.version.desc()).first()
    version = (last.version + 1) if last else 1

    # Compute sha256 from EI directly
    sha256 = f"ei-job-{job_id}"  # placeholder — real hash computed on Pi after download

    mv = ModelVersion(
        version   = version,
        sha256    = sha256,
        eim_path  = "",           # not stored locally
        accuracy  = accuracy,
        ei_job_id = job_id,
        approved  = False,
        deployed  = False,
    )
    db.add(mv)
    db.commit()
    log.info("Saved ModelVersion v%d", version)