from sqlalchemy import Column, Integer, String, Float
from database import Base


class Product(Base):
    __tablename__ = "products"

    id               = Column(Integer, primary_key=True, index=True)
    label            = Column(String, unique=True, index=True, nullable=False)  # EI class label
    name             = Column(String, nullable=False)
    price            = Column(Float, nullable=False)
    approx_weight_g  = Column(Float, nullable=True)
    image_url        = Column(String, nullable=True)
    stock_quantity      = Column(Integer, default=0)
    low_stock_threshold = Column(Integer, default=10)
