import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
    PROJECT_NAME: str = "Momaz POS - Retail Pakaian (Multi-Tenant)"
    VERSION: str = "2.0.0"

    # Cloud Database (Neon.tech PostgreSQL)
    # POOLED URL — untuk query reguler sehari-hari
    # Neon pooler (PgBouncer) tidak support startup params seperti search_path
    # URL rewrite: postgres:// → postgresql:// (psycopg3 compatibility)
    raw_db_url: str = (
        os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
        or os.getenv("POSTGRES_URL_NON_POOLING")
        or ""
    ).strip()
    if raw_db_url.startswith("postgres://"):
        raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)
    
    DATABASE_URL: str = raw_db_url

    # UNPOOLED URL — wajib untuk DDL (CREATE SCHEMA, CREATE TABLE)
    # Neon pooler tidak bisa handle DDL, gunakan direct/unpooled connection
    raw_db_url_unpooled: str = (
        os.getenv("POSTGRES_URL_NON_POOLING")
        or os.getenv("DATABASE_URL_UNPOOLED")
        or raw_db_url  # fallback ke pooled jika tidak ada unpooled
    ).strip()
    if raw_db_url_unpooled.startswith("postgres://"):
        raw_db_url_unpooled = raw_db_url_unpooled.replace("postgres://", "postgresql://", 1)
    
    DATABASE_URL_UNPOOLED: str = raw_db_url_unpooled
    
    # Master Database (Global Users & Tenants Registry)
    MASTER_DATABASE_PATH: Path = BASE_DIR / "master.db"
    MASTER_DATABASE_URL: str = DATABASE_URL if DATABASE_URL else f"sqlite:///{MASTER_DATABASE_PATH}"
    MASTER_DATABASE_URL_UNPOOLED: str = DATABASE_URL_UNPOOLED if DATABASE_URL_UNPOOLED else f"sqlite:///{MASTER_DATABASE_PATH}"
    
    # Tenants Database Directory (used when running in SQLite fallback mode)
    TENANTS_DIR: Path = BASE_DIR / "tenants"
    
    # Security: production requires an explicit key; local keys are process-local.
    IS_PRODUCTION: bool = os.getenv("PRODUCTION", "").strip().lower() in {"1", "true", "yes", "on"}
    configured_secret: str = os.getenv("SECRET_KEY", "").strip()
    if IS_PRODUCTION and (len(configured_secret.encode("utf-8")) < 32 or configured_secret.startswith("super-secret-momaz-pos-")):
        raise RuntimeError("SECRET_KEY produksi wajib diisi dengan kunci acak minimal 32 byte.")
    SECRET_KEY: str = configured_secret or secrets.token_urlsafe(48)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # SQLite Performance (configurable via env)
    SQLITE_SYNCHRONOUS: str = os.getenv("SQLITE_SYNCHRONOUS", "NORMAL")  # NORMAL, FULL, or OFF

settings = Settings()
