from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from config import settings

engine = create_engine(
    settings.DATABASE_URL,
    # Required for SQLite — allows the same connection across threads
    connect_args={"check_same_thread": False}
    if "sqlite" in settings.DATABASE_URL
    else {},
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
