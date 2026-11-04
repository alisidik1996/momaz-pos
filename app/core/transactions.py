"""Serialize tenant mutations and roll back failed service operations."""
from datetime import datetime, timezone
from functools import wraps

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session


def lock_database_for_write(db: Session):
    bind = db.get_bind()
    if bind.dialect.name == "sqlite":
        connection = db.connection()
        # sqlite3's legacy transaction mode does not start a transaction for
        # SELECTs. Acquire the writer lock before reading stock or sequences.
        raw_connection = connection.connection.driver_connection
        if not raw_connection.in_transaction:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
    elif bind.dialect.name == "postgresql":
        schema = bind.get_execution_options().get("schema_translate_map", {}).get(None, "public")
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:scope))"),
            {"scope": f"momaz-pos-write:{schema}"},
        )


def transactional(function):
    """Services own their commits; failures always roll back the whole mutation."""
    @wraps(function)
    def wrapped(db: Session, *args, **kwargs):
        try:
            lock_database_for_write(db)
            return function(db, *args, **kwargs)
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail="Data duplikat atau referensi data tidak valid.") from exc
        except OperationalError as exc:
            db.rollback()
            raise HTTPException(status_code=503, detail="Database sedang sibuk atau tidak tersedia. Silakan coba kembali.") from exc
        except Exception:
            db.rollback()
            raise

    return wrapped


def generate_document_number(db: Session, column, prefix: str) -> str:
    lock_database_for_write(db)
    date_prefix = f"{prefix}-{datetime.now(timezone.utc):%Y%m%d}-"
    numbers = db.query(column).filter(column.like(f"{date_prefix}%")).all()
    sequence = max(
        (int(value[len(date_prefix):]) for (value,) in numbers if value[len(date_prefix):].isdigit()),
        default=0,
    ) + 1
    return f"{date_prefix}{sequence:04d}"
