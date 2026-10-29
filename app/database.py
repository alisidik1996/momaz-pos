from pathlib import Path
from typing import Optional, Generator
import re
from fastapi import Request, HTTPException, Depends
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import settings

# Determine database dialect
is_postgres = bool(settings.MASTER_DATABASE_URL and settings.MASTER_DATABASE_URL.startswith("postgres"))

# 1. Master Database Setup
master_connect_args = {} if is_postgres else {"check_same_thread": False}
master_engine = create_engine(
    settings.MASTER_DATABASE_URL,
    connect_args=master_connect_args,
    pool_pre_ping=True,
    echo=False
)

if not is_postgres:
    @event.listens_for(master_engine, "connect")
    def set_master_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.close()

MasterSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=master_engine)
MasterBase = declarative_base()

def get_master_db() -> Generator[Session, None, None]:
    db = MasterSessionLocal()
    try:
        yield db
    finally:
        db.close()

# 2. Tenant Database Base & Manager
Base = declarative_base()

class TenantManager:
    _engines = {}
    _sessionmakers = {}

    @classmethod
    def get_db_path(cls, tenant_slug: str) -> Path:
        return settings.TENANTS_DIR / f"{tenant_slug}.db"

    @classmethod
    def get_engine(cls, tenant_slug: str):
        if tenant_slug not in cls._engines:
            if is_postgres:
                # In PostgreSQL (Neon.tech), isolate each tenant in its own schema
                schema_name = "tenant_" + re.sub(r"[^a-zA-Z0-9_]", "_", tenant_slug.lower())
                with master_engine.connect() as conn:
                    conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}";'))
                    conn.commit()

                engine = create_engine(
                    settings.DATABASE_URL,
                    connect_args={"options": f"-c search_path={schema_name},public"},
                    pool_pre_ping=True,
                    echo=False
                )
            else:
                db_path = cls.get_db_path(tenant_slug)
                engine = create_engine(
                    f"sqlite:///{db_path}",
                    connect_args={"check_same_thread": False},
                    echo=False
                )
                
                @event.listens_for(engine, "connect")
                def set_tenant_sqlite_pragma(dbapi_connection, connection_record):
                    cursor = dbapi_connection.cursor()
                    cursor.execute("PRAGMA foreign_keys=ON;")
                    cursor.execute("PRAGMA journal_mode=WAL;")
                    cursor.execute("PRAGMA synchronous=NORMAL;")
                    cursor.close()

            cls._engines[tenant_slug] = engine
            cls._sessionmakers[tenant_slug] = sessionmaker(
                autocommit=False, autoflush=False, bind=engine
            )
            cls._run_migrations(engine)
        return cls._engines[tenant_slug]

    @classmethod
    def get_session(cls, tenant_slug: str) -> Session:
        cls.get_engine(tenant_slug)
        return cls._sessionmakers[tenant_slug]()

    @classmethod
    def _run_migrations(cls, engine):
        if is_postgres:
            # On PostgreSQL, metadata.create_all creates all latest schema tables
            Base.metadata.create_all(bind=engine)
            return

        from sqlalchemy import inspect, text
        try:
            inspector = inspect(engine)
            existing_tables = inspector.get_table_names()
            
            with engine.connect() as conn:
                # 1. Products table
                if "products" in existing_tables:
                    prod_cols = [c["name"] for c in inspector.get_columns("products")]
                    if "cost_price" not in prod_cols:
                        conn.execute(text("ALTER TABLE products ADD COLUMN cost_price FLOAT DEFAULT 0.0;"))
                    if "stock" not in prod_cols:
                        conn.execute(text("ALTER TABLE products ADD COLUMN stock INTEGER DEFAULT 0;"))
                    if "min_stock" not in prod_cols:
                        conn.execute(text("ALTER TABLE products ADD COLUMN min_stock INTEGER DEFAULT 5;"))
                    if "member_discount_type" not in prod_cols:
                        conn.execute(text("ALTER TABLE products ADD COLUMN member_discount_type VARCHAR(20) DEFAULT 'percent';"))
                    if "member_discount_value" not in prod_cols:
                        conn.execute(text("ALTER TABLE products ADD COLUMN member_discount_value FLOAT DEFAULT 0.0;"))
                    if "affiliate_commission_type" not in prod_cols:
                        conn.execute(text("ALTER TABLE products ADD COLUMN affiliate_commission_type VARCHAR(20) DEFAULT 'percent';"))
                    if "affiliate_commission_value" not in prod_cols:
                        conn.execute(text("ALTER TABLE products ADD COLUMN affiliate_commission_value FLOAT DEFAULT 0.0;"))
                    
                    if "product_variants" in existing_tables:
                        try:
                            conn.execute(text("""
                                UPDATE products SET
                                    stock = COALESCE((SELECT SUM(stock) FROM product_variants WHERE product_variants.product_id = products.id), stock),
                                    cost_price = COALESCE((SELECT AVG(cost_price) FROM product_variants WHERE product_variants.product_id = products.id AND cost_price > 0), cost_price)
                                WHERE EXISTS (SELECT 1 FROM product_variants WHERE product_variants.product_id = products.id);
                            """))
                        except Exception:
                            pass
                    conn.commit()

                # 2. Sales order items
                if "sales_order_items" in existing_tables:
                    item_cols = {c["name"]: c for c in inspector.get_columns("sales_order_items")}
                    if "product_id" not in item_cols:
                        conn.execute(text("ALTER TABLE sales_order_items ADD COLUMN product_id INTEGER;"))
                        if "product_variants" in existing_tables:
                            try:
                                conn.execute(text("""
                                    UPDATE sales_order_items SET product_id = (SELECT product_id FROM product_variants WHERE product_variants.id = sales_order_items.variant_id)
                                    WHERE product_id IS NULL;
                                """))
                            except Exception:
                                pass
                        conn.commit()

                    # Drop NOT NULL constraint on variant_info if present
                    if "variant_info" in item_cols and not item_cols["variant_info"].get("nullable", True):
                        conn.execute(text("PRAGMA foreign_keys=OFF;"))
                        conn.execute(text("""
                            CREATE TABLE sales_order_items_new (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                order_id INTEGER NOT NULL,
                                product_id INTEGER,
                                variant_id INTEGER,
                                product_name VARCHAR(150) NOT NULL,
                                variant_info VARCHAR(100) DEFAULT '',
                                sku VARCHAR(50) NOT NULL,
                                barcode VARCHAR(50) NOT NULL,
                                cost_price FLOAT,
                                unit_price FLOAT,
                                quantity INTEGER,
                                discount_amount FLOAT,
                                subtotal FLOAT
                            );
                        """))
                        conn.execute(text("""
                            INSERT INTO sales_order_items_new (id, order_id, product_id, variant_id, product_name, variant_info, sku, barcode, cost_price, unit_price, quantity, discount_amount, subtotal)
                            SELECT id, order_id, product_id, variant_id, product_name, COALESCE(variant_info, ''), sku, barcode, cost_price, unit_price, quantity, discount_amount, subtotal FROM sales_order_items;
                        """))
                        conn.execute(text("DROP TABLE sales_order_items;"))
                        conn.execute(text("ALTER TABLE sales_order_items_new RENAME TO sales_order_items;"))
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sales_order_items_id ON sales_order_items (id);"))
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sales_order_items_order_id ON sales_order_items (order_id);"))
                        conn.execute(text("PRAGMA foreign_keys=ON;"))
                        conn.commit()

                # 3. Stock movements
                if "stock_movements" in existing_tables:
                    mov_cols = {c["name"]: c for c in inspector.get_columns("stock_movements")}
                    if "product_id" not in mov_cols:
                        conn.execute(text("ALTER TABLE stock_movements ADD COLUMN product_id INTEGER;"))
                        if "product_variants" in existing_tables:
                            try:
                                conn.execute(text("""
                                    UPDATE stock_movements SET product_id = (SELECT product_id FROM product_variants WHERE product_variants.id = stock_movements.variant_id)
                                    WHERE product_id IS NULL;
                                """))
                            except Exception:
                                pass
                        conn.commit()

                    # Drop NOT NULL constraint on variant_id if present
                    if "variant_id" in mov_cols and not mov_cols["variant_id"].get("nullable", True):
                        conn.execute(text("PRAGMA foreign_keys=OFF;"))
                        conn.execute(text("""
                            CREATE TABLE stock_movements_new (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                product_id INTEGER,
                                variant_id INTEGER,
                                user_id INTEGER,
                                change_qty INTEGER NOT NULL,
                                current_stock INTEGER NOT NULL,
                                movement_type VARCHAR(30) NOT NULL,
                                reference VARCHAR(100),
                                note TEXT,
                                created_at DATETIME
                            );
                        """))
                        conn.execute(text("""
                            INSERT INTO stock_movements_new (id, product_id, variant_id, user_id, change_qty, current_stock, movement_type, reference, note, created_at)
                            SELECT id, product_id, variant_id, user_id, change_qty, current_stock, movement_type, reference, note, created_at FROM stock_movements;
                        """))
                        conn.execute(text("DROP TABLE stock_movements;"))
                        conn.execute(text("ALTER TABLE stock_movements_new RENAME TO stock_movements;"))
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_stock_movements_id ON stock_movements (id);"))
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_stock_movements_product_id ON stock_movements (product_id);"))
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_stock_movements_variant_id ON stock_movements (variant_id);"))
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_stock_movements_created_at ON stock_movements (created_at);"))
                        conn.execute(text("PRAGMA foreign_keys=ON;"))
                        conn.commit()

                # 4. Return order items
                if "return_order_items" in existing_tables:
                    ret_cols = [c["name"] for c in inspector.get_columns("return_order_items")]
                    if "product_id" not in ret_cols:
                        conn.execute(text("ALTER TABLE return_order_items ADD COLUMN product_id INTEGER;"))
                        conn.commit()

                # 5. Return orders
                if "return_orders" in existing_tables:
                    ro_cols = [c["name"] for c in inspector.get_columns("return_orders")]
                    if "exchange_product_id" not in ro_cols:
                        conn.execute(text("ALTER TABLE return_orders ADD COLUMN exchange_product_id INTEGER;"))
                        conn.commit()

                # 6. Customers & Member Affiliate
                if "customers" in existing_tables:
                    cust_cols = [c["name"] for c in inspector.get_columns("customers")]
                    if "member_id" not in cust_cols:
                        conn.execute(text("ALTER TABLE customers ADD COLUMN member_id VARCHAR(30);"))
                    if "total_commission" not in cust_cols:
                        conn.execute(text("ALTER TABLE customers ADD COLUMN total_commission FLOAT DEFAULT 0.0;"))
                    conn.commit()

                    # Auto-assign 12-digit random alphanumeric member_id for existing customers without member_id
                    try:
                        import random
                        chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
                        rows = conn.execute(text("SELECT id FROM customers WHERE member_id IS NULL OR member_id = '';")).fetchall()
                        for r in rows:
                            gen_id = "".join(random.choices(chars, k=12))
                            conn.execute(text("UPDATE customers SET member_id = :mid WHERE id = :cid;"), {"mid": gen_id, "cid": r[0]})
                        conn.commit()
                    except Exception:
                        pass

                # 7. Affiliate Commissions table
                if "affiliate_commissions" not in existing_tables:
                    conn.execute(text("""
                        CREATE TABLE affiliate_commissions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            customer_id INTEGER NOT NULL,
                            order_id INTEGER,
                            amount FLOAT NOT NULL DEFAULT 0.0,
                            notes VARCHAR(255),
                            created_at DATETIME,
                            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
                            FOREIGN KEY (order_id) REFERENCES sales_orders(id) ON DELETE SET NULL
                        );
                    """))
                    conn.commit()
        except Exception as e:
            # Table might not exist yet during initial create
            pass

    @classmethod
    def init_tenant_db(cls, tenant_slug: str):
        """Creates all tenant tables in tenants/{tenant_slug}.db"""
        engine = cls.get_engine(tenant_slug)
        Base.metadata.create_all(bind=engine)
        cls._run_migrations(engine)

    @classmethod
    def close_tenant(cls, tenant_slug: str):
        """Disposes connections and clears sessionmaker for a tenant"""
        if tenant_slug in cls._engines:
            cls._engines[tenant_slug].dispose()
            cls._engines.pop(tenant_slug, None)
            cls._sessionmakers.pop(tenant_slug, None)

def extract_token_from_string(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    import urllib.parse
    cleaned = urllib.parse.unquote(str(raw).strip()).strip('"').strip("'")
    while cleaned.lower().startswith("bearer "):
        cleaned = cleaned[7:].strip().strip('"').strip("'")
    return cleaned if cleaned else None

def get_tenant_slug_from_request(request: Request) -> Optional[str]:
    # 1. From explicit header
    slug = request.headers.get("X-Tenant-Slug")
    if slug:
        return slug

    # 2. Extract JWT token from Authorization header first, then fallback to cookie
    token = extract_token_from_string(request.headers.get("Authorization"))
    if not token:
        token = extract_token_from_string(request.cookies.get("access_token"))

    if token:
        from app.core.security import decode_access_token
        payload = decode_access_token(token)
        if payload:
            if payload.get("tenant_slug"):
                return payload.get("tenant_slug")
            
            # Lookup tenant from master.db if user is logged in but token lacks slug
            try:
                from app.modules.tenants.models import MasterUser, Tenant
                db = MasterSessionLocal()
                try:
                    user_id = payload.get("id")
                    username = payload.get("sub")
                    m_user = None
                    if user_id:
                        m_user = db.query(MasterUser).filter(MasterUser.id == user_id).first()
                    elif username:
                        m_user = db.query(MasterUser).filter(MasterUser.username == username).first()
                    
                    if m_user and m_user.tenant_id:
                        t = db.query(Tenant).filter(Tenant.id == m_user.tenant_id).first()
                        if t and t.slug:
                            return t.slug
                finally:
                    db.close()
            except Exception:
                pass

    # 3. Graceful fallback: If only 1 tenant is registered in master.db, use it
    try:
        from app.modules.tenants.models import Tenant
        db = MasterSessionLocal()
        try:
            active_tenants = db.query(Tenant).filter(Tenant.is_active == True).all()
            if len(active_tenants) == 1:
                return active_tenants[0].slug
        finally:
            db.close()
    except Exception:
        pass

    return None

def get_db(request: Request) -> Generator[Session, None, None]:
    """Dependency injecting tenant database session based on request user's tenant"""
    tenant_slug = get_tenant_slug_from_request(request)
    if not tenant_slug:
        # Fallback or check if single default tenant exists
        # In test environments or when no tenant is resolved, handle gracefully
        raise HTTPException(
            status_code=400,
            detail="Konteks toko (Tenant) tidak ditemukan. Silakan login atau pilih toko."
        )

    db = TenantManager.get_session(tenant_slug)
    try:
        yield db
    finally:
        db.close()
