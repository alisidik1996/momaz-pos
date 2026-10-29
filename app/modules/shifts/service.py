from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException
from app.modules.shifts.models import CashierShift
from app.modules.shifts.schemas import ShiftOpenRequest, ShiftCloseRequest, ShiftOut

def get_active_shift(db: Session, user_id: int) -> Optional[CashierShift]:
    return db.query(CashierShift).filter(
        CashierShift.user_id == user_id,
        CashierShift.status == "open"
    ).first()

def open_shift(db: Session, user_id: int, req: ShiftOpenRequest) -> CashierShift:
    existing = get_active_shift(db, user_id)
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Shift kasir #{existing.id} masih terbuka. Tutup shift sebelumnya sebelum membuka shift baru."
        )
    
    shift = CashierShift(
        user_id=user_id,
        starting_cash=req.starting_cash,
        ending_cash_expected=req.starting_cash,
        status="open",
        note=req.note
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift

def close_shift(db: Session, shift_id: int, user_id: int, req: ShiftCloseRequest) -> CashierShift:
    shift = db.query(CashierShift).filter(CashierShift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift tidak ditemukan.")
    if shift.status == "closed":
        raise HTTPException(status_code=400, detail="Shift ini sudah ditutup sebelumnya.")
    
    # Calculate expected cash
    shift.ending_cash_expected = shift.starting_cash + shift.total_sales_cash - shift.total_refunds
    shift.ending_cash_actual = req.ending_cash_actual
    shift.cash_difference = shift.ending_cash_actual - shift.ending_cash_expected
    shift.end_time = datetime.now(timezone.utc)
    shift.status = "closed"
    if req.note:
        shift.note = f"{shift.note + ' | ' if shift.note else ''}Catatan Tutup: {req.note}"
        
    db.commit()
    db.refresh(shift)
    return shift

def get_shifts_history(db: Session, limit: int = 50) -> List[ShiftOut]:
    shifts = db.query(CashierShift).options(
        joinedload(CashierShift.user)
    ).order_by(CashierShift.id.desc()).limit(limit).all()
    
    output = []
    for s in shifts:
        out = ShiftOut.model_validate(s)
        out.cashier_name = s.user.full_name if s.user else "Kasir"
        output.append(out)
    return output
