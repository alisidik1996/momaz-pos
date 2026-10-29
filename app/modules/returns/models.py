from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base

class ReturnOrder(Base):
    __tablename__ = "return_orders"
    
    id = Column(Integer, primary_key=True, index=True)
    return_number = Column(String(50), unique=True, index=True, nullable=False)
    order_id = Column(Integer, ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    cashier_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    reason = Column(String(50), default="defect") # 'defect', 'change_mind', 'other'
    total_refund_amount = Column(Float, default=0.0)
    additional_charge = Column(Float, default=0.0)
    exchange_product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    exchange_variant_id = Column(Integer, ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True)
    
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    
    order = relationship("SalesOrder", back_populates="returns")
    cashier = relationship("User")
    exchange_product = relationship("Product")
    exchange_variant = relationship("ProductVariant")
    items = relationship("ReturnOrderItem", back_populates="return_order", cascade="all, delete-orphan")

class ReturnOrderItem(Base):
    __tablename__ = "return_order_items"
    
    id = Column(Integer, primary_key=True, index=True)
    return_id = Column(Integer, ForeignKey("return_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    variant_id = Column(Integer, ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True)
    quantity = Column(Integer, default=1)
    refund_subtotal = Column(Float, default=0.0)
    
    return_order = relationship("ReturnOrder", back_populates="items")
    product = relationship("Product")
    variant = relationship("ProductVariant")
