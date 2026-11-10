from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

def test_fresh_database_migrates_to_head(tmp_path):
    database = tmp_path / "migration-test.sqlite3"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    try:
        tables = set(inspect(engine).get_table_names())
        assert {"alembic_version", "categories", "products", "sales", "sale_items", "stock_movements", "payments"}.issubset(tables)
    finally:
        engine.dispose()
