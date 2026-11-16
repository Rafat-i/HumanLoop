from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Record(Base):
    __abstract__ = True
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class User(Record):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(80))
    roles: Mapped[list] = mapped_column(JSON, default=list)
    adult_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)


class Session(Record):
    __tablename__ = "sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AccountToken(Record):
    __tablename__ = "account_tokens"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str] = mapped_column(String(16))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorkerProfile(Record):
    __tablename__ = "worker_profiles"
    __table_args__ = (CheckConstraint("hourly_rate >= 100"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    display_name: Mapped[str] = mapped_column(String(80), index=True)
    headline: Mapped[str] = mapped_column(String(160))
    bio: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(String(80), index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    hourly_rate: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="CAD")
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    review_status: Mapped[str] = mapped_column(String(20), default="PENDING")
    identity_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)


class Service(Record):
    __tablename__ = "services"
    worker_id: Mapped[str] = mapped_column(ForeignKey("worker_profiles.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    price: Mapped[int] = mapped_column(Integer)
    __table_args__ = (CheckConstraint("price >= 100"),)


class Bookmark(Record):
    __tablename__ = "bookmarks"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    worker_id: Mapped[str] = mapped_column(ForeignKey("worker_profiles.id", ondelete="CASCADE"))
    __table_args__ = (UniqueConstraint("user_id", "worker_id"),)


class Task(Record):
    __tablename__ = "tasks"
    __table_args__ = (CheckConstraint("budget >= 100"), CheckConstraint("expected_minutes > 0"))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    assigned_worker_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40), index=True)
    required_skills: Mapped[list] = mapped_column(JSON, default=list)
    city: Mapped[str] = mapped_column(String(80))
    budget: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="CAD")
    expected_minutes: Mapped[int] = mapped_column(Integer, default=60)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requirements: Mapped[str] = mapped_column(Text, default="")
    visibility: Mapped[str] = mapped_column(String(10), default="PUBLIC")
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    payment_status: Mapped[str] = mapped_column(String(20), default="UNPAID")
    agent_created: Mapped[bool] = mapped_column(Boolean, default=False)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)


class TaskApplication(Record):
    __tablename__ = "task_applications"
    __table_args__ = (UniqueConstraint("task_id", "worker_id"), CheckConstraint("compensation >= 100"))
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    worker_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    proposal: Mapped[str] = mapped_column(Text)
    compensation: Mapped[int] = mapped_column(Integer)
    estimated_minutes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")


class TaskAssignment(Record):
    __tablename__ = "task_assignments"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), unique=True)
    worker_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    application_id: Mapped[str] = mapped_column(ForeignKey("task_applications.id"), unique=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TaskSubmission(Record):
    __tablename__ = "task_submissions"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    worker_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    report: Mapped[str] = mapped_column(Text)


class Attachment(Record):
    __tablename__ = "attachments"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    uploader_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    storage_key: Mapped[str] = mapped_column(String(80), unique=True)
    filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(80))
    size: Mapped[int] = mapped_column(Integer)
    scan_status: Mapped[str] = mapped_column(String(20), default="NOT_SCANNED")


class Message(Record):
    __tablename__ = "messages"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    sender_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Review(Record):
    __tablename__ = "reviews"
    __table_args__ = (CheckConstraint("rating >= 1 AND rating <= 5"),)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), unique=True)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    worker_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(Text)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)


class Payment(Record):
    __tablename__ = "payments"
    __table_args__ = (CheckConstraint("amount >= 100"),)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), unique=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    provider: Mapped[str] = mapped_column(String(20))
    provider_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")


class PaymentTransaction(Record):
    __tablename__ = "payment_transactions"
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"))
    event_id: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(20))


class APIKey(Record):
    __tablename__ = "api_keys"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    prefix: Mapped[str] = mapped_column(String(16))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list] = mapped_column(JSON)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class AgentToolCall(Record):
    __tablename__ = "agent_tool_calls"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    key_id: Mapped[str | None] = mapped_column(ForeignKey("api_keys.id"), nullable=True)
    tool: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20))


class IdempotencyRecord(Record):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("owner_id", "key", "operation"),)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    key: Mapped[str] = mapped_column(String(128))
    operation: Mapped[str] = mapped_column(String(100))
    request_hash: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str] = mapped_column(String(36))


class Notification(Record):
    __tablename__ = "notifications"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)


class Report(Record):
    __tablename__ = "reports"
    reporter_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")


class Dispute(Record):
    __tablename__ = "disputes"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), unique=True)
    opened_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")


class AuditLog(Record):
    __tablename__ = "audit_logs"
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    resource_id: Mapped[str] = mapped_column(String(36))
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class FeatureFlag(Record):
    __tablename__ = "feature_flags"
    name: Mapped[str] = mapped_column(String(80), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
