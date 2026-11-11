"""Add customer, payment and unit snapshots to sales invoices."""
from alembic import op
import sqlalchemy as sa

revision = "0004_sales_documents"
down_revision = "0003_inventory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sales", sa.Column("customer_name", sa.String(160), nullable=True))
    op.add_column("sales", sa.Column("customer_phone", sa.String(40), nullable=True))
    op.add_column("sales", sa.Column("invoice_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sales", sa.Column("payment_method", sa.String(24), nullable=False, server_default="cash"))
    op.add_column("sales", sa.Column("paid_amount", sa.Numeric(14, 2), nullable=False, server_default="0"))
    op.add_column("sales", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("sale_items", sa.Column("product_sku", sa.String(64), nullable=False, server_default=""))
    op.add_column("sale_items", sa.Column("unit_name", sa.String(32), nullable=False, server_default="قطعة"))
    op.add_column("sale_items", sa.Column("discount", sa.Numeric(14, 2), nullable=False, server_default="0"))
    op.add_column("sale_items", sa.Column("tax_amount", sa.Numeric(14, 2), nullable=False, server_default="0"))
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE sales SET invoice_date = created_at, customer_name = 'عميل سابق' "
        "WHERE invoice_date IS NULL"
    ))
    bind.execute(sa.text(
        "UPDATE sale_items SET product_sku = COALESCE((SELECT sku FROM products "
        "WHERE products.id = sale_items.product_id), ''), unit_name = COALESCE((SELECT unit "
        "FROM products WHERE products.id = sale_items.product_id), 'قطعة')"
    ))
    with op.batch_alter_table("sales") as batch:
        batch.alter_column("invoice_date", existing_type=sa.DateTime(timezone=True), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("sales") as batch:
        batch.drop_column("notes")
        batch.drop_column("paid_amount")
        batch.drop_column("payment_method")
        batch.drop_column("invoice_date")
        batch.drop_column("customer_phone")
        batch.drop_column("customer_name")
    with op.batch_alter_table("sale_items") as batch:
        batch.drop_column("tax_amount")
        batch.drop_column("discount")
        batch.drop_column("unit_name")
        batch.drop_column("product_sku")
