from sqlalchemy import create_engine, inspect

from app import seed


def test_seed_initializes_the_master_registry_without_sample_users(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'seed.db'}")
    monkeypatch.setattr(seed, "master_engine", engine)
    monkeypatch.setattr(seed, "is_postgres", False)
    try:
        seed.seed_database()
        assert {"tenants", "master_users"} <= set(inspect(engine).get_table_names())
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM master_users").scalar() == 0
    finally:
        engine.dispose()
