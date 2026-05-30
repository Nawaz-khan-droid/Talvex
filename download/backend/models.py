"""
SQLAlchemy ORM models matching the existing Prisma schema.
Column names use camelCase to match the actual SQLite columns.
These models map to EXISTING tables - do NOT use MetaData.create_all().
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.orm import relationship

from database import Base


class TimestampMillis(TypeDecorator):
    """SQLAlchemy type that stores datetime as millisecond timestamps (integer).
    The existing Prisma/SQLite database stores all dates as integer milliseconds.
    """
    impl = Integer
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, datetime):
            return int(value.timestamp() * 1000)
        if isinstance(value, (int, float)):
            return int(value)
        return None

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        if isinstance(value, datetime):
            return value
        return None


class User(Base):
    __tablename__ = "User"

    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    passwordHash = Column(String, nullable=False)
    displayName = Column(String, nullable=True)
    role = Column(String, nullable=False, default="user")  # "user" or "admin"
    isActive = Column(Boolean, nullable=False, default=True)
    createdAt = Column(TimestampMillis, default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000))
    updatedAt = Column(TimestampMillis, default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000), onupdate=lambda: int(datetime.now(timezone.utc).timestamp() * 1000))

    # Relationships
    personas = relationship("JobPersona", back_populates="user")
    applications = relationship("Application", back_populates="user")
    settings = relationship("UserSettings", back_populates="user", uselist=False)
    audit_logs = relationship("AuditLog", foreign_keys="AuditLog.actorUserId", back_populates="actor_user")


class UserSettings(Base):
    __tablename__ = "UserSettings"

    id = Column(String, primary_key=True)
    userId = Column(String, ForeignKey("User.id"), unique=True, nullable=False)
    encryptedSettings = Column(Text, nullable=False, default="{}")
    updatedAt = Column(TimestampMillis, default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000), onupdate=lambda: int(datetime.now(timezone.utc).timestamp() * 1000))

    user = relationship("User", back_populates="settings")


class JobPersona(Base):
    __tablename__ = "JobPersona"

    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    skillsJson = Column(String, nullable=False)
    masterBullets = Column(String, nullable=False)
    summaryTemplate = Column(String, nullable=True)
    createdAt = Column(TimestampMillis, default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000))
    updatedAt = Column(TimestampMillis, default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000))
    userId = Column(String, ForeignKey("User.id"), nullable=True)  # nullable for migration compat

    # Relationships
    user = relationship("User", back_populates="personas")
    applications = relationship("Application", back_populates="persona")


class Application(Base):
    __tablename__ = "Application"

    id = Column(String, primary_key=True)
    personaId = Column(String, ForeignKey("JobPersona.id"), nullable=False)
    company = Column(String, nullable=False)
    roleTitle = Column(String, nullable=False)
    jobDescription = Column(String, nullable=False)
    status = Column(String, nullable=False, default="SCRAPED")
    matchScore = Column(Float, nullable=False, default=0)
    atsScore = Column(Float, nullable=False, default=0)
    extractedKeywords = Column(String, nullable=True)
    privacyStatus = Column(String, nullable=False, default="CLEAN")
    appliedDate = Column(TimestampMillis, nullable=True)
    lastFollowUp = Column(TimestampMillis, nullable=True)
    createdAt = Column(TimestampMillis, default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000))
    updatedAt = Column(TimestampMillis, default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000))

    # Multi-platform tracking
    platform = Column(String, nullable=False, default="manual")
    jobUrl = Column(String, nullable=True)
    salaryMin = Column(Integer, nullable=True)
    salaryMax = Column(Integer, nullable=True)
    salaryCurrency = Column(String, nullable=False, default="INR")
    workMode = Column(String, nullable=True)
    tenure = Column(String, nullable=True)
    perks = Column(String, nullable=True)
    location = Column(String, nullable=True)
    companySize = Column(String, nullable=True)
    sourceEmail = Column(String, nullable=True)

    # Follow-up tracking
    nextFollowUp = Column(TimestampMillis, nullable=True)
    followUpCount = Column(Integer, nullable=False, default=0)
    lastResponseAt = Column(TimestampMillis, nullable=True)
    responseType = Column(String, nullable=True)

    # Custom notes
    notes = Column(String, nullable=True)

    # Relationships
    userId = Column(String, ForeignKey("User.id"), nullable=True)  # nullable for migration compat
    user = relationship("User", back_populates="applications")
    persona = relationship("JobPersona", back_populates="applications")
    canary = relationship("TrackingCanary", back_populates="application", uselist=False)
    resume_versions = relationship("ResumeVersion", back_populates="application", order_by="ResumeVersion.version")
    document_analysis = relationship("DocumentAnalysis", back_populates="application", uselist=False)
    audit_logs = relationship("AuditLog", back_populates="application")


class TrackingCanary(Base):
    __tablename__ = "TrackingCanary"

    id = Column(String, primary_key=True)
    appId = Column(String, ForeignKey("Application.id"), unique=True, nullable=False)
    canaryEmail = Column(String, unique=True, nullable=False)
    trackingSlug = Column(String, nullable=True)
    leakFlagged = Column(Boolean, nullable=False, default=False)
    leakDetails = Column(String, nullable=True)
    createdAt = Column(TimestampMillis, default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000))

    application = relationship("Application", back_populates="canary")


class ResumeVersion(Base):
    __tablename__ = "ResumeVersion"

    id = Column(String, primary_key=True)
    appId = Column(String, ForeignKey("Application.id"), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    filePath = Column(String, nullable=False)
    contentHash = Column(String, nullable=False)
    createdAt = Column(TimestampMillis, default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000))

    application = relationship("Application", back_populates="resume_versions")


class DocumentAnalysis(Base):
    __tablename__ = "DocumentAnalysis"

    id = Column(String, primary_key=True)
    appId = Column(String, ForeignKey("Application.id"), unique=True, nullable=False)
    fileName = Column(String, nullable=False)
    fileType = Column(String, nullable=False)
    fileSize = Column(Integer, nullable=False)
    extractedText = Column(String, nullable=False)
    contactInfo = Column(String, nullable=True)
    detectedSkills = Column(String, nullable=True)
    detectedSections = Column(String, nullable=True)
    atsScore = Column(Float, nullable=False, default=0)
    wordCount = Column(Integer, nullable=False, default=0)
    issues = Column(String, nullable=True)
    recommendations = Column(String, nullable=True)
    ocrUsed = Column(Boolean, nullable=False, default=False)
    analyzedAt = Column(TimestampMillis, default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000))

    application = relationship("Application", back_populates="document_analysis")


class ChatHistory(Base):
    __tablename__ = "ChatHistory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chatId = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    intent = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    modelUsed = Column(String, nullable=True)
    createdAt = Column(Float, nullable=False)  # epoch seconds


# Remove the module-level singleton — it requires a DB session.
# Consumers must use get_chat_history() factory or call methods with a session.


class AuditLog(Base):
    __tablename__ = "AuditLog"

    id = Column(String, primary_key=True)
    appId = Column(String, ForeignKey("Application.id"), nullable=True)
    action = Column(String, nullable=False)
    actor = Column(String, nullable=False, default="SYSTEM")
    details = Column(String, nullable=True)
    timestamp = Column(TimestampMillis, default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000))
    actorUserId = Column(String, ForeignKey("User.id"), nullable=True)  # who performed the action

    application = relationship("Application", back_populates="audit_logs")
    actor_user = relationship("User", foreign_keys=[actorUserId], back_populates="audit_logs")


class ApiUsageLog(Base):
    __tablename__ = "ApiUsageLog"

    id = Column(Integer, primary_key=True, autoincrement=True)
    userId = Column(String, ForeignKey("User.id"), nullable=True, index=True)
    service = Column(String, nullable=False, index=True)  # "openrouter", "jsearch", "tavily"
    endpoint = Column(String, nullable=False)  # e.g., "search-v2", "chat/completions"
    status = Column(String, nullable=False, default="success")  # "success", "error", "rate_limited"
    creditsUsed = Column(Float, nullable=False, default=0.0)
    tokensUsed = Column(Integer, nullable=True)
    errorMessage = Column(String, nullable=True)
    createdAt = Column(Float, nullable=False)  # epoch seconds (matches ChatHistory pattern)


class UserCreditBalance(Base):
    __tablename__ = "UserCreditBalance"

    userId = Column(String, ForeignKey("User.id"), primary_key=True)
    balance = Column(Float, nullable=False, default=100.0)
    totalUsed = Column(Float, nullable=False, default=0.0)
    lastUpdated = Column(TimestampMillis, default=lambda: int(datetime.now(timezone.utc).timestamp() * 1000), onupdate=lambda: int(datetime.now(timezone.utc).timestamp() * 1000))
