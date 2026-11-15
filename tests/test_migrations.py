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
            "sale_items", "stock_movements", "payments",
        }.issubset(tables)
        assert "unit_id" in {column["name"] for column in inspector.get_columns("products")}
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT COUNT(*) FROM units")) >= 7
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0002_catalog"
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
    finally:
        engine.dispose()
