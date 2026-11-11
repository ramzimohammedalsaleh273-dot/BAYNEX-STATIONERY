"""Add optional wholesale price to the product catalog."""
import sqlalchemy as sa
from alembic import op

revision = "0006_wholesale_price"
down_revision = "0005_pos_returns_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("wholesale_price", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("products") as batch:
        batch.drop_column("wholesale_price")
