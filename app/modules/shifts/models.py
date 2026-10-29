from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base

class CashierShift(Base):
    __tablename__ = "shifts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    start_time = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    end_time = Column(DateTime, nullable=True)
    
    starting_cash = Column(Float, default=0.0)          # Modal awal di laci kasir
    total_sales_cash = Column(Float, default=0.0)       # Penjualan Tunai
    total_sales_non_cash = Column(Float, default=0.0)   # Penjualan QRIS/Kartu
    total_refunds = Column(Float, default=0.0)          # Pengembalian dana tunai
    
    ending_cash_expected = Column(Float, default=0.0)   # Kas seharusnya (Modal + Tunai - Refund)
    ending_cash_actual = Column(Float, nullable=True)   # Kas fisik aktual yang dihitung kasir
    cash_difference = Column(Float, default=0.0)        # Selisih (Actual - Expected)
    
    status = Column(String(20), default="open", index=True) # 'open', 'closed'
    note = Column(Text, nullable=True)
    
    user = relationship("User")
    orders = relationship("SalesOrder", back_populates="shift")
