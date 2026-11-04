"""Tenant-scoped user synchronization with compensation for partial commits."""
import logging
from typing import Optional
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.core.transactions import lock_database_for_write

logger = logging.getLogger(__name__)


class DualDBSyncError(Exception):
    """Raised when a user change cannot be committed to both databases."""
    pass


def _get_master_user(master_db: Session, username: str, tenant_id: int):
    from app.modules.tenants.models import MasterUser

    user = master_db.query(MasterUser).filter(func.lower(MasterUser.username) == username.strip().lower()).first()
    if user is not None and user.tenant_id != tenant_id:
        raise HTTPException(status_code=400, detail="Username sudah digunakan oleh akun lain.")
    return user


def snapshot_master_user(master_db: Session, username: str, tenant_id: int):
    user = _get_master_user(master_db, username, tenant_id)
    return {column.name: getattr(user, column.name) for column in user.__table__.columns} if user else None


def commit_user_sync(tenant_db: Session, master_db: Session, username: str, tenant_id: int, original):
    """Commit the login registry first; restore it if the tenant commit fails."""
    from app.modules.tenants.models import MasterUser

    master_committed = False
    try:
        master_db.commit()
        master_committed = True
        tenant_db.commit()
    except SQLAlchemyError as exc:
        tenant_db.rollback()
        master_db.rollback()
        if master_committed:
            try:
                user = _get_master_user(master_db, username, tenant_id)
                if original is None:
                    if user is not None:
                        master_db.delete(user)
                elif user is None:
                    master_db.add(MasterUser(**original))
                else:
                    for field, value in original.items():
                        setattr(user, field, value)
                master_db.commit()
            except SQLAlchemyError:
                master_db.rollback()
                logger.error("User synchronization compensation failed")
        raise DualDBSyncError("Perubahan pengguna gagal disinkronkan.") from exc


def sync_user_to_master(
    tenant_db: Session,
    master_db: Session,
    tenant_id: Optional[int],
    username: str,
    password_hash: str,
    full_name: str,
    role: str,
    is_active: bool,
    commit: bool = True,
) -> bool:
    """Create a registry account; an existing username must never be overwritten."""
    from app.modules.tenants.models import MasterUser

    try:
        lock_database_for_write(master_db)
        if tenant_id is None:
            raise DualDBSyncError("Konteks toko tidak valid.")
        username_normalized = username.strip().lower()
        if _get_master_user(master_db, username_normalized, tenant_id) is not None:
            raise HTTPException(status_code=400, detail="Username sudah terdaftar.")
        master_db.add(MasterUser(
            username=username_normalized,
            password_hash=password_hash,
            full_name=full_name,
            role=role,
            tenant_id=tenant_id,
            is_active=is_active,
        ))
        if commit:
            master_db.commit()
        return True

    except SQLAlchemyError as e:
        master_db.rollback()
        raise DualDBSyncError("Sinkronisasi akun gagal.") from e


def sync_user_update_to_master(
    master_db: Session,
    username: str,
    tenant_id: int,
    full_name: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    password_hash: Optional[str] = None,
    commit: bool = True,
) -> bool:
    """Sync user updates to master DB."""
    try:
        lock_database_for_write(master_db)
        m_user = _get_master_user(master_db, username, tenant_id)
        if not m_user:
            return False

        if full_name is not None:
            m_user.full_name = full_name
        if role is not None:
            m_user.role = role
        if is_active is not None:
            m_user.is_active = is_active
        if password_hash:
            m_user.password_hash = password_hash

        if commit:
            master_db.commit()
        return True

    except SQLAlchemyError as e:
        master_db.rollback()
        raise DualDBSyncError("Sinkronisasi perubahan akun gagal.") from e


def sync_user_delete_to_master(master_db: Session, username: str, tenant_id: int, commit: bool = True) -> bool:
    """Sync user deletion to master DB."""
    try:
        lock_database_for_write(master_db)
        m_user = _get_master_user(master_db, username, tenant_id)
        if m_user:
            master_db.delete(m_user)
            if commit:
                master_db.commit()
        return True

    except SQLAlchemyError as e:
        master_db.rollback()
        raise DualDBSyncError("Sinkronisasi penghapusan akun gagal.") from e
