from pathlib import Path
from threading import RLock
from typing import Optional, Generator
import re

from fastapi import Request, HTTPException
from sqlalchemy import create_engine, event, text, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.config import settings

is_postgres = bool(settings.MASTER_DATABASE_URL and settings.MASTER_DATABASE_URL.startswith("postgres"))


def _configure_sqlite_engine(engine):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragmas(connection, _):
        synchronous = settings.SQLITE_SYNCHRONOUS.upper()
        if synchronous not in {"OFF", "NORMAL", "FULL", "EXTRA"}:
            raise ValueError("SQLITE_SYNCHRONOUS tidak valid.")
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute(f"PRAGMA synchronous={synchronous}")
        finally:
            cursor.close()


master_engine = create_engine(
    settings.MASTER_DATABASE_URL,
    connect_args={} if is_postgres else {"check_same_thread": False},
    pool_pre_ping=True,
    echo=False,
)
if not is_postgres:
    _configure_sqlite_engine(master_engine)
else:
    master_engine = master_engine.execution_options(schema_translate_map={None: "public"})

MasterSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=master_engine)
MasterBase = declarative_base()
Base = declarative_base()
_master_unpooled_engine = None
_master_engine_lock = RLock()


def _get_master_unpooled_engine():
    global _master_unpooled_engine
    with _master_engine_lock:
        if _master_unpooled_engine is None:
            _master_unpooled_engine = create_engine(
                settings.MASTER_DATABASE_URL_UNPOOLED,
                connect_args={} if is_postgres else {"check_same_thread": False},
                pool_pre_ping=True,
                echo=False,
            )
            if is_postgres:
                _master_unpooled_engine = _master_unpooled_engine.execution_options(schema_translate_map={None: "public"})
        return _master_unpooled_engine


def get_master_db() -> Generator[Session, None, None]:
    with MasterSessionLocal() as db:
        try:
            yield db
        except Exception:
            db.rollback()
            raise


class TenantManager:
    _engines = {}
    _sessionmakers = {}
    _lock = RLock()

    @classmethod
    def validate_slug(cls, tenant_slug: str) -> str:
        # New slugs use <=56 ASCII characters. Safe legacy Unicode slugs and
        # 100-character filenames remain accessible without renaming data.
        if not isinstance(tenant_slug, str) or len(tenant_slug) > 100 or not re.fullmatch(r"[\w-]+", tenant_slug):
            raise ValueError("Slug toko tidak valid (maksimal 100 karakter, tanpa pemisah path).")
        return tenant_slug

    @classmethod
    def schema_name(cls, tenant_slug: str) -> str:
        # Match the legacy PostgreSQL normalization and identifier truncation.
        return "tenant_" + re.sub(r"[^a-zA-Z0-9_]", "_", tenant_slug.lower())[:56]

    @classmethod
    def _check_schema_collision(cls, tenant_slug: str):
        from app.modules.tenants.models import Tenant

        schema = cls.schema_name(tenant_slug)
        with MasterSessionLocal() as db:
            for (other_slug,) in db.query(Tenant.slug).all():
                if other_slug != tenant_slug and cls.schema_name(other_slug) == schema:
                    raise HTTPException(status_code=409, detail="Nama database toko bentrok dengan toko lain. Konfigurasi tenant perlu diperbaiki.")

    @classmethod
    def get_db_path(cls, tenant_slug: str) -> Path:
        return settings.TENANTS_DIR / f"{cls.validate_slug(tenant_slug)}.db"

    @classmethod
    def get_engine(cls, tenant_slug: str):
        cls.validate_slug(tenant_slug)
        with cls._lock:
            if tenant_slug in cls._engines:
                return cls._engines[tenant_slug]
            engine = None
            try:
                if is_postgres:
                    cls._check_schema_collision(tenant_slug)
                    schema_name = cls.schema_name(tenant_slug)
                    # Fully qualify every ORM/DDL table, rather than relying on
                    # connection-local search_path that a transaction pooler can reset.
                    schema_map = {None: schema_name}
                    with _get_master_unpooled_engine().begin() as connection:
                        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
                        connection = connection.execution_options(schema_translate_map=schema_map)
                        cls._run_migrations(connection)
                        Base.metadata.create_all(bind=connection)
                    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, echo=False).execution_options(schema_translate_map=schema_map)
                else:
                    settings.TENANTS_DIR.mkdir(parents=True, exist_ok=True)
                    engine = create_engine(
                        f"sqlite:///{cls.get_db_path(tenant_slug)}",
                        connect_args={"check_same_thread": False},
                        pool_pre_ping=True,
                        echo=False,
                    )
                    _configure_sqlite_engine(engine)
                    cls._run_migrations(engine)
                    Base.metadata.create_all(bind=engine)
                factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, info={"tenant_slug": tenant_slug})
                # Publish the engine and factory together only after initialization succeeds.
                cls._sessionmakers[tenant_slug] = factory
                cls._engines[tenant_slug] = engine
                return engine
            except Exception:
                if engine is not None:
                    engine.dispose()
                raise

    @classmethod
    def get_session(cls, tenant_slug: str) -> Session:
        with cls._lock:
            cls.get_engine(tenant_slug)
            return cls._sessionmakers[tenant_slug]()

    @classmethod
    def _run_migrations(cls, bind):
        from app.core.migrations import migrate_tenant_schema

        migrate_tenant_schema(bind)

    @classmethod
    def init_tenant_db(cls, tenant_slug: str):
        cls.get_engine(tenant_slug)

    @classmethod
    def close_tenant(cls, tenant_slug: str):
        with cls._lock:
            engine = cls._engines.pop(tenant_slug, None)
            cls._sessionmakers.pop(tenant_slug, None)
            if engine is not None:
                engine.dispose()


def extract_token_from_string(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    import urllib.parse

    cleaned = urllib.parse.unquote(str(raw).strip()).strip('"').strip("'")
    while cleaned.lower().startswith("bearer "):
        cleaned = cleaned[7:].strip().strip('"').strip("'")
    return cleaned if cleaned else None


def get_request_identity(request: Request) -> dict:
    """Authenticate against the registry, never trust tenant/role claims alone."""
    identity = getattr(request.state, "identity", None)
    if identity is not None:
        return identity
    token = extract_token_from_string(request.headers.get("Authorization"))
    if not token:
        token = extract_token_from_string(request.cookies.get("access_token"))
    if not token:
        raise HTTPException(status_code=401, detail="Belum terotentikasi. Silakan login terlebih dahulu.", headers={"WWW-Authenticate": "Bearer"})
    from app.core.security import decode_access_token, TokenError, valid_auth_version
    from app.modules.tenants.models import MasterUser

    try:
        payload = decode_access_token(token)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc), headers={"WWW-Authenticate": "Bearer"}) from exc
    username = payload.get("sub") if payload else None
    if not isinstance(username, str) or not username.strip():
        raise HTTPException(status_code=401, detail="Token payload tidak valid.")
    with MasterSessionLocal() as db:
        user = db.query(MasterUser).filter(func.lower(MasterUser.username) == username.strip().lower()).first()
        if not user or not user.is_active or (payload.get("id") is not None and payload["id"] != user.id):
            raise HTTPException(status_code=401, detail="Pengguna tidak aktif atau sesi tidak valid.")
        if not valid_auth_version(payload.get("ver"), user.password_hash):
            raise HTTPException(status_code=401, detail="Sesi login tidak berlaku lagi. Silakan login kembali.")
        tenant = user.tenant
        if tenant and not tenant.is_active:
            raise HTTPException(status_code=403, detail="Toko tidak aktif.")
        slug = tenant.slug if tenant else None
        if payload.get("tenant_slug") is not None and payload["tenant_slug"] != slug:
            raise HTTPException(status_code=401, detail="Konteks toko pada sesi tidak valid.")
        if payload.get("tenant_id") is not None and payload["tenant_id"] != user.tenant_id:
            raise HTTPException(status_code=401, detail="Konteks toko pada sesi tidak valid.")
        identity = {
            "sub": user.username.strip().lower(), "id": user.id, "full_name": user.full_name,
            "role": user.role, "tenant_id": user.tenant_id, "tenant_slug": slug,
        }
    request.state.identity = identity
    return identity


def get_tenant_slug_from_request(request: Request) -> Optional[str]:
    identity = get_request_identity(request)
    slug = identity["tenant_slug"]
    selected_slug = request.headers.get("X-Tenant-Slug")
    if selected_slug is not None and selected_slug.strip() != slug:
        raise HTTPException(status_code=403, detail="Anda tidak memiliki akses ke toko yang dipilih.")
    return slug


def get_db(request: Request) -> Generator[Session, None, None]:
    tenant_slug = get_tenant_slug_from_request(request)
    if not tenant_slug:
        raise HTTPException(status_code=400, detail="Konteks toko tidak ditemukan. Silakan selesaikan setup toko.")
    db = TenantManager.get_session(tenant_slug)
    try:
        from app.modules.auth.models import User

        identity = get_request_identity(request)
        user = db.query(User).filter(func.lower(User.username) == identity["sub"]).first()
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="Pengguna toko tidak aktif atau tidak ditemukan.")
        db.info["tenant_id"] = identity["tenant_id"]
        request.state.current_user = user
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
