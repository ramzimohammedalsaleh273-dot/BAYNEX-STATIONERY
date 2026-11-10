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
