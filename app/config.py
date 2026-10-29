import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
    PROJECT_NAME: str = "Momaz POS - Retail Pakaian (Multi-Tenant)"
    VERSION: str = "2.0.0"
    
    # Cloud Database (Neon.tech PostgreSQL / Vercel Postgres)
    # If not set, gracefully falls back to local SQLite files
    raw_db_url: str = (
        os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
        or os.getenv("POSTGRES_URL_NON_POOLING")
        or ""
    ).strip()
    if raw_db_url.startswith("postgres://"):
        raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)
    
    DATABASE_URL: str = raw_db_url
    
    # Master Database (Global Users & Tenants Registry)
    MASTER_DATABASE_PATH: Path = BASE_DIR / "master.db"
    MASTER_DATABASE_URL: str = DATABASE_URL if DATABASE_URL else f"sqlite:///{MASTER_DATABASE_PATH}"
    
    # Tenants Database Directory (used when running in SQLite fallback mode)
    TENANTS_DIR: Path = BASE_DIR / "tenants"
    
    # Vercel Blob Storage Credentials
    BLOB_READ_WRITE_TOKEN: str = os.getenv("BLOB_READ_WRITE_TOKEN", "").strip()
    BLOB_STORE_ID: str = os.getenv("BLOB_STORE_ID", "").strip()
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-momaz-pos-multi-tenant-key-2026")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

settings = Settings()
if not settings.DATABASE_URL:
    try:
        settings.TENANTS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
