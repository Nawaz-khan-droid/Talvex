"""initial_schema

Create all 8 TALVEX tables with foreign keys and indexes.

Tables created:
  - User          — auth + RBAC
  - UserSettings  — encrypted BYOK key storage
  - JobPersona    — resume personas (scoped by userId)
  - Application   — job applications (core entity)
  - TrackingCanary — email leak detection
  - ResumeVersion  — resume file versioning
  - DocumentAnalysis — ATS scoring & PII extraction
  - AuditLog      — action audit trail

Revision ID: 001_initial
Revises: None
Create Date: 2026-05-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── User ────────────────────────────────────────────────
    op.create_table(
        "User",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False, unique=True, index=True),
        sa.Column("passwordHash", sa.String(), nullable=False),
        sa.Column("displayName", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=False, server_default="user"),
        sa.Column("isActive", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("createdAt", sa.Integer(), nullable=True),
        sa.Column("updatedAt", sa.Integer(), nullable=True),
    )

    # ── UserSettings ────────────────────────────────────────
    op.create_table(
        "UserSettings",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("userId", sa.String(), sa.ForeignKey("User.id"), nullable=False, unique=True),
        sa.Column("encryptedSettings", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("updatedAt", sa.Integer(), nullable=True),
    )

    # ── JobPersona ──────────────────────────────────────────
    op.create_table(
        "JobPersona",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("skillsJson", sa.String(), nullable=False),
        sa.Column("masterBullets", sa.String(), nullable=False),
        sa.Column("summaryTemplate", sa.String(), nullable=True),
        sa.Column("createdAt", sa.Integer(), nullable=True),
        sa.Column("updatedAt", sa.Integer(), nullable=True),
        sa.Column("userId", sa.String(), sa.ForeignKey("User.id"), nullable=True),
    )
    op.create_index("ix_jobpersona_userId", "JobPersona", ["userId"])

    # ── Application ─────────────────────────────────────────
    op.create_table(
        "Application",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("personaId", sa.String(), sa.ForeignKey("JobPersona.id"), nullable=False),
        sa.Column("company", sa.String(), nullable=False),
        sa.Column("roleTitle", sa.String(), nullable=False),
        sa.Column("jobDescription", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="SCRAPED"),
        sa.Column("matchScore", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("atsScore", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("extractedKeywords", sa.String(), nullable=True),
        sa.Column("privacyStatus", sa.String(), nullable=False, server_default="CLEAN"),
        sa.Column("appliedDate", sa.Integer(), nullable=True),
        sa.Column("lastFollowUp", sa.Integer(), nullable=True),
        sa.Column("createdAt", sa.Integer(), nullable=True),
        sa.Column("updatedAt", sa.Integer(), nullable=True),
        # Multi-platform tracking
        sa.Column("platform", sa.String(), nullable=False, server_default="manual"),
        sa.Column("jobUrl", sa.String(), nullable=True),
        sa.Column("salaryMin", sa.Integer(), nullable=True),
        sa.Column("salaryMax", sa.Integer(), nullable=True),
        sa.Column("salaryCurrency", sa.String(), nullable=False, server_default="INR"),
        sa.Column("workMode", sa.String(), nullable=True),
        sa.Column("tenure", sa.String(), nullable=True),
        sa.Column("perks", sa.String(), nullable=True),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("companySize", sa.String(), nullable=True),
        sa.Column("sourceEmail", sa.String(), nullable=True),
        # Follow-up tracking
        sa.Column("nextFollowUp", sa.Integer(), nullable=True),
        sa.Column("followUpCount", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("lastResponseAt", sa.Integer(), nullable=True),
        sa.Column("responseType", sa.String(), nullable=True),
        # Custom notes
        sa.Column("notes", sa.String(), nullable=True),
        # Data isolation FK
        sa.Column("userId", sa.String(), sa.ForeignKey("User.id"), nullable=True),
    )
    op.create_index("ix_application_userId", "Application", ["userId"])
    op.create_index("ix_application_personaId", "Application", ["personaId"])
    op.create_index("ix_application_status", "Application", ["status"])

    # ── TrackingCanary ──────────────────────────────────────
    op.create_table(
        "TrackingCanary",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("appId", sa.String(), sa.ForeignKey("Application.id"), nullable=False, unique=True),
        sa.Column("canaryEmail", sa.String(), nullable=False, unique=True),
        sa.Column("trackingSlug", sa.String(), nullable=True),
        sa.Column("leakFlagged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("leakDetails", sa.String(), nullable=True),
        sa.Column("createdAt", sa.Integer(), nullable=True),
    )

    # ── ResumeVersion ───────────────────────────────────────
    op.create_table(
        "ResumeVersion",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("appId", sa.String(), sa.ForeignKey("Application.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("filePath", sa.String(), nullable=False),
        sa.Column("contentHash", sa.String(), nullable=False),
        sa.Column("createdAt", sa.Integer(), nullable=True),
    )
    op.create_index("ix_resumeversion_appId", "ResumeVersion", ["appId"])

    # ── DocumentAnalysis ────────────────────────────────────
    op.create_table(
        "DocumentAnalysis",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("appId", sa.String(), sa.ForeignKey("Application.id"), nullable=False, unique=True),
        sa.Column("fileName", sa.String(), nullable=False),
        sa.Column("fileType", sa.String(), nullable=False),
        sa.Column("fileSize", sa.Integer(), nullable=False),
        sa.Column("extractedText", sa.String(), nullable=False),
        sa.Column("contactInfo", sa.String(), nullable=True),
        sa.Column("detectedSkills", sa.String(), nullable=True),
        sa.Column("detectedSections", sa.String(), nullable=True),
        sa.Column("atsScore", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("wordCount", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("issues", sa.String(), nullable=True),
        sa.Column("recommendations", sa.String(), nullable=True),
        sa.Column("ocrUsed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("analyzedAt", sa.Integer(), nullable=True),
    )

    # ── AuditLog ────────────────────────────────────────────
    op.create_table(
        "AuditLog",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("appId", sa.String(), sa.ForeignKey("Application.id"), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False, server_default="SYSTEM"),
        sa.Column("details", sa.String(), nullable=True),
        sa.Column("timestamp", sa.Integer(), nullable=True),
        sa.Column("actorUserId", sa.String(), sa.ForeignKey("User.id"), nullable=True),
    )
    op.create_index("ix_auditlog_appId", "AuditLog", ["appId"])
    op.create_index("ix_auditlog_actorUserId", "AuditLog", ["actorUserId"])


def downgrade() -> None:
    """Drop all tables in reverse dependency order."""
    op.drop_table("AuditLog")
    op.drop_table("DocumentAnalysis")
    op.drop_table("ResumeVersion")
    op.drop_table("TrackingCanary")
    op.drop_table("Application")
    op.drop_table("JobPersona")
    op.drop_table("UserSettings")
    op.drop_table("User")
