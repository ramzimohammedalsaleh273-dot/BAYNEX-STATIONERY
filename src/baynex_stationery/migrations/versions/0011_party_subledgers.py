"""Add customer master records and party dimensions to journal lines."""
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0011_party_subledgers"
down_revision = "0010_sale_cost_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customers",
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
    op.create_index("ix_customers_name", "customers", ["name"])
    op.create_index("ix_customers_phone", "customers", ["phone"])
    op.add_column(
        "sales", sa.Column("customer_id", sa.Integer(),
                           sa.ForeignKey("customers.id", ondelete="RESTRICT")),
    )
    op.add_column(
        "journal_lines", sa.Column("customer_id", sa.Integer(),
                                   sa.ForeignKey("customers.id", ondelete="RESTRICT")),
    )
    op.add_column(
        "journal_lines", sa.Column("supplier_id", sa.Integer(),
                                   sa.ForeignKey("suppliers.id", ondelete="RESTRICT")),
    )

    connection = op.get_bind()
    sales = connection.execute(sa.text(
        "SELECT id, customer_name, customer_phone FROM sales "
        "WHERE customer_name IS NOT NULL AND trim(customer_name) != '' "
        "AND trim(customer_name) != 'عميل نقدي' ORDER BY id"
    )).mappings()
    customer_ids = {}
    for sale in sales:
        key = (sale["customer_name"].strip(), (sale["customer_phone"] or "").strip() or None)
        if key not in customer_ids:
            next_id = connection.execute(sa.text(
                "SELECT COALESCE(MAX(id), 0) + 1 FROM customers"
            )).scalar_one()
            code = f"LEG-{next_id:08d}"
            result = connection.execute(sa.text(
                "INSERT INTO customers (id, code, name, phone, is_active, created_at) "
                "VALUES (:id, :code, :name, :phone, 1, :created_at)"
            ), {
                "id": next_id, "code": code, "name": key[0], "phone": key[1],
                "created_at": datetime.now(UTC),
            })
            customer_ids[key] = next_id
        connection.execute(
            sa.text("UPDATE sales SET customer_id=:customer_id WHERE id=:sale_id"),
            {"customer_id": customer_ids[key], "sale_id": sale["id"]},
        )

    connection.execute(sa.text(
        "UPDATE journal_lines SET customer_id = ("
        "SELECT s.customer_id FROM journal_entries j "
        "JOIN sales s ON j.source_type='sale' AND j.source_id=s.id "
        "WHERE j.id=journal_lines.entry_id) "
        "WHERE EXISTS (SELECT 1 FROM journal_entries j "
        "JOIN sales s ON j.source_type='sale' AND j.source_id=s.id "
        "WHERE j.id=journal_lines.entry_id AND journal_lines.debit > 0 "
        "AND journal_lines.account_id=(SELECT id FROM accounts WHERE code='1100'))"
    ))
    connection.execute(sa.text(
        "UPDATE journal_lines SET supplier_id = ("
        "SELECT p.supplier_id FROM journal_entries j "
        "JOIN purchases p ON j.source_type='purchase' AND j.source_id=p.id "
        "WHERE j.id=journal_lines.entry_id) "
        "WHERE EXISTS (SELECT 1 FROM journal_entries j "
        "JOIN purchases p ON j.source_type='purchase' AND j.source_id=p.id "
        "WHERE j.id=journal_lines.entry_id AND journal_lines.credit > 0 "
        "AND journal_lines.account_id=(SELECT id FROM accounts WHERE code='2100'))"
    ))


def downgrade() -> None:
    op.drop_column("journal_lines", "supplier_id")
    op.drop_column("journal_lines", "customer_id")
    op.drop_column("sales", "customer_id")
    op.drop_index("ix_customers_phone", table_name="customers")
    op.drop_index("ix_customers_name", table_name="customers")
    op.drop_table("customers")
