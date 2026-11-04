import sys
from pathlib import Path
root = Path(__file__).resolve().parent
sys.path.insert(0, str(root))

from app.database import MasterSessionLocal, TenantManager
from app.modules.tenants.models import MasterUser, Tenant
from app.modules.auth.models import User as TenantUser
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def normalize_master():
    db = MasterSessionLocal()
    try:
        updated = 0
        for user in db.query(MasterUser).all():
            norm = user.username.lower()
            if user.username != norm:
                logger.info(f"Master: {user.username} -> {norm}")
                user.username = norm
                updated += 1
        db.commit()
        logger.info(f"Master: {updated} normalized")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Master failed: {e}")
        return False
    finally:
        db.close()

def normalize_tenants():
    db = MasterSessionLocal()
    try:
        tenants = db.query(Tenant).filter(Tenant.is_active == True).all()
        for tenant in tenants:
            logger.info(f"Tenant: {tenant.slug}")
            try:
                tdb = TenantManager.get_session(tenant.slug)
                try:
                    updated = 0
                    for user in tdb.query(TenantUser).all():
                        norm = user.username.lower()
                        if user.username != norm:
                            logger.info(f"  {user.username} -> {norm}")
                            user.username = norm
                            updated += 1
                    tdb.commit()
                    logger.info(f"  {updated} normalized")
                finally:
                    tdb.close()
            except Exception as e:
                logger.error(f"  Failed: {e}")
        return True
    finally:
        db.close()

if __name__ == "__main__":
    logger.info("=== FIX 401 AUTH ERRORS ===")
    if normalize_master() and normalize_tenants():
        logger.info("DONE! Clear browser cookies and login.")
    else:
        logger.error("FAILED! Check errors above.")
        sys.exit(1)
