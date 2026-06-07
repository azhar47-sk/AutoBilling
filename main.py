"""
main.py
-------
FastAPI application entry point.

Start with:
    uvicorn main:app --reload --port 8000

Auto-docs at:
    http://localhost:8000/docs
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import engine, Base
from config import settings
from models import owner, product, model_version, receipt    # register all models

from routers import auth, products, training, model, receipts
from services.auth import hash_password
from database import SessionLocal
from models.owner import Owner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("main")


# ── startup / shutdown ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Seed default owner account if none exists
    db = SessionLocal()
    try:
        if not db.query(Owner).first():
            db.add(Owner(
                email=settings.OWNER_EMAIL,
                hashed_password=hash_password(settings.OWNER_PASSWORD),
            ))
            db.commit()
            log.info("Created default owner account: %s", settings.OWNER_EMAIL)
    finally:
        db.close()

    log.info("AutoBill backend ready")
    yield
    log.info("AutoBill backend shutting down")


# ── app ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AutoBill API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(auth.router)
app.include_router(products.router)
app.include_router(training.router)
app.include_router(model.router)
app.include_router(receipts.router)


@app.get("/health", methods=["GET", "HEAD"])
def health():
    return {"status": "ok"}
