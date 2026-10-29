from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.modules.auth.service import get_current_user
from app.modules.auth.models import User
from app.modules.shifts.schemas import ShiftOpenRequest, ShiftCloseRequest, ShiftOut
from app.modules.shifts import service

router = APIRouter(prefix="/api/shifts", tags=["Cashier Shifts & Cash Drawer"])

@router.get("/current", response_model=Optional[ShiftOut])
def get_current_shift(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    shift = service.get_active_shift(db, current_user.id)
    if not shift:
        return None
    out = ShiftOut.model_validate(shift)
    out.cashier_name = current_user.full_name
    return out

@router.post("/open", response_model=ShiftOut)
def open_shift(
    req: ShiftOpenRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    shift = service.open_shift(db, current_user.id, req)
    out = ShiftOut.model_validate(shift)
    out.cashier_name = current_user.full_name
    return out

@router.post("/{shift_id}/close", response_model=ShiftOut)
def close_shift(
    shift_id: int,
    req: ShiftCloseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    shift = service.close_shift(db, shift_id, current_user.id, req)
    out = ShiftOut.model_validate(shift)
    out.cashier_name = current_user.full_name
    return out

@router.get("/history", response_model=List[ShiftOut])
def get_history(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    return service.get_shifts_history(db, limit=limit)
