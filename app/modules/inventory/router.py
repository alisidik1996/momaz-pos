from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.modules.auth.service import get_current_user, require_admin
from app.modules.auth.models import User
from app.modules.inventory.schemas import (
    StockAdjustmentRequest, StockInRequest, LowStockItemOut, StockMovementOut
)
from app.modules.inventory import service

router = APIRouter(prefix="/api/inventory", tags=["Inventory & Stock Management"])

@router.get("/low-stock", response_model=List[LowStockItemOut])
def get_low_stock(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return service.get_low_stock_variants(db)

@router.get("/movements", response_model=List[StockMovementOut])
def get_movements(
    variant_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    return service.get_stock_movements(db, variant_id=variant_id, limit=limit)

@router.post("/adjust")
def adjust_stock(
    req: StockAdjustmentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    movement = service.adjust_stock(db, req, user_id=current_user.id)
    return {"message": "Penyesuaian stok berhasil disimpan.", "movement_id": movement.id}

@router.post("/stock-in")
def stock_in(
    req: StockInRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    movements = service.process_stock_in(db, req, user_id=current_user.id)
    return {"message": f"Berhasil menambah stok {len(movements)} item pakaian."}
