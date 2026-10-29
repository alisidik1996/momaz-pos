from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.modules.auth.service import get_current_user
from app.modules.auth.models import User
from app.modules.customers.schemas import CustomerCreate, CustomerUpdate, CustomerOut, AffiliateCommissionOut
from app.modules.customers import service

router = APIRouter(prefix="/api/customers", tags=["Customers, Members & Affiliate"])

@router.get("/generate-member-id")
def get_random_member_id(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return {"member_id": service.generate_random_member_id(db)}

@router.get("/by-code/{code}", response_model=CustomerOut)
def get_customer_by_code(code: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    cust = service.get_customer_by_code(db, code)
    if not cust:
        raise HTTPException(status_code=404, detail="Member / Pelanggan dengan ID atau No. HP tersebut tidak ditemukan.")
    return cust

@router.get("/commissions", response_model=List[AffiliateCommissionOut])
def get_commissions(
    customer_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    commissions = service.get_affiliate_commissions(db, customer_id=customer_id)
    out = []
    for c in commissions:
        item = AffiliateCommissionOut.model_validate(c)
        item.customer_name = c.customer.name if c.customer else "Member"
        out.append(item)
    return out

@router.get("", response_model=List[CustomerOut])
def list_customers(
    q: Optional[str] = Query(None, description="Cari nama, ID member, atau telepon"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    return service.get_customers(db, query=q)

@router.post("", response_model=CustomerOut)
def create_customer(
    cust_in: CustomerCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    return service.create_customer(db, cust_in)

@router.put("/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: int,
    cust_in: CustomerUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    return service.update_customer(db, customer_id, cust_in)

@router.delete("/{customer_id}")
def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    return service.delete_customer(db, customer_id)
