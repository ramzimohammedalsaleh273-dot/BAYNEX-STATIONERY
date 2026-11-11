"""Introduce warehouse-aware stock ledger, counts and transfers.

Existing product balances are migrated into opening movements after assigning all
legacy movements to the default warehouse. The opening movement is calculated as
current cached stock minus the sum of legacy movements, so the resulting ledger
equals the pre-migration balance without replaying historical sales.
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_inventory"
down_revision = "0002_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "warehouses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("code", name="uq_warehouses_code"),
    )
    op.execute(
        "INSERT INTO warehouses (code, name, is_default, is_active, created_at) "
        "VALUES ('MAIN', 'المستودع الرئيسي', 1, 1, CURRENT_TIMESTAMP)"
    )
    default_id = op.get_bind().execute(
        sa.text("SELECT id FROM warehouses WHERE code='MAIN'")
    ).scalar_one()

    op.add_column("stock_movements", sa.Column("warehouse_id", sa.Integer(), nullable=True))
    op.execute(
        sa.text("UPDATE stock_movements SET warehouse_id=:warehouse_id WHERE warehouse_id IS NULL")
        .bindparams(warehouse_id=default_id)
    )
    with op.batch_alter_table("stock_movements", recreate="always") as batch:
        batch.alter_column("warehouse_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key(
            "fk_stock_movements_warehouse_id_warehouses",
            "warehouses", ["warehouse_id"], ["id"], ondelete="RESTRICT",
        )

    op.add_column("sales", sa.Column("warehouse_id", sa.Integer(), nullable=True))
    op.execute(
        sa.text("UPDATE sales SET warehouse_id=:warehouse_id WHERE warehouse_id IS NULL")
        .bindparams(warehouse_id=default_id)
    )
    with op.batch_alter_table("sales", recreate="always") as batch:
        batch.alter_column("warehouse_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key(
            "fk_sales_warehouse_id_warehouses",
            "warehouses", ["warehouse_id"], ["id"], ondelete="RESTRICT",
        )

    op.create_index("ix_stock_movements_product_warehouse", "stock_movements", ["product_id", "warehouse_id"])
    op.create_index("ix_stock_movements_created_at", "stock_movements", ["created_at"])

    op.create_table(
        "inventory_counts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("number", sa.String(40), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("number", name="uq_inventory_counts_number"),
    )
    op.create_table(
        "inventory_count_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("count_id", sa.Integer(), sa.ForeignKey("inventory_counts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("book_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("counted_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("difference", sa.Numeric(14, 3), nullable=False),
        sa.UniqueConstraint("count_id", "product_id", name="uq_inventory_count_product"),
    )
    op.create_table(
        "inventory_transfers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("number", sa.String(40), nullable=False),
        sa.Column("source_warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("destination_warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("number", name="uq_inventory_transfers_number"),
    )
    op.create_table(
        "inventory_transfer_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("transfer_id", sa.Integer(), sa.ForeignKey("inventory_transfers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.UniqueConstraint("transfer_id", "product_id", name="uq_inventory_transfer_product"),
    )

    # Preserve every existing balance and historical sale movement exactly once.
    op.execute(
        "INSERT INTO stock_movements "
        "(product_id, warehouse_id, movement_type, quantity_delta, reference_type, reference_id, note, created_at) "
        "SELECT p.id, " + str(default_id) + ", 'opening', "
        "CAST(p.stock_quantity - COALESCE((SELECT SUM(m.quantity_delta) FROM stock_movements m "
        "WHERE m.product_id=p.id), 0) AS NUMERIC), "
        "'migration', p.id, 'رصيد افتتاحي ناتج عن ترحيل المرحلة الثالثة', CURRENT_TIMESTAMP "
        "FROM products p WHERE CAST(p.stock_quantity - COALESCE((SELECT SUM(m.quantity_delta) "
        "FROM stock_movements m WHERE m.product_id=p.id), 0) AS NUMERIC) <> 0"
    )


def downgrade() -> None:
    # Keep stock_movements and sales intact; remove only phase-3 documents and warehouse links.
    op.drop_table("inventory_transfer_lines")
    op.drop_table("inventory_transfers")
    op.drop_table("inventory_count_lines")
    op.drop_table("inventory_counts")
    op.drop_index("ix_stock_movements_created_at", table_name="stock_movements")
    op.drop_index("ix_stock_movements_product_warehouse", table_name="stock_movements")
    with op.batch_alter_table("sales", recreate="always") as batch:
        batch.drop_constraint("fk_sales_warehouse_id_warehouses", type_="foreignkey")
        batch.drop_column("warehouse_id")
    with op.batch_alter_table("stock_movements", recreate="always") as batch:
        batch.drop_constraint("fk_stock_movements_warehouse_id_warehouses", type_="foreignkey")
        batch.drop_column("warehouse_id")
    op.drop_table("warehouses")
