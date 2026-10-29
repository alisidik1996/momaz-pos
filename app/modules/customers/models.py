from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base

class Customer(Base):
    __tablename__ = "customers"
    
    id = Column(Integer, primary_key=True, index=True)
    member_id = Column(String(30), unique=True, index=True, nullable=True) # 12-digit random alphanumeric
    name = Column(String(100), nullable=False, index=True)
    phone = Column(String(30), unique=True, index=True, nullable=True)
    email = Column(String(100), nullable=True)
    address = Column(Text, nullable=True)
    total_spend = Column(Float, default=0.0)
    total_commission = Column(Float, default=0.0)
    visit_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    commissions = relationship("AffiliateCommission", back_populates="customer", cascade="all, delete-orphan")

class AffiliateCommission(Base):
    __tablename__ = "affiliate_commissions"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("sales_orders.id", ondelete="SET NULL"), nullable=True)
    amount = Column(Float, nullable=False, default=0.0)
    notes = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    customer = relationship("Customer", back_populates="commissions")
    order = relationship("SalesOrder")
