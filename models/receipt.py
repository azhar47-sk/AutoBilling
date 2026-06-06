from sqlalchemy import Column, Integer, String, Float, DateTime, JSON
from sqlalchemy.sql import func
from database import Base


class Receipt(Base):
    __tablename__ = "receipts"

    id             = Column(Integer, primary_key=True, index=True)
    items          = Column(JSON, nullable=False)       # list of cart item dicts
    total          = Column(Float, nullable=False)
    payment_method = Column(String, nullable=True)
    paid_at        = Column(DateTime(timezone=True), server_default=func.now())
