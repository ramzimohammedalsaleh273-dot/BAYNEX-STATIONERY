"""Track inventory valuation for purchase return lines."""
import sqlalchemy as sa
from alembic import op

revision = "0013_purchase_return_inventory_cost"
down_revision = "0012_purchase_returns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "purchase_return_items",
        sa.Column("inventory_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("purchase_return_items", "inventory_cost")
