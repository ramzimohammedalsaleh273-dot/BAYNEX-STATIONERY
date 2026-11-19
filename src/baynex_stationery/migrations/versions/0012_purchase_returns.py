"""Add supplier purchase returns and item-level traceability."""
import sqlalchemy as sa
from alembic import op

revision = "0012_purchase_returns"
down_revision = "0011_party_subledgers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "purchase_returns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("number", sa.String(40), nullable=False, unique=True),
        sa.Column("purchase_id", sa.Integer(), sa.ForeignKey("purchases.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="posted"),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_purchase_returns_purchase_id", "purchase_returns", ["purchase_id"])
    op.create_table(
        "purchase_return_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("purchase_return_id", sa.Integer(), sa.ForeignKey("purchase_returns.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("purchase_item_id", sa.Integer(), sa.ForeignKey("purchase_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("line_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.UniqueConstraint("purchase_return_id", "purchase_item_id", name="uq_purchase_return_item"),
    )
    op.create_index("ix_purchase_return_items_purchase_return_id", "purchase_return_items", ["purchase_return_id"])


def downgrade() -> None:
    op.drop_index("ix_purchase_return_items_purchase_return_id", table_name="purchase_return_items")
    op.drop_table("purchase_return_items")
    op.drop_index("ix_purchase_returns_purchase_id", table_name="purchase_returns")
    op.drop_table("purchase_returns")
