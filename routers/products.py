import os
import shutil
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from pydantic import BaseModel

from database import get_db
from models.product import Product
from schemas import ProductCreate, ProductOut
from services.auth import require_owner, require_pi
from config import settings

router = APIRouter(prefix="/products", tags=["products"])
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Pi reads product catalogue ────────────────────────────────────────────────

@router.get("", response_model=list[ProductOut])
def list_products(
    db: Session = Depends(get_db),
    _: None = Depends(require_pi),         # Pi calls this with X-Pi-Secret
):
    """Return all products. Called by the Pi at startup to sync local DB."""
    return db.query(Product).all()


# ── Owner CRUD ────────────────────────────────────────────────────────────────

@router.get("/all", response_model=list[ProductOut])
def list_products_owner(
    db: Session = Depends(get_db),
    owner_id: int = Depends(require_owner),
):
    """Owner dashboard — returns all products."""
    return db.query(Product).all()


@router.post("", response_model=ProductOut, status_code=201)
def create_product(
    body: ProductCreate,
    db:   Session = Depends(get_db),
    owner_id: int = Depends(require_owner),
):
    existing = db.query(Product).filter(Product.label == body.label).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Label '{body.label}' already exists")

    product = Product(**body.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/{label}", status_code=204)
def delete_product(
    label: str,
    db:    Session = Depends(get_db),
    owner_id: int = Depends(require_owner),
):
    product = db.query(Product).filter(Product.label == label).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(product)
    db.commit()


# ── Image upload for a product ────────────────────────────────────────────────

@router.post("/{label}/images", status_code=201)
async def upload_product_images(
    label: str,
    files: list[UploadFile] = File(...),
    db:    Session = Depends(get_db),
    owner_id: int = Depends(require_owner),
):

    logger.info("Upload API HIT")
    logger.info("Label: %s", label)
    logger.info("Files received: %s", len(files))
    """
    Accept photo uploads from the owner mobile app.
    Saves to storage/images/{label}/ for later EI training.
    """
    product = db.query(Product).filter(Product.label == label).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    label_dir = os.path.join(settings.IMAGES_DIR, label)
    os.makedirs(label_dir, exist_ok=True)

    saved = []
    for upload in files:
        if not upload.content_type.startswith("image/"):
            continue
        dest = os.path.join(label_dir, upload.filename)
        with open(dest, "wb") as f:
            shutil.copyfileobj(upload.file, f)
        saved.append(upload.filename)

    # Use the first uploaded image as the product display image
    if saved and not product.image_url:
        product.image_url = f"/products/images/{label}/{saved[0]}"
        db.commit()

    return {"saved": len(saved), "files": saved}


# ── Serve product images ──────────────────────────────────────────────────────

from fastapi.responses import FileResponse


@router.get("/images/{label}/{filename}")
def get_product_image(label: str, filename: str):
    path = os.path.join(settings.IMAGES_DIR, label, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path)

#  stock update endpoint

class StockUpdateRequest(BaseModel):
    quantity:  int
    operation: str   # "add" | "subtract" | "set"

@router.patch("/{label}/stock", response_model=ProductOut)
def update_stock(
    label: str,
    body:  StockUpdateRequest,
    db:    Session = Depends(get_db),
    owner_id: int  = Depends(require_owner),
):
    product = db.query(Product).filter(Product.label == label).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if body.operation == "add":
        product.stock_quantity += body.quantity
    elif body.operation == "subtract":
        product.stock_quantity = max(0, product.stock_quantity - body.quantity)
    elif body.operation == "set":
        product.stock_quantity = body.quantity
    else:
        raise HTTPException(status_code=400, detail="operation must be add, subtract or set")

    db.commit()
    db.refresh(product)
    return product