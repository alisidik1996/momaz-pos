from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.modules.auth.service import get_current_user
from app.modules.auth.models import User
from app.modules.returns.schemas import ReturnCreateRequest, ReturnOrderOut
from app.modules.returns import service

router = APIRouter(prefix="/api/returns", tags=["Returns & Exchanges"])

@router.post("", response_model=ReturnOrderOut)
def create_return(
    req: ReturnCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ret = service.process_return_exchange(db, req, cashier_id=current_user.id)
    history = service.get_return_orders(db, limit=1)
    return history[0]

@router.get("", response_model=List[ReturnOrderOut])
def list_returns(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    return service.get_return_orders(db, limit=limit)
