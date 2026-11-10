"""Install the built wheel into an isolated target and smoke-test its real entry point."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

root = Path(__file__).resolve().parents[1]
wheels = list((root / "dist").glob("*.whl"))
if len(wheels) != 1:
    raise SystemExit(f"Expected exactly one wheel, found {len(wheels)}")

required = {
    "baynex_stationery/migrations/env.py",
    "baynex_stationery/migrations/versions/0001_initial_schema.py",
    "baynex_stationery/migrations/script.py.mako",
}
with ZipFile(wheels[0]) as archive:
    missing = required - set(archive.namelist())
if missing:
    raise SystemExit(f"Wheel is missing migration files: {sorted(missing)}")

install_target = root / "build" / "wheel-install"
subprocess.run(
    [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--no-deps",
        "--target",
        str(install_target),
        str(wheels[0]),
    ],
    check=True,
)

with tempfile.TemporaryDirectory(prefix="baynex-wheel-smoke-") as data_dir:
    environment = os.environ.copy()
    environment["BAYNEX_DATA_DIR"] = data_dir
    environment["PYTHONPATH"] = str(install_target)
    environment["QT_QPA_PLATFORM"] = "offscreen"
    smoke = """
from pathlib import Path
from PySide6.QtWidgets import QApplication
from sqlalchemy import inspect
from baynex_stationery.app import run
from baynex_stationery.config import DATABASE_PATH
from baynex_stationery.db.session import SessionLocal, engine, initialize_database
from baynex_stationery.services.products import create_product, list_products
from baynex_stationery.ui.main_window import MainWindow

initialize_database()
tables = set(inspect(engine).get_table_names())
required_tables = {"alembic_version", "categories", "products", "sales", "sale_items", "stock_movements", "payments"}
assert required_tables.issubset(tables), tables
with SessionLocal.begin() as session:
    create_product(session, sku="SMOKE-001", name="اختبار الحزمة", sale_price=12, opening_stock=3)
with SessionLocal() as session:
    products = list_products(session)
    assert len(products) == 1 and products[0].sku == "SMOKE-001"
assert Path(DATABASE_PATH).is_file()
assert callable(run)
app = QApplication([])
window = MainWindow()
window.show()
app.processEvents()
assert window.table.rowCount() == 1
window.close()
app.quit()
print("WHEEL_INSTALL_SMOKE_OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", smoke],
        cwd=install_target,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    if "WHEEL_INSTALL_SMOKE_OK" not in result.stdout:
        raise SystemExit(f"Installed wheel smoke test did not report success: {result.stdout}")
    print(result.stdout.strip())
