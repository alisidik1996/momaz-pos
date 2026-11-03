"""
Dual-database synchronization utilities for Master DB <-> Tenant DB user sync.
Implements atomic-like pattern with rollback on failure.
"""
import logging
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class DualDBSyncError(Exception):
    """Raised when dual-DB sync fails and requires manual intervention."""
    pass


def sync_user_to_master(
    tenant_db: Session,
    master_db: Session,
    tenant_id: Optional[int],
    username: str,
    password_hash: str,
    full_name: str,
    role: str,
    is_active: bool
) -> bool:
    """
    Sync tenant user to master database.
    Returns True on success, raises DualDBSyncError on failure.

    Pattern: Tenant DB commit happens BEFORE this is called.
    If master sync fails, we log error but don't rollback tenant
    (user can still work in tenant, login might fail until manual fix).
    """
    from app.modules.tenants.models import MasterUser, Tenant

    try:
        # Case-insensitive lookup
        username_normalized = username.lower()
        m_user = master_db.query(MasterUser).filter(MasterUser.username == username_normalized).first()

        if not m_user:
            m_user = MasterUser(
                username=username_normalized,
                password_hash=password_hash,
                full_name=full_name,
                role=role,
                tenant_id=tenant_id,
                is_active=is_active
            )
            master_db.add(m_user)
        else:
            # Update existing
            m_user.password_hash = password_hash
            m_user.full_name = full_name
            m_user.role = role
            m_user.is_active = is_active
            if tenant_id:
                m_user.tenant_id = tenant_id

        master_db.commit()
        return True

    except SQLAlchemyError as e:
        master_db.rollback()
        logger.error(f"Failed to sync user '{username}' to master DB: {e}")
        raise DualDBSyncError(f"Master DB sync failed: {e}")


def sync_user_update_to_master(
    master_db: Session,
    username: str,
    full_name: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    password_hash: Optional[str] = None
) -> bool:
    """Sync user updates to master DB."""
    from app.modules.tenants.models import MasterUser

    try:
        # Case-insensitive lookup
        username_normalized = username.lower()
        m_user = master_db.query(MasterUser).filter(MasterUser.username == username_normalized).first()
        if not m_user:
            logger.warning(f"User '{username}' not found in master DB for update sync")
            return False

        if full_name is not None:
            m_user.full_name = full_name
        if role is not None:
            m_user.role = role
        if is_active is not None:
            m_user.is_active = is_active
        if password_hash:
            m_user.password_hash = password_hash

        master_db.commit()
        return True

    except SQLAlchemyError as e:
        master_db.rollback()
        logger.error(f"Failed to sync user update '{username}' to master DB: {e}")
        raise DualDBSyncError(f"Master DB update sync failed: {e}")


def sync_user_delete_to_master(master_db: Session, username: str) -> bool:
    """Sync user deletion to master DB."""
    from app.modules.tenants.models import MasterUser

    try:
        # Case-insensitive lookup
        username_normalized = username.lower()
        m_user = master_db.query(MasterUser).filter(MasterUser.username == username_normalized).first()
        if m_user:
            master_db.delete(m_user)
            master_db.commit()
        return True

    except SQLAlchemyError as e:
        master_db.rollback()
        logger.error(f"Failed to delete user '{username}' from master DB: {e}")
        # Don't raise - deletion already happened in tenant DB
        return False
