"""Add chart of accounts and double-entry journals."""
import sqlalchemy as sa
from alembic import op

revision = "0008_accounting"
down_revision = "0007_purchases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("account_type", sa.String(20), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="RESTRICT")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_accounts_account_type", "accounts", ["account_type"])
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("number", sa.String(40), nullable=False, unique=True),
        sa.Column("entry_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.String(240), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("source_type", sa.String(30)),
        sa.Column("source_id", sa.Integer()),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_journal_entries_entry_date", "journal_entries", ["entry_date"])
    op.create_table(
        "journal_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("description", sa.String(240)),
        sa.Column("debit", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("credit", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.UniqueConstraint("entry_id", "account_id", name="uq_journal_line_account"),
        sa.CheckConstraint(
            "(debit >= 0) AND (credit >= 0) AND NOT (debit > 0 AND credit > 0)",
            name="ck_journal_line_one_side",
        ),
    )
    op.create_index("ix_journal_lines_account_id", "journal_lines", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_journal_lines_account_id", table_name="journal_lines")
    op.drop_table("journal_lines")
    op.drop_index("ix_journal_entries_entry_date", table_name="journal_entries")
    op.drop_table("journal_entries")
    op.drop_index("ix_accounts_account_type", table_name="accounts")
    op.drop_table("accounts")
