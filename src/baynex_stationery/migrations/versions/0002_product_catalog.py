"""Add reusable units and product catalog metadata."""
from alembic import op
import sqlalchemy as sa

revision = "0002_catalog"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "units",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("symbol", sa.String(24), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("name", name="uq_units_name"),
        sa.UniqueConstraint("symbol", name="uq_units_symbol"),
    )
    units = sa.table(
        "units",
        sa.column("name", sa.String(80)),
        sa.column("symbol", sa.String(24)),
        sa.column("is_active", sa.Boolean()),
    )
    op.bulk_insert(units, [
        {"name": "قطعة", "symbol": "قطعة", "is_active": True},
        {"name": "علبة", "symbol": "علبة", "is_active": True},
        {"name": "كرتون", "symbol": "كرتون", "is_active": True},
        {"name": "متر", "symbol": "متر", "is_active": True},
        {"name": "كيلوجرام", "symbol": "كجم", "is_active": True},
        {"name": "جرام", "symbol": "جم", "is_active": True},
        {"name": "خدمة", "symbol": "خدمة", "is_active": True},
    ])
    op.add_column("categories", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("products", sa.Column("unit_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_products_unit_id_units", "products", "units", ["unit_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_index("ix_products_barcode", "products", ["barcode"])
    op.execute(
        "UPDATE products SET unit_id = (SELECT id FROM units WHERE units.symbol = products.unit) "
        "WHERE unit_id IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_products_barcode", table_name="products")
    op.drop_constraint("fk_products_unit_id_units", "products", type_="foreignkey")
    op.drop_column("products", "unit_id")
    op.drop_column("categories", "description")
    op.drop_table("units")
