from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_fresh_database_migrates_to_head(tmp_path):
    database = tmp_path / "migration-test.sqlite3"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert {
            "alembic_version", "categories", "units", "products", "sales",
            "sale_items", "stock_movements", "payments", "warehouses",
            "inventory_counts", "inventory_count_lines", "inventory_transfers",
            "inventory_transfer_lines", "sale_returns", "sale_return_items",
            "cashier_events", "suppliers", "purchases", "purchase_items", "purchase_payments", "accounts", "journal_entries", "journal_lines", "treasury_accounts", "treasury_vouchers",
        }.issubset(tables)
        product_columns = {column["name"] for column in inspector.get_columns("products")}
        sale_item_columns = {column["name"] for column in inspector.get_columns("sale_items")}
        assert "unit_cost_snapshot" in sale_item_columns
        assert "unit_id" in product_columns
        assert "wholesale_price" in product_columns
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT COUNT(*) FROM units")) >= 7
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0010_sale_cost_snapshot"
            assert connection.scalar(text("SELECT COUNT(*) FROM warehouses WHERE is_default=1")) == 1
    finally:
        engine.dispose()


def test_upgrade_from_phase_one_preserves_existing_products(tmp_path):
    database = tmp_path / "upgrade-test.sqlite3"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.upgrade(config, "0001_initial")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO categories (name, is_active) VALUES (:name, 1)"),
                {"name": "أقلام"},
            )
            connection.execute(text("""
                INSERT INTO products (
                    sku, barcode, name, unit, cost_price, sale_price, stock_quantity,
                    minimum_stock, is_active, notes, category_id, created_at, updated_at
                ) VALUES (
                    'OLD-01', '6280000000001', 'قلم قديم', 'قطعة', 2, 4, 9,
                    1, 1, NULL, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """))
        command.upgrade(config, "head")
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT sku, stock_quantity, unit_id FROM products WHERE sku='OLD-01'")
            ).one()
            assert row.sku == "OLD-01"
            assert str(row.stock_quantity) in {"9", "9.000"}
            assert row.unit_id is not None
            balance = connection.scalar(text(
                "SELECT SUM(quantity_delta) FROM stock_movements WHERE product_id="
                "(SELECT id FROM products WHERE sku='OLD-01')"
            ))
            assert str(balance) in {"9", "9.000"}
    finally:
        engine.dispose()



def test_upgrade_from_phase_two_preserves_legacy_sales_movements_and_balance(tmp_path):
    database = tmp_path / "phase-two-ledger.sqlite3"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.upgrade(config, "0002_catalog")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO products (
                    sku, barcode, name, unit, cost_price, sale_price, stock_quantity,
                    minimum_stock, is_active, notes, category_id, unit_id, created_at, updated_at
                ) VALUES (
                    'LEGACY-01', NULL, 'دفتر تاريخي', 'قطعة', 2, 4, 8,
                    0, 1, NULL, NULL, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """))
            product_id = connection.scalar(text(
                "SELECT id FROM products WHERE sku='LEGACY-01'"
            ))
            connection.execute(text("""
                INSERT INTO stock_movements (
                    product_id, movement_type, quantity_delta, reference_type,
                    reference_id, note, created_at
                ) VALUES (
                    :product_id, 'sale', -2, 'sale', 77, 'فاتورة تاريخية',
                    CURRENT_TIMESTAMP
                )
            """), {"product_id": product_id})
        command.upgrade(config, "head")
        with engine.connect() as connection:
            movements = connection.execute(text("""
                SELECT movement_type, quantity_delta, warehouse_id
                FROM stock_movements WHERE product_id=:product_id ORDER BY id
            """), {"product_id": product_id}).all()
            assert len(movements) == 2
            assert movements[0].movement_type == "sale"
            assert str(movements[0].quantity_delta) in {"-2", "-2.000"}
            assert movements[1].movement_type == "opening"
            assert str(movements[1].quantity_delta) in {"10", "10.000"}
            assert movements[0].warehouse_id == movements[1].warehouse_id
            balance = connection.scalar(text(
                "SELECT SUM(quantity_delta) FROM stock_movements WHERE product_id=:product_id"
            ), {"product_id": product_id})
            assert str(balance) in {"8", "8.000"}
    finally:
        engine.dispose()
