from sqlalchemy import Column, Integer, String
from database import Base


class Owner(Base):
    __tablename__ = "owners"

    id              = Column(Integer, primary_key=True, index=True)
    email           = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
