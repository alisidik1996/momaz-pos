from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.modules.auth.service import get_current_user
from app.modules.auth.models import User
from app.modules.sales.schemas import (
    CheckoutRequest, SalesOrderOut, ReceiptOut
)
from app.modules.sales import service

router = APIRouter(prefix="/api/sales", tags=["POS Sales & Orders"])

@router.post("/checkout", response_model=SalesOrderOut)
def checkout(
    req: CheckoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    order = service.process_checkout(db, req, cashier_id=current_user.id)
    out = SalesOrderOut.model_validate(order)
    out.cashier_name = current_user.full_name
    if order.customer:
        out.customer_name = order.customer.name
    return out

@router.get("/orders", response_model=List[SalesOrderOut])
def get_orders(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    return service.get_recent_orders(db, limit=limit)

@router.get("/orders/{order_id}", response_model=SalesOrderOut)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    order = service.get_order_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order tidak ditemukan.")
    out = SalesOrderOut.model_validate(order)
    out.cashier_name = order.cashier.full_name if order.cashier else "Kasir"
    out.customer_name = order.customer.name if order.customer else "Umum"
    return out

@router.get("/orders/{order_id}/receipt", response_model=ReceiptOut)
def get_receipt(
    order_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    order = service.get_order_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order tidak ditemukan.")
    return service.build_receipt_data(db, order)
