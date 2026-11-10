from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _config(database):
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    return config


def test_fresh_database_migrates_to_head(tmp_path):
    database = tmp_path / "migration-test.sqlite3"
    command.upgrade(_config(database), "head")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert {
            "alembic_version", "categories", "products", "sales", "sale_items",
            "stock_movements", "payments", "units", "product_barcodes",
        }.issubset(tables)
        assert "unit_id" in {column["name"] for column in inspector.get_columns("products")}
    finally:
        engine.dispose()


def test_upgrade_preserves_existing_catalog_data(tmp_path):
    database = tmp_path / "legacy-catalog.sqlite3"
    command.upgrade(_config(database), "0001_initial")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO categories (id, name, is_active) VALUES (1, :name, 1)"),
                {"name": "تصنيف قديم"},
            )
            connection.execute(
                text(
                    "INSERT INTO products "
                    "(id, sku, barcode, name, unit, cost_price, sale_price, stock_quantity, "
                    "minimum_stock, is_active, notes, category_id, created_at, updated_at) "
                    "VALUES (1, 'OLD-01', '6281234567890', 'دفتر قديم', 'علبة', "
                    "2, 3, 7, 1, 1, NULL, 1, '2026-11-10 10:00:00', '2026-11-10 10:00:00')"
                )
            )
    finally:
        engine.dispose()

    command.upgrade(_config(database), "head")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    try:
        with engine.connect() as connection:
            product = connection.execute(
                text("SELECT sku, name, barcode, unit, unit_id, category_id FROM products WHERE id = 1")
            ).one()
            category = connection.execute(
                text("SELECT code, name FROM categories WHERE id = 1")
            ).one()
            migrated_barcode = connection.execute(
                text("SELECT code, barcode_type, is_primary FROM product_barcodes WHERE product_id = 1")
            ).one()
            unit_name = connection.execute(
                text("SELECT name FROM units WHERE id = :unit_id"), {"unit_id": product.unit_id}
            ).scalar_one()
        assert tuple(product[:4]) == ("OLD-01", "دفتر قديم", "6281234567890", "علبة")
        assert product.category_id == 1
        assert category.code == "CAT-000001"
        assert unit_name == "علبة"
        assert tuple(migrated_barcode) == ("6281234567890", "primary", 1)
    finally:
        engine.dispose()
