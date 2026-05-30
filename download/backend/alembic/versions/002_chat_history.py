"""add_chat_history_table

Migrate Telegram chat history from SQLite shadow database to PostgreSQL.
The ChatHistory model stores per-user message history for the Telegram bot,
replacing the old sqlite3-based implementation in services/chat_history.py.

Tables created:
  - ChatHistory   — Telegram bot message history (chatId, role, content, intent, confidence, modelUsed, createdAt)

Revision ID: 002_chat_history
Revises: 001_initial
Create Date: 2026-05-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002_chat_history"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ChatHistory",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("chatId", sa.String(), nullable=False, index=True),
        sa.Column("role", sa.String(), nullable=False),  # 'user' or 'assistant'
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("modelUsed", sa.String(), nullable=True),
        sa.Column("createdAt", sa.Float(), nullable=False),  # epoch seconds
    )


def downgrade() -> None:
    op.drop_table("ChatHistory")
