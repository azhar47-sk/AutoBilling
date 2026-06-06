import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    DATABASE_URL:       str   = os.getenv("DATABASE_URL", "sqlite:///./autobill.db")

    JWT_SECRET:         str   = os.getenv("JWT_SECRET", "dev-secret-change-me")
    JWT_ALGORITHM:      str   = "HS256"
    JWT_EXPIRE_MINUTES: int   = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))

    PI_SECRET:          str   = os.getenv("PI_SECRET", "pi-secret-change-me")

    EI_API_KEY:         str   = os.getenv("EI_API_KEY", "")
    EI_PROJECT_ID:      str   = os.getenv("EI_PROJECT_ID", "")
    EI_BASE_URL:        str   = "https://studio.edgeimpulse.com/v1"

    STORAGE_DIR:        str   = os.getenv("STORAGE_DIR", "./storage")
    MODELS_DIR:         str   = os.path.join(os.getenv("STORAGE_DIR", "./storage"), "models")
    IMAGES_DIR:         str   = os.path.join(os.getenv("STORAGE_DIR", "./storage"), "images")

    OWNER_EMAIL:        str   = os.getenv("OWNER_EMAIL", "owner@example.com")
    OWNER_PASSWORD:     str   = os.getenv("OWNER_PASSWORD", "changeme")


settings = Settings()

# Ensure storage directories exist
os.makedirs(settings.MODELS_DIR, exist_ok=True)
os.makedirs(settings.IMAGES_DIR, exist_ok=True)
