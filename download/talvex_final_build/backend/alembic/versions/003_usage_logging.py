"""add_api_usage_log_and_user_credit_balance

Add API usage tracking and per-user credit balance tables.

Tables created:
  - ApiUsageLog       — per-request log of external API calls (service, endpoint, credits, tokens, status)
  - UserCreditBalance — per-user credit wallet (balance, totalUsed, lastUpdated)

Revision ID: 003_usage_logging
Revises: 002_chat_history
Create Date: 2026-05-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003_usage_logging"
down_revision: Union[str, None] = "002_chat_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── ApiUsageLog ─────────────────────────────────────────
    op.create_table(
        "ApiUsageLog",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("userId", sa.String(), sa.ForeignKey("User.id"), nullable=True),
        sa.Column("service", sa.String(), nullable=False),  # "openrouter", "jsearch", "tavily"
        sa.Column("endpoint", sa.String(), nullable=False),  # e.g., "search-v2", "chat/completions"
        sa.Column("status", sa.String(), nullable=False, server_default="success"),
        sa.Column("creditsUsed", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("tokensUsed", sa.Integer(), nullable=True),
        sa.Column("errorMessage", sa.String(), nullable=True),
        sa.Column("createdAt", sa.Float(), nullable=False),  # epoch seconds
    )
    op.create_index("ix_apiusagelog_userId", "ApiUsageLog", ["userId"])
    op.create_index("ix_apiusagelog_service", "ApiUsageLog", ["service"])

    # ── UserCreditBalance ───────────────────────────────────
    op.create_table(
        "UserCreditBalance",
        sa.Column("userId", sa.String(), sa.ForeignKey("User.id"), primary_key=True),
        sa.Column("balance", sa.Float(), nullable=False, server_default=sa.text("100")),
        sa.Column("totalUsed", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("lastUpdated", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("UserCreditBalance")
    op.drop_table("ApiUsageLog")
