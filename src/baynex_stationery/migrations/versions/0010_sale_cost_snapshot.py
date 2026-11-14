"""Store historical unit cost on sales invoice lines."""
import sqlalchemy as sa
from alembic import op

revision = "0010_sale_cost_snapshot"
down_revision = "0009_treasury"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sale_items",
        sa.Column(
            "unit_cost_snapshot", sa.Numeric(14, 2),
            nullable=False, server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("sale_items", "unit_cost_snapshot")
