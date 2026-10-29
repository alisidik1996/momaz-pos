from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from app.database import get_db
from app.modules.setup.schemas import SetupInitRequest, SetupStatusResponse
from app.modules.setup import service
from app.core.models import StoreSettings

router = APIRouter(prefix="/api/setup", tags=["Initial Setup Wizard"])

@router.get("/status", response_model=SetupStatusResponse)
def get_setup_status(db: Session = Depends(get_db)):
    is_required = service.check_setup_required(db)
    store = db.query(StoreSettings).first()
    store_name = store.store_name if store else None
    return SetupStatusResponse(
        is_setup_required=is_required,
        store_name=store_name
    )

@router.post("/init")
def initialize_store(req: SetupInitRequest, response: Response, db: Session = Depends(get_db)):
    admin, token = service.initialize_system(db, req)
    
    # Set auth cookie for seamless transition into backoffice
    response.set_cookie(
        key="access_token",
        value=f"Bearer {token}",
        httponly=False,
        max_age=86400,
        samesite="lax"
    )

    return {
        "message": "Inisialisasi toko dan database berhasil!",
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": admin.id,
            "username": admin.username,
            "full_name": admin.full_name,
            "role": admin.role
        }
    }
