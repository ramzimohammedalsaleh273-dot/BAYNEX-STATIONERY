"""Database engine and versioned schema initialization."""
from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from baynex_stationery.config import APP_DIR, DATABASE_URL

APP_DIR.mkdir(parents=True, exist_ok=True)
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)

@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def initialize_database() -> None:
    """Create or safely upgrade the local database to the latest migration."""
    migration_config = Config()
    migration_config.set_main_option(
        "script_location",
        str(__import__("pathlib").Path(__file__).resolve().parents[1] / "migrations"),
    )
    migration_config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(migration_config, "head")
