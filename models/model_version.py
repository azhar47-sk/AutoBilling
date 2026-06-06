from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.sql import func
from database import Base


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id           = Column(Integer, primary_key=True, index=True)
    version      = Column(Integer, nullable=False)          # auto-incremented
    sha256       = Column(String, nullable=False, unique=True)
    eim_path     = Column(String, nullable=False)           # path on server disk
    accuracy     = Column(Float, nullable=True)             # from EI training result
    ei_job_id    = Column(String, nullable=True)            # Edge Impulse job id
    approved     = Column(Boolean, default=False)           # owner approved
    deployed     = Column(Boolean, default=False)           # latest deployed to Pi
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    approved_at  = Column(DateTime(timezone=True), nullable=True)
