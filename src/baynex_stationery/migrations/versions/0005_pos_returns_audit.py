"""Add sales returns and cashier activity history."""
import sqlalchemy as sa
from alembic import op

revision = "0005_pos_returns_audit"
down_revision = "0004_sales_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sale_returns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("number", sa.String(40), nullable=False, unique=True),
        sa.Column("sale_id", sa.Integer(), sa.ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="posted"),
        sa.Column("refund_method", sa.String(24), nullable=False, server_default="cash"),
        sa.Column("refund_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sale_returns_sale_id", "sale_returns", ["sale_id"])
    op.create_table(
        "sale_return_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sale_return_id", sa.Integer(), sa.ForeignKey("sale_returns.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sale_item_id", sa.Integer(), sa.ForeignKey("sale_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(14, 2), nullable=False),
        sa.UniqueConstraint("sale_return_id", "sale_item_id", name="uq_sale_return_item"),
    )
    op.create_table(
        "cashier_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("reference_type", sa.String(30), nullable=False),
        sa.Column("reference_id", sa.Integer(), nullable=False),
        sa.Column("reference_number", sa.String(40), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_cashier_events_created_at", "cashier_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_cashier_events_created_at", table_name="cashier_events")
    op.drop_table("cashier_events")
    op.drop_table("sale_return_items")
    op.drop_index("ix_sale_returns_sale_id", table_name="sale_returns")
    op.drop_table("sale_returns")
