"""Initial run index schema.

Revision ID: 001_initial
Revises:
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("host", sa.String(length=256), nullable=True),
        sa.Column("model_hash", sa.String(length=128), nullable=True),
        sa.Column("data_hash", sa.String(length=128), nullable=True),
        sa.Column("valid", sa.Boolean(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("quality_summary", sa.Text(), nullable=True),
        sa.Column("latency_summary", sa.Text(), nullable=True),
        sa.Column("workspace_path", sa.Text(), nullable=False),
        sa.Column("import_status", sa.String(length=64), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index("ix_runs_run_id", "runs", ["run_id"])

    op.create_table(
        "candidates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("candidate_id", sa.String(length=128), nullable=False),
        sa.Column("profile_id", sa.String(length=128), nullable=True),
        sa.Column("valid", sa.Boolean(), nullable=False),
        sa.Column("quality_value", sa.String(length=64), nullable=True),
        sa.Column("latency_p99_ms", sa.String(length=64), nullable=True),
        sa.Column("summary_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.run_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "candidate_id", name="uq_run_candidate"),
    )
    op.create_index("ix_candidates_run_id", "candidates", ["run_id"])

    op.create_table(
        "profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("profile_id", sa.String(length=128), nullable=False),
        sa.Column("label", sa.String(length=256), nullable=True),
        sa.Column("model_hash", sa.String(length=128), nullable=True),
        sa.Column("bundle_id", sa.String(length=128), nullable=True),
        sa.Column("eligible", sa.Boolean(), nullable=False),
        sa.Column("state", sa.String(length=64), nullable=False),
        sa.Column("rejection_reasons", sa.Text(), nullable=True),
        sa.Column("certified_quality", sa.String(length=64), nullable=True),
        sa.Column("certified_p99_ms", sa.String(length=64), nullable=True),
        sa.Column("peak_rss_bytes", sa.String(length=64), nullable=True),
        sa.Column("provider", sa.String(length=128), nullable=True),
        sa.Column("provenance_json", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id"),
    )
    op.create_index("ix_profiles_profile_id", "profiles", ["profile_id"])

    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("report_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("report_type", sa.String(length=64), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.run_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_id"),
    )
    op.create_index("ix_reports_run_id", "reports", ["run_id"])
    op.create_index("ix_reports_report_id", "reports", ["report_id"])

    op.create_table(
        "artifacts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("artifact_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.run_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "artifact_id", name="uq_run_artifact"),
    )
    op.create_index("ix_artifacts_run_id", "artifacts", ["run_id"])
    op.create_index("ix_artifacts_artifact_id", "artifacts", ["artifact_id"])

    op.create_table(
        "switch_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("from_profile", sa.String(length=128), nullable=True),
        sa.Column("to_profile", sa.String(length=128), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("manual", sa.Boolean(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_switch_events_sequence", "switch_events", ["sequence"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("target", sa.String(length=256), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_index("ix_switch_events_sequence", table_name="switch_events")
    op.drop_table("switch_events")
    op.drop_index("ix_artifacts_artifact_id", table_name="artifacts")
    op.drop_index("ix_artifacts_run_id", table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_index("ix_reports_report_id", table_name="reports")
    op.drop_index("ix_reports_run_id", table_name="reports")
    op.drop_table("reports")
    op.drop_index("ix_profiles_profile_id", table_name="profiles")
    op.drop_table("profiles")
    op.drop_index("ix_candidates_run_id", table_name="candidates")
    op.drop_table("candidates")
    op.drop_index("ix_runs_run_id", table_name="runs")
    op.drop_table("runs")
