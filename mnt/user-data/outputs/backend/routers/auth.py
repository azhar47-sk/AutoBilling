from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.owner import Owner
from schemas import LoginRequest, TokenResponse
from services.auth import verify_password, create_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    owner = db.query(Owner).filter(Owner.email == body.email).first()
    if not owner or not verify_password(body.password, owner.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenResponse(access_token=create_token(owner.id))
