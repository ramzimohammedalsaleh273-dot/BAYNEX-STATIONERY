"""Add structured categories, units of measure and multiple product barcodes."""
from alembic import op
import sqlalchemy as sa

revision = "0002_catalog"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("categories", sa.Column("code", sa.String(32), nullable=True))
    op.add_column("categories", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("categories", sa.Column("parent_id", sa.Integer(), nullable=True))
    op.execute("UPDATE categories SET code = 'CAT-' || printf('%06d', id) WHERE code IS NULL")
    with op.batch_alter_table("categories") as batch:
        batch.alter_column("code", existing_type=sa.String(32), nullable=False)
        batch.create_foreign_key(
            "fk_categories_parent_id_categories", "categories", ["parent_id"], ["id"],
            ondelete="RESTRICT",
        )

    op.create_table(
        "units",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("decimal_places", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    units = sa.table(
        "units", sa.column("code", sa.String), sa.column("name", sa.String),
        sa.column("symbol", sa.String), sa.column("decimal_places", sa.Integer),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(units, [
        {"code": "PCS", "name": "قطعة", "symbol": "قطعة", "decimal_places": 0, "is_active": True},
        {"code": "BOX", "name": "علبة", "symbol": "علبة", "decimal_places": 0, "is_active": True},
        {"code": "CTN", "name": "كرتون", "symbol": "كرتون", "decimal_places": 0, "is_active": True},
        {"code": "REAM", "name": "رزمة", "symbol": "رزمة", "decimal_places": 0, "is_active": True},
        {"code": "M", "name": "متر", "symbol": "م", "decimal_places": 3, "is_active": True},
        {"code": "KG", "name": "كيلوجرام", "symbol": "كجم", "decimal_places": 3, "is_active": True},
        {"code": "L", "name": "لتر", "symbol": "لتر", "decimal_places": 3, "is_active": True},
    ])
    op.execute(
        "INSERT INTO units (code, name, symbol, decimal_places, is_active) "
        "SELECT 'LEGACY-' || lower(hex(randomblob(4))), p.unit, p.unit, 3, 1 "
        "FROM products p WHERE NOT EXISTS "
        "(SELECT 1 FROM units u WHERE lower(u.name) = lower(p.unit)) GROUP BY p.unit"
    )
    op.add_column("products", sa.Column("unit_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE products SET unit_id = "
        "(SELECT id FROM units WHERE lower(units.name) = lower(products.unit) LIMIT 1)"
    )
    with op.batch_alter_table("products") as batch:
        batch.alter_column("unit_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key(
            "fk_products_unit_id_units", "units", ["unit_id"], ["id"], ondelete="RESTRICT"
        )

    op.create_table(
        "product_barcodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("barcode_type", sa.String(20), nullable=False, server_default="internal"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("code", name="uq_product_barcodes_code"),
    )
    op.execute(
        "INSERT INTO product_barcodes (product_id, code, barcode_type, is_primary) "
        "SELECT id, barcode, 'primary', 1 FROM products WHERE barcode IS NOT NULL"
    )
    op.create_index("ix_product_barcodes_product_id", "product_barcodes", ["product_id"])
    op.create_index("uq_product_barcodes_code_ci", "product_barcodes", [sa.text("lower(code)")], unique=True)
    op.create_index("uq_products_sku_ci", "products", [sa.text("lower(sku)")], unique=True)
    op.create_index(
        "uq_products_barcode_ci", "products", [sa.text("lower(barcode)")],
        unique=True, sqlite_where=sa.text("barcode IS NOT NULL"),
    )
    op.create_index("uq_categories_code_ci", "categories", [sa.text("lower(code)")], unique=True)
    op.create_index("uq_categories_name_ci", "categories", [sa.text("lower(name)")], unique=True)
    op.create_index("uq_units_code_ci", "units", [sa.text("lower(code)")], unique=True)
    op.create_index("uq_units_name_ci", "units", [sa.text("lower(name)")], unique=True)


def downgrade() -> None:
    op.drop_index("uq_units_name_ci", table_name="units")
    op.drop_index("uq_units_code_ci", table_name="units")
    op.drop_index("uq_categories_name_ci", table_name="categories")
    op.drop_index("uq_categories_code_ci", table_name="categories")
    op.drop_index("uq_products_barcode_ci", table_name="products")
    op.drop_index("uq_products_sku_ci", table_name="products")
    op.drop_index("uq_product_barcodes_code_ci", table_name="product_barcodes")
    op.drop_index("ix_product_barcodes_product_id", table_name="product_barcodes")
    op.drop_table("product_barcodes")
    with op.batch_alter_table("products") as batch:
        batch.drop_constraint("fk_products_unit_id_units", type_="foreignkey")
        batch.drop_column("unit_id")
    op.drop_table("units")
    with op.batch_alter_table("categories") as batch:
        batch.drop_constraint("fk_categories_parent_id_categories", type_="foreignkey")
        batch.drop_column("parent_id")
        batch.drop_column("description")
        batch.drop_column("code")
