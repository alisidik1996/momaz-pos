import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.core.security import hash_password
from app.core.models import StoreSettings
from app.modules.auth.models import User
from app.modules.catalog.models import Category, Brand, Product, ProductVariant

TEST_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(scope="function")
def db_session():
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    
    session = TestingSessionLocal()
    
    # Seed default user and store settings for testing
    admin = User(
        username="admin_test",
        password_hash=hash_password("admin123"),
        full_name="Admin Test",
        role="admin"
    )
    cashier = User(
        username="cashier_test",
        password_hash=hash_password("cashier123"),
        full_name="Cashier Test",
        role="cashier"
    )
    settings = StoreSettings(store_name="Test Fashion Store", return_policy_days=7)
    session.add_all([admin, cashier, settings])
    session.commit()
    
    yield session
    
    session.close()
    Base.metadata.drop_all(bind=engine)
