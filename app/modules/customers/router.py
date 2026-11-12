from fastapi import APIRouter, Depends, Query, HTTPException, Response, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db, MasterSessionLocal, TenantManager
from app.modules.auth.service import get_current_user
from app.modules.auth.models import User
from app.modules.tenants.models import Tenant
from app.modules.customers.schemas import CustomerCreate, CustomerUpdate, CustomerOut, AffiliateCommissionOut
from app.modules.customers import service
from app.modules.sales.models import SalesOrder

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

# Public endpoint for member portal (no auth required)
@router.get("/portal/lookup")
def member_portal_lookup(
    request: Request,
    code: str = Query(..., description="Member ID or phone number")
):
    """Public endpoint for member to check points and purchase history"""
    clean_code = code.strip().upper()

    # Determine tenant session:
    # 1. From request token/cookie if present
    # 2. Or from X-Tenant-Slug header / query param tenant
    # 3. Or search active tenants in master registry
    db = None
    close_db = False

    tenant_slug = request.headers.get("X-Tenant-Slug") or request.query_params.get("tenant")
    if not tenant_slug:
        try:
            from app.database import get_request_identity
            identity = get_request_identity(request)
            tenant_slug = identity.get("tenant_slug")
        except HTTPException:
            tenant_slug = None

    if tenant_slug:
        db = TenantManager.get_session(tenant_slug)
        close_db = True
        cust = service.get_customer_by_code(db, clean_code)
    else:
        # Search all active tenants for customer code
        with MasterSessionLocal() as master_db:
            active_tenants = master_db.query(Tenant).filter(Tenant.is_active == True).all()

        cust = None
        for t in active_tenants:
            t_session = TenantManager.get_session(t.slug)
            try:
                found = service.get_customer_by_code(t_session, clean_code)
                if found:
                    cust = found
                    db = t_session
                    close_db = True
                    break
            finally:
                if not cust:
                    t_session.close()

    if not db or not cust:
        if db and close_db:
            db.close()
        raise HTTPException(status_code=404, detail="Member tidak ditemukan.")

    try:
        # Get purchase history (completed orders only)
        orders = db.query(SalesOrder).filter(
            SalesOrder.customer_id == cust.id,
            SalesOrder.status == "completed"
        ).order_by(SalesOrder.created_at.desc()).limit(50).all()

        order_history = []
        for o in orders:
            order_history.append({
                "invoice_number": o.invoice_number,
                "date": o.created_at.isoformat() if o.created_at else None,
                "total_amount": o.total_amount,
                "payment_method": o.payment_method,
                "items_count": len(o.items) if o.items else 0
            })

        return {
            "member": {
                "id": cust.id,
                "member_id": cust.member_id,
                "name": cust.name,
                "phone": cust.phone,
                "total_spend": cust.total_spend or 0.0,
                "total_commission": cust.total_commission or 0.0
            },
            "history": order_history
        }
    finally:
        if close_db and db:
            db.close()

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
