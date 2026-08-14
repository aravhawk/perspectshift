"""SQLAlchemy models for the run / artifact index."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class RunRecord(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    host: Mapped[str | None] = mapped_column(String(256), nullable=True)
    model_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    data_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    valid: Mapped[bool] = mapped_column(Boolean, default=False)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    quality_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    workspace_path: Mapped[str] = mapped_column(Text)
    import_status: Mapped[str] = mapped_column(String(64), default="indexed")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    candidates: Mapped[list[CandidateRecord]] = relationship(back_populates="run")
    artifacts: Mapped[list[ArtifactRecord]] = relationship(back_populates="run")
    reports: Mapped[list[ReportRecord]] = relationship(back_populates="run")


class CandidateRecord(Base):
    __tablename__ = "candidates"
    __table_args__ = (UniqueConstraint("run_id", "candidate_id", name="uq_run_candidate"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), index=True)
    candidate_id: Mapped[str] = mapped_column(String(128))
    profile_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    valid: Mapped[bool] = mapped_column(Boolean, default=False)
    quality_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_p99_ms: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[RunRecord] = relationship(back_populates="candidates")


class ProfileIndexRecord(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    model_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    bundle_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    state: Mapped[str] = mapped_column(String(64), default="unknown")
    rejection_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    certified_quality: Mapped[str | None] = mapped_column(String(64), nullable=True)
    certified_p99_ms: Mapped[str | None] = mapped_column(String(64), nullable=True)
    peak_rss_bytes: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provenance_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ReportRecord(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), index=True)
    report_type: Mapped[str] = mapped_column(String(64), default="summary")
    path: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[RunRecord] = relationship(back_populates="reports")


class ArtifactRecord(Base):
    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("run_id", "artifact_id", name="uq_run_artifact"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artifact_id: Mapped[str] = mapped_column(String(128), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), index=True)
    kind: Mapped[str] = mapped_column(String(64), default="file")
    path: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[RunRecord] = relationship(back_populates="artifacts")


class SwitchEventRecord(Base):
    __tablename__ = "switch_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sequence: Mapped[int] = mapped_column(Integer, index=True)
    from_profile: Mapped[str | None] = mapped_column(String(128), nullable=True)
    to_profile: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    manual: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEventRecord(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(128), default="operator")
    action: Mapped[str] = mapped_column(String(128))
    target: Mapped[str | None] = mapped_column(String(256), nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
