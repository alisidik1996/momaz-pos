from sqlalchemy import Column, Integer, String, Float, Boolean, Text, DateTime
from datetime import datetime, timezone
from app.database import Base

class StoreSettings(Base):
    __tablename__ = "store_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    store_name = Column(String(100), default="MOMAZ APPAREL STORE")
    tagline = Column(String(150), default="Casual & Formal Fashion Distro")
    address = Column(Text, default="Jl. Pemuda No. 45, Jakarta")
    phone = Column(String(30), default="0812-3456-7890")
    email = Column(String(100), default="hello@momazapparel.com")
    receipt_footer = Column(Text, default="Terima kasih atas kunjungan Anda!\nBarang yang sudah dibeli dapat ditukar maksimal 3 hari setelah pembelian dengan membawa struk ini & tag utuh.")
    return_policy_days = Column(Integer, default=3)
    tax_rate = Column(Float, default=11.0) # 11% PPN
    is_tax_enabled = Column(Boolean, default=False)
    currency_symbol = Column(String(10), default="Rp")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
