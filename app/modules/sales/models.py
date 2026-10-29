from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base

class SalesOrder(Base):
    __tablename__ = "sales_orders"
    
    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String(50), unique=True, index=True, nullable=False)
    shift_id = Column(Integer, ForeignKey("shifts.id", ondelete="SET NULL"), nullable=True, index=True)
    cashier_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    
    subtotal = Column(Float, default=0.0)
    discount_amount = Column(Float, default=0.0)
    tax_amount = Column(Float, default=0.0)
    total_amount = Column(Float, default=0.0)
    
    payment_method = Column(String(30), default="cash") # 'cash', 'qris', 'card', 'split'
    amount_paid = Column(Float, default=0.0)
    change_amount = Column(Float, default=0.0)
    
    status = Column(String(20), default="completed", index=True) # 'completed', 'cancelled', 'refunded'
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    
    cashier = relationship("User")
    customer = relationship("Customer")
    shift = relationship("CashierShift", back_populates="orders")
    items = relationship("SalesOrderItem", back_populates="order", cascade="all, delete-orphan")
    returns = relationship("ReturnOrder", back_populates="order")

class SalesOrderItem(Base):
    __tablename__ = "sales_order_items"
    
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    variant_id = Column(Integer, ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True)
    
    product_name = Column(String(150), nullable=False)
    variant_info = Column(String(100), default="", nullable=True) # optional / empty
    sku = Column(String(50), nullable=False)
    barcode = Column(String(50), nullable=False)
    
    cost_price = Column(Float, default=0.0)
    unit_price = Column(Float, default=0.0)
    quantity = Column(Integer, default=1)
    discount_amount = Column(Float, default=0.0)
    subtotal = Column(Float, default=0.0) # (unit_price * qty) - discount_amount
    
    order = relationship("SalesOrder", back_populates="items")
    product = relationship("Product")
    variant = relationship("ProductVariant")
