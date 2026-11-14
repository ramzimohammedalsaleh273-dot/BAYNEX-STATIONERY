"""Create supplier and purchase documents."""
import sqlalchemy as sa
from alembic import op

revision = "0007_purchases"
down_revision = "0006_wholesale_price"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("phone", sa.String(40)),
        sa.Column("address", sa.Text()),
        sa.Column("tax_number", sa.String(80)),
        sa.Column("notes", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_suppliers_name", "suppliers", ["name"])
    op.create_table(
        "purchases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("number", sa.String(40), nullable=False, unique=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("invoice_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supplier_invoice_number", sa.String(80)),
        sa.Column("subtotal", sa.Numeric(14, 2), nullable=False),
        sa.Column("discount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        sa.Column("paid_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_purchases_supplier_id", "purchases", ["supplier_id"])
    op.create_table(
        "purchase_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("purchase_id", sa.Integer(), sa.ForeignKey("purchases.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("product_name", sa.String(200), nullable=False),
        sa.Column("product_sku", sa.String(64), nullable=False, server_default=""),
        sa.Column("unit_name", sa.String(32), nullable=False, server_default="قطعة"),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("discount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("line_total", sa.Numeric(14, 2), nullable=False),
    )
    op.create_index("ix_purchase_items_purchase_id", "purchase_items", ["purchase_id"])
    op.create_table(
        "purchase_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("purchase_id", sa.Integer(), sa.ForeignKey("purchases.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("method", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_purchase_payments_purchase_id", "purchase_payments", ["purchase_id"])


def downgrade() -> None:
    op.drop_index("ix_purchase_payments_purchase_id", table_name="purchase_payments")
    op.drop_table("purchase_payments")
    op.drop_index("ix_purchase_items_purchase_id", table_name="purchase_items")
    op.drop_table("purchase_items")
    op.drop_index("ix_purchases_supplier_id", table_name="purchases")
    op.drop_table("purchases")
    op.drop_index("ix_suppliers_name", table_name="suppliers")
    op.drop_table("suppliers")
