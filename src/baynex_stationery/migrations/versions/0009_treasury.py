"""Add cashbox, bank accounts, and treasury vouchers."""
import sqlalchemy as sa
from alembic import op

revision = "0009_treasury"
down_revision = "0008_accounting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "treasury_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("account_kind", sa.String(12), nullable=False),
        sa.Column("ledger_account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("account_kind IN ('cash', 'bank')", name="ck_treasury_account_kind"),
    )
    op.create_index("ix_treasury_accounts_name", "treasury_accounts", ["name"])
    op.create_table(
        "treasury_vouchers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("number", sa.String(40), nullable=False, unique=True),
        sa.Column("voucher_type", sa.String(16), nullable=False),
        sa.Column("treasury_account_id", sa.Integer(), sa.ForeignKey("treasury_accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("destination_account_id", sa.Integer(), sa.ForeignKey("treasury_accounts.id", ondelete="RESTRICT")),
        sa.Column("counter_account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="RESTRICT")),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("voucher_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.String(240), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="posted"),
        sa.Column("journal_entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("voucher_type IN ('receipt', 'payment', 'transfer')", name="ck_treasury_voucher_type"),
        sa.CheckConstraint("amount > 0", name="ck_treasury_voucher_amount_positive"),
        sa.CheckConstraint(
            "(voucher_type = 'transfer' AND destination_account_id IS NOT NULL AND counter_account_id IS NULL) OR "
            "(voucher_type IN ('receipt', 'payment') AND destination_account_id IS NULL AND counter_account_id IS NOT NULL)",
            name="ck_treasury_voucher_counterparty",
        ),
    )
    op.create_index("ix_treasury_vouchers_voucher_date", "treasury_vouchers", ["voucher_date"])
    op.create_index("ix_treasury_vouchers_treasury_account_id", "treasury_vouchers", ["treasury_account_id"])


def downgrade() -> None:
    op.drop_index("ix_treasury_vouchers_treasury_account_id", table_name="treasury_vouchers")
    op.drop_index("ix_treasury_vouchers_voucher_date", table_name="treasury_vouchers")
    op.drop_table("treasury_vouchers")
    op.drop_index("ix_treasury_accounts_name", table_name="treasury_accounts")
    op.drop_table("treasury_accounts")
