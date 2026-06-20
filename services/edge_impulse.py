"""
services/edge_impulse.py
------------------------
All Edge Impulse REST API interactions:
  - upload_images()     → upload labelled training images
  - trigger_train()     → start a training job
  - poll_status()       → check job progress + accuracy
  - download_eim()      → download the compiled .eim for Linux AARCH64
"""

import os
import logging
import hashlib
import asyncio
from pathlib import Path

import httpx
from config import settings

log = logging.getLogger("edge_impulse")

EI_HEADERS = {
    "x-api-key":    settings.EI_API_KEY,
    "Content-Type": "application/json",
}
BASE = settings.EI_BASE_URL
PID  = settings.EI_PROJECT_ID


# ── upload images ─────────────────────────────────────────────────────────────

async def upload_images(label: str, image_paths: list[str], split_ratio: float = 0.8) -> int:
    """
    Upload images to Edge Impulse under a given label.
    Automatically splits data into training and testing sets.

    split_ratio: fraction of images to use for training (default 0.8 = 80/20 split)
    Returns the number of successfully uploaded images.
    """
    # Split images into training and testing
    split_index  = int(len(image_paths) * split_ratio)
    train_images = image_paths[:split_index]
    test_images  = image_paths[split_index:]

    log.info(
        "Splitting %d images for label '%s': %d training / %d testing",
        len(image_paths), label, len(train_images), len(test_images)
    )

    uploaded = 0
    uploaded += await _upload_batch(label, train_images, "training")
    uploaded += await _upload_batch(label, test_images,  "testing")

    log.info("Uploaded %d/%d images for label '%s'", uploaded, len(image_paths), label)
    return uploaded


async def _upload_batch(label: str, image_paths: list[str], category: str) -> int:
    """Upload a batch of images to a specific EI category (training or testing)."""
    url      = f"https://ingestion.edgeimpulse.com/api/{category}/files"
    uploaded = 0

    # Generous timeouts — image uploads can be slow
    timeout = httpx.Timeout(connect=30.0, write=120.0, read=60.0, pool=30.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        for i, image_path in enumerate(image_paths):
            filename = Path(image_path).name
            with open(image_path, "rb") as f:
                image_data = f.read()

            # Retry up to 3 times per image
            for attempt in range(3):
                try:
                    resp = await client.post(
                        url,
                        headers={
                            "x-api-key": settings.EI_API_KEY,
                            "x-label":   label,
                        },
                        files={
                            "data": (f"{label}.{category}.{i:04d}.jpg", image_data, "image/jpeg"),
                        },
                    )

                    if resp.status_code in (200, 201):
                        uploaded += 1
                        log.debug("Uploaded %s → EI %s '%s'", filename, category, label)
                        break
                    else:
                        log.warning("Upload %s attempt %d failed: %d %s",
                                    filename, attempt + 1, resp.status_code, resp.text[:100])

                except (httpx.WriteTimeout, httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
                    log.warning("Timeout on %s attempt %d: %s", filename, attempt + 1, exc)
                    if attempt == 2:
                        log.error("Giving up on %s after 3 attempts", filename)
                    await asyncio.sleep(2)  # brief pause before retry

    return uploaded


# ── trigger training ──────────────────────────────────────────────────────────

async def trigger_train() -> str:
    """
    Start a training job on Edge Impulse.
    Tries multiple endpoints since EI has changed their API over versions.
    Returns the job_id string.
    """
    # Endpoints to try in order
    url = f"{BASE}/api/{PID}/jobs/build-ondevice-model"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            url,
            headers=EI_HEADERS,
            params={"type": "runner-linux-armv7"},   # query param — deployment type
            json={"engine": "tflite"},                  # body — engine type
        )
        log.info("Training response %d: %s", resp.status_code, resp.text[:300])

        if resp.status_code in (200, 201):
            data = resp.json()
            if data.get("success") is False:
                raise RuntimeError(f"Edge Impulse error: {data.get('error')}")
            job_id = str(data.get("id", data.get("jobId", "")))
            if job_id:
                log.info("Training job started: %s", job_id)
                return job_id
            raise RuntimeError(f"No job ID in response: {data}")

        raise RuntimeError(f"Training failed: {resp.status_code} {resp.text[:200]}")


# ── poll job status ───────────────────────────────────────────────────────────

async def poll_status(job_id: str) -> dict:
    """
    Poll a training job and return:
    {
        "status":   "queued" | "running" | "completed" | "failed",
        "progress": 0-100,
        "accuracy": float | None,
    }
    Response format from EI:
    {"success":true,"job":{"id":...,"finishedSuccessful":true/false/null,...}}
    """
    url = f"{BASE}/api/{PID}/jobs/{job_id}/status"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=EI_HEADERS)
        log.info("Poll job %s → %d", job_id, resp.status_code)

        if resp.status_code != 200:
            log.warning("Poll failed for job %s: %d", job_id, resp.status_code)
            return {"status": "running", "progress": 0, "accuracy": None}

        body = resp.json()

    if not body.get("success"):
        return {"status": "failed", "progress": 0, "accuracy": None}

    job = body.get("job", {})

    finished_successful = job.get("finishedSuccessful")
    finished            = job.get("finished")        # timestamp when done

    # Job failed
    if finished_successful is False:
        return {"status": "failed", "progress": 0, "accuracy": None}

    # Job completed successfully
    if finished_successful is True:
        accuracy = await _fetch_accuracy()
        log.info("Job %s completed, accuracy=%s", job_id, accuracy)
        return {"status": "completed", "progress": 100, "accuracy": accuracy}

    # Job still running — estimate progress from timestamps
    progress = 0
    if job.get("started") and not finished:
        try:
            from datetime import datetime, timezone
            started = datetime.fromisoformat(
                job["started"].replace("Z", "+00:00"))
            now     = datetime.now(timezone.utc)
            elapsed = (now - started).seconds
            # Training typically takes 5-15 min, show proportional progress
            progress = min(90, int(elapsed / 600 * 90))
        except Exception:
            progress = 0

    return {"status": "running", "progress": progress, "accuracy": None}


async def _fetch_accuracy() -> float | None:
    """
    1. Trigger validation job POST /jobs/classify?impulseId=3
    2. Poll until job completes
    3. Fetch accuracyScore from GET /classify/all/result
    """
    try:
        # Step 1 — trigger validation job
        val_job_id = await _trigger_validation()
        if not val_job_id:
            log.warning("Could not start validation job — fetching last result")
        else:
            # Step 2 — poll until validation job completes (max 5 min)
            log.info("Waiting for validation job %s...", val_job_id)
            for _ in range(20):
                await asyncio.sleep(15)
                done = await _poll_validation_job(val_job_id)
                if done:
                    log.info("Validation job %s completed", val_job_id)
                    break

    except Exception as exc:
        log.warning("Validation flow error: %s", exc)

    # Step 3 — fetch accuracy result
    return await _fetch_accuracy_result()


async def _trigger_validation() -> str | None:
    """Trigger validation job — POST /jobs/classify?impulseId=3"""
    try:
        url = f"{BASE}/api/{PID}/jobs/classify"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                headers=EI_HEADERS,
                params={"impulseId": "3"},
            )
            log.info("Validation trigger → %d: %s", resp.status_code, resp.text[:200])
            if resp.status_code in (200, 201):
                data = resp.json()
                if data.get("success"):
                    job_id = str(data.get("id", ""))
                    log.info("Validation job started: %s", job_id)
                    return job_id
    except Exception as exc:
        log.warning("Validation trigger failed: %s", exc)
    return None


async def _poll_validation_job(job_id: str) -> bool:
    """Returns True when validation job is done (success or fail)."""
    try:
        url = f"{BASE}/api/{PID}/jobs/{job_id}/status"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=EI_HEADERS)
            if resp.status_code == 200:
                job = resp.json().get("job", {})
                finished = job.get("finishedSuccessful")
                if finished is True:
                    return True
                if finished is False:
                    log.warning("Validation job %s failed", job_id)
                    return True  # stop polling
    except Exception as exc:
        log.warning("Poll validation %s failed: %s", job_id, exc)
    return False


async def _fetch_accuracy_result() -> float | None:
    """Fetch accuracyScore from GET /classify/all/result"""
    try:
        url = f"{BASE}/api/{PID}/classify/all/result"

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=EI_HEADERS)

            log.info("Accuracy result → %d: %s",
                    resp.status_code,
                    resp.text[:200])

            if resp.status_code == 200:

                data = resp.json()

                if data.get("success"):

                    accuracy_data = data.get("accuracy", {})

                    if not accuracy_data:
                        log.warning("Accuracy field missing or empty in EI response: %s", data)
                        return None

                    acc = round(
                        float(accuracy_data.get("accuracyScore", 0)),
                        2
                    )

                    good = accuracy_data.get(
                        "totalSummary", {}
                    ).get("good", 0)

                    bad = accuracy_data.get(
                        "totalSummary", {}
                    ).get("bad", 0)

                    log.info(
                        "Accuracy: %.2f%% (%d correct / %d incorrect)",
                        acc,
                        good,
                        bad
                    )

                    return acc

    except Exception as exc:
        log.warning("Accuracy result fetch failed: %s", exc)

    return None


# ── download .eim ─────────────────────────────────────────────────────────────

async def download_eim(version: int) -> str:
    """
    Download the compiled Linux AARCH64 .eim file from Edge Impulse.
    Saves to MODELS_DIR/v{version}.eim.
    Returns the local file path.
    """
    dest = os.path.join(settings.MODELS_DIR, f"v{version}.eim")

    # EI deployment endpoint for Linux AARCH64
    deploy_url = (
        f"{BASE}/api/{PID}/deployment/download"
        f"?type=runner-linux-armv7"
    )

    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
        async with client.stream(
            "GET", deploy_url, headers={"x-api-key": settings.EI_API_KEY}
        ) as resp:
            resp.raise_for_status()
            tmp = dest + ".tmp"
            with open(tmp, "wb") as f:
                async for chunk in resp.aiter_bytes(65536):
                    f.write(chunk)

    os.chmod(tmp, 0o755)
    os.replace(tmp, dest)
    log.info("Downloaded .eim → %s", dest)
    return dest


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

# Retrain Function
async def trigger_retrain():
    url = (
        f"https://studio.edgeimpulse.com/v1/api/"
        f"{PID}/jobs/retrain"
    )

    headers = {
        "x-api-key": settings.EI_API_KEY
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, headers=headers)

    response.raise_for_status()

    data = response.json()

    if not data.get("success"):
        raise RuntimeError(f"Retrain failed: {data}")

    return data["id"]