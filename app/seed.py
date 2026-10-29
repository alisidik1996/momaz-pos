from app.database import engine, Base
# Import all models so metadata knows all tables
import app.core.models
import app.modules.auth.models
import app.modules.catalog.models
import app.modules.inventory.models
import app.modules.customers.models
import app.modules.shifts.models
import app.modules.sales.models
import app.modules.returns.models

def seed_database():
    """Ensure database schema and tables exist in SQLite without injecting mock data."""
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    seed_database()
    print("[OK] Database schema initialized (no mock seeds). Ready for Setup Wizard.")
