from sqlalchemy import Column, Integer, String, Float, Boolean, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base

class Category(Base):
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    slug = Column(String(100), unique=True, index=True)
    description = Column(Text, nullable=True)
    
    products = relationship("Product", back_populates="category")

class Brand(Base):
    __tablename__ = "brands"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    
    products = relationship("Product", back_populates="brand")

class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    brand_id = Column(Integer, ForeignKey("brands.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(150), nullable=False, index=True)
    sku = Column(String(50), nullable=True, index=True)
    barcode = Column(String(50), nullable=True, index=True)
    description = Column(Text, nullable=True)
    cost_price = Column(Float, default=0.0)
    base_price = Column(Float, default=0.0)
    discount_price = Column(Float, default=0.0, nullable=True)
    stock = Column(Integer, default=0)
    min_stock = Column(Integer, default=5)
    image_url = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    member_discount_type = Column(String(20), default="percent")       # 'percent' or 'nominal'
    member_discount_value = Column(Float, default=0.0)
    affiliate_commission_type = Column(String(20), default="percent")  # 'percent' or 'nominal'
    affiliate_commission_value = Column(Float, default=0.0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    category = relationship("Category", back_populates="products")
    brand = relationship("Brand", back_populates="products")
    variants = relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan")

class ProductVariant(Base):
    __tablename__ = "product_variants"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    sku = Column(String(50), unique=True, index=True, nullable=False)
    barcode = Column(String(50), unique=True, index=True, nullable=False)
    size = Column(String(30), nullable=False)    # e.g., 'S', 'M', 'L', 'XL', 'XXL', '28', '30'
    color = Column(String(50), nullable=False)   # e.g., 'Hitam', 'Putih', 'Navy', 'Maroon'
    cost_price = Column(Float, default=0.0)      # HPP / Harga Beli Modal
    sell_price = Column(Float, default=0.0)      # Harga Jual Kasir
    stock = Column(Integer, default=0)           # Jumlah stok fisik
    min_stock = Column(Integer, default=5)       # Peringatan stok menipis
    is_active = Column(Boolean, default=True)
    
    product = relationship("Product", back_populates="variants")
