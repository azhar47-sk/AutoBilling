from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models.receipt import Receipt
from schemas import ReceiptIn, ReceiptOut
from services.auth import require_owner, require_pi

router = APIRouter(prefix="/receipts", tags=["receipts"])


# ── Pi posts completed receipts ───────────────────────────────────────────────

@router.post("", response_model=ReceiptOut, status_code=201)
def create_receipt(
    body: ReceiptIn,
    db:   Session = Depends(get_db),
    _:    None    = Depends(require_pi),
):
    receipt = Receipt(
        items=body.items,
        total=body.total,
        payment_method=body.payment_method,
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    return receipt


@router.post("/item", status_code=204)
def log_item(
    db: Session = Depends(get_db),
    _:  None    = Depends(require_pi),
):
    """
    Optional per-item logging endpoint called by billing.py on each detection.
    Currently a no-op — extend if you want item-level analytics.
    """
    return


# ── Owner views sales history ─────────────────────────────────────────────────

@router.get("", response_model=list[ReceiptOut])
def list_receipts(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    owner_id: int = Depends(require_owner),
):
    return (
        db.query(Receipt)
        .order_by(Receipt.paid_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
