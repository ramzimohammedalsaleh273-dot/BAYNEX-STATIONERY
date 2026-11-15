from sqlalchemy import create_engine, inspect

from baynex_stationery.db import session as database


def test_application_database_initializer_is_repeatable(tmp_path, monkeypatch):
    database_file = tmp_path / "application.sqlite3"
    monkeypatch.setattr(database, "DATABASE_URL", f"sqlite:///{database_file.as_posix()}")

    database.initialize_database()
    database.initialize_database()

    engine = create_engine(f"sqlite:///{database_file.as_posix()}")
    try:
        tables = set(inspect(engine).get_table_names())
        assert {"alembic_version", "categories", "products", "sales", "sale_items", "stock_movements", "payments"}.issubset(tables)
    finally:
        engine.dispose()
