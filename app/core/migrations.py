"""Idempotent legacy tenant migrations, always scoped to the tenant schema."""
import secrets

from sqlalchemy import MetaData, inspect, text


def _table_name(name, schema=None):
    return f'"{schema}"."{name}"' if schema else f'"{name}"'


def _add_legacy_columns(connection, schema=None):
    inspector = inspect(connection)
    tables = set(inspector.get_table_names(schema=schema))
    old_columns = {table: {column["name"]: column for column in inspector.get_columns(table, schema=schema)} for table in tables}
    products = _table_name("products", schema)
    variants = _table_name("product_variants", schema)
    additions = {
        "products": {
            "cost_price": "FLOAT DEFAULT 0.0", "stock": "INTEGER DEFAULT 0", "min_stock": "INTEGER DEFAULT 5",
            "member_discount_type": "VARCHAR(20) DEFAULT 'percent'", "member_discount_value": "FLOAT DEFAULT 0.0",
            "affiliate_commission_type": "VARCHAR(20) DEFAULT 'percent'", "affiliate_commission_value": "FLOAT DEFAULT 0.0",
        },
        "sales_order_items": {
            "product_id": f"INTEGER REFERENCES {products}(id) ON DELETE SET NULL",
            # NULL preserves the distinction between legacy invoices and new
            # per-item commission snapshots; no historical rates are invented.
            "affiliate_commission_amount": "FLOAT",
        },
        "stock_movements": {"product_id": f"INTEGER REFERENCES {products}(id) ON DELETE CASCADE"},
        "return_order_items": {"product_id": f"INTEGER REFERENCES {products}(id) ON DELETE SET NULL"},
        "return_orders": {"exchange_product_id": f"INTEGER REFERENCES {products}(id) ON DELETE SET NULL"},
        "customers": {"member_id": "VARCHAR(30)", "total_commission": "FLOAT DEFAULT 0.0"},
    }
    for table, columns in additions.items():
        if table not in tables:
            continue
        table_name = _table_name(table, schema)
        for column, definition in columns.items():
            if column not in old_columns[table]:
                connection.execute(text(f'ALTER TABLE {table_name} ADD COLUMN "{column}" {definition}'))

    # Product stock and variant stock are independent. Do not copy variant
    # quantities into products, which would make total_stock count them twice.
    if "products" in tables and "product_variants" in tables and "cost_price" not in old_columns["products"]:
        if {"product_id", "cost_price"} <= old_columns["product_variants"].keys():
            connection.execute(text(f"""
                UPDATE {products} SET cost_price = COALESCE(
                    (SELECT AVG(cost_price) FROM {variants}
                     WHERE {variants}.product_id = {products}.id AND cost_price > 0), 0.0)
            """))
    if "product_variants" in tables:
        for table in ("sales_order_items", "stock_movements", "return_order_items"):
            if table in tables and "product_id" not in old_columns[table] and "variant_id" in old_columns[table]:
                table_name = _table_name(table, schema)
                connection.execute(text(f"""
                    UPDATE {table_name} SET product_id =
                        (SELECT product_id FROM {variants} WHERE {variants}.id = {table_name}.variant_id)
                    WHERE product_id IS NULL
                """))
    if "customers" in tables:
        customers = _table_name("customers", schema)
        used = {row[0] for row in connection.execute(text(f"SELECT member_id FROM {customers} WHERE member_id IS NOT NULL"))}
        missing = connection.execute(text(f"SELECT id FROM {customers} WHERE member_id IS NULL OR member_id = ''")).all()
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        for (customer_id,) in missing:
            for _ in range(100):
                member_id = "".join(secrets.choice(alphabet) for _ in range(12))
                if member_id not in used:
                    break
            else:
                raise RuntimeError("Gagal membuat ID member unik.")
            used.add(member_id)
            connection.execute(text(f"UPDATE {customers} SET member_id = :member_id WHERE id = :id"), {"member_id": member_id, "id": customer_id})
        connection.execute(text(f'CREATE UNIQUE INDEX IF NOT EXISTS "ix_customers_member_id" ON {customers} (member_id)'))
    return old_columns


def _rebuild_sqlite_table(connection, table_name):
    from app.database import Base

    original = Base.metadata.tables[table_name]
    metadata = MetaData()
    for table in Base.metadata.tables.values():
        if table.name != table_name:
            table.to_metadata(metadata)
    temporary_name = f"{table_name}__migrating"
    replacement = original.to_metadata(metadata, name=temporary_name)
    columns = {column["name"] for column in inspect(connection).get_columns(table_name)}
    copy_columns = [column.name for column in replacement.columns if column.name in columns]
    destination = ", ".join(f'"{column}"' for column in copy_columns)
    source = ", ".join("COALESCE(variant_info, '')" if column == "variant_info" else f'"{column}"' for column in copy_columns)
    foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
    connection.commit()
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    connection.commit()
    try:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        replacement.create(connection)
        connection.exec_driver_sql(f'INSERT INTO "{temporary_name}" ({destination}) SELECT {source} FROM "{table_name}"')
        connection.exec_driver_sql(f'DROP TABLE "{table_name}"')
        connection.exec_driver_sql(f'ALTER TABLE "{temporary_name}" RENAME TO "{table_name}"')
        for index in original.indexes:
            index.create(connection)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.exec_driver_sql(f"PRAGMA foreign_keys={'ON' if foreign_keys else 'OFF'}")
        connection.commit()


def migrate_tenant_schema(bind):
    if bind.dialect.name == "postgresql":
        schema = bind.get_execution_options()["schema_translate_map"][None]
        old_columns = _add_legacy_columns(bind, schema)
        for table, column in (("sales_order_items", "variant_info"), ("stock_movements", "variant_id")):
            definition = old_columns.get(table, {}).get(column)
            if definition and not definition.get("nullable", True):
                bind.execute(text(f'ALTER TABLE {_table_name(table, schema)} ALTER COLUMN "{column}" DROP NOT NULL'))
        return

    with bind.connect() as connection:
        try:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            old_columns = _add_legacy_columns(connection)
            connection.commit()
            for table, column in (("sales_order_items", "variant_info"), ("stock_movements", "variant_id")):
                definition = old_columns.get(table, {}).get(column)
                if definition and not definition.get("nullable", True):
                    _rebuild_sqlite_table(connection, table)
        except Exception:
            connection.rollback()
            raise
