import random
import string
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.modules.customers.models import Customer, AffiliateCommission
from app.modules.customers.schemas import CustomerCreate, CustomerUpdate

def generate_random_member_id(db: Session, length: int = 12) -> str:
    """Generate a unique 12-digit alphanumeric uppercase member ID"""
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789" # Omit confusing O, 0, I, 1
    for _ in range(50):
        code = "".join(random.choices(chars, k=length))
        if not db.query(Customer).filter(Customer.member_id == code).first():
            return code
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))

def get_customers(db: Session, query: Optional[str] = None) -> List[Customer]:
    stmt = db.query(Customer)
    if query:
        stmt = stmt.filter(
            (Customer.name.ilike(f"%{query}%")) |
            (Customer.phone.ilike(f"%{query}%")) |
            (Customer.member_id.ilike(f"%{query}%"))
        )
    return stmt.order_by(Customer.id.desc()).all()

def get_customer_by_id(db: Session, customer_id: int) -> Optional[Customer]:
    return db.query(Customer).filter(Customer.id == customer_id).first()

def get_customer_by_code(db: Session, code: str) -> Optional[Customer]:
    """Lookup by member_id or phone number"""
    clean_code = code.strip().upper()
    cust = db.query(Customer).filter(Customer.member_id == clean_code).first()
    if not cust:
        cust = db.query(Customer).filter(Customer.phone == code.strip()).first()
    return cust

def create_customer(db: Session, cust_in: CustomerCreate) -> Customer:
    if cust_in.phone:
        existing = db.query(Customer).filter(Customer.phone == cust_in.phone).first()
        if existing:
            # If existing customer has no member_id, generate one
            if not existing.member_id:
                existing.member_id = generate_random_member_id(db)
                db.commit()
                db.refresh(existing)
            return existing

    member_id = cust_in.member_id.strip().upper() if cust_in.member_id else generate_random_member_id(db)

    # Check member_id uniqueness
    if db.query(Customer).filter(Customer.member_id == member_id).first():
        member_id = generate_random_member_id(db)
            
    customer = Customer(
        member_id=member_id,
        name=cust_in.name,
        phone=cust_in.phone,
        email=cust_in.email,
        address=cust_in.address,
        total_commission=0.0
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer

def update_customer(db: Session, customer_id: int, cust_in: CustomerUpdate) -> Customer:
    customer = get_customer_by_id(db, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Pelanggan tidak ditemukan.")
        
    for k, v in cust_in.model_dump(exclude_unset=True).items():
        if k == "member_id" and v:
            v = v.strip().upper()
        setattr(customer, k, v)
        
    db.commit()
    db.refresh(customer)
    return customer

def get_affiliate_commissions(db: Session, customer_id: Optional[int] = None) -> List[AffiliateCommission]:
    query = db.query(AffiliateCommission)
    if customer_id:
        query = query.filter(AffiliateCommission.customer_id == customer_id)
    return query.order_by(AffiliateCommission.id.desc()).all()

def delete_customer(db: Session, customer_id: int):
    customer = get_customer_by_id(db, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Member / Pelanggan tidak ditemukan.")

    # Detach from sales orders to preserve sales transactions
    from app.modules.sales.models import SalesOrder
    db.query(SalesOrder).filter(SalesOrder.customer_id == customer_id).update({"customer_id": None})
    
    # Remove associated commission records
    db.query(AffiliateCommission).filter(AffiliateCommission.customer_id == customer_id).delete()

    db.delete(customer)
    db.commit()
    return {"message": f"Member '{customer.name}' berhasil dihapus."}
