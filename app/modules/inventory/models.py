from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base

class StockMovement(Base):
    __tablename__ = "stock_movements"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=True, index=True)
    variant_id = Column(Integer, ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    change_qty = Column(Integer, nullable=False) # e.g. +10 or -2
    current_stock = Column(Integer, nullable=False) # stock after change
    movement_type = Column(String(30), nullable=False) # 'sale', 'return', 'restock', 'adjustment'
    reference = Column(String(100), nullable=True) # e.g. 'INV-20261027-001'
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    
    product = relationship("Product")
    variant = relationship("ProductVariant")
    user = relationship("User")
