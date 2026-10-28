"""Track one-time capacity release and enforce active alert deduplication."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0004_capacity_release_alert_guard"
down_revision = "0003_monitoring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("scheduled_allocations")}
    if "released_at" not in columns:
        op.add_column(
            "scheduled_allocations",
            sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        )

    # Keep the oldest currently-open alert for each fingerprint. Historical
    # resolved alerts are retained and do not participate in the uniqueness rule.
    bind.execute(sa.text(
        "DELETE FROM monitoring_alerts "
        "WHERE resolved = :false_value AND id NOT IN ("
        " SELECT MIN(id) FROM monitoring_alerts "
        " WHERE resolved = :false_value GROUP BY fingerprint)"
    ), {"false_value": False})

    indexes = {item["name"] for item in inspect(bind).get_indexes("monitoring_alerts")}
    if "ix_monitoring_alerts_active_fingerprint" in indexes:
        op.drop_index("ix_monitoring_alerts_active_fingerprint", table_name="monitoring_alerts")
    if "uq_monitoring_alerts_active_fingerprint" not in indexes:
        op.create_index(
            "uq_monitoring_alerts_active_fingerprint",
            "monitoring_alerts",
            ["fingerprint"],
            unique=True,
            sqlite_where=sa.text("resolved = 0"),
            postgresql_where=sa.text("resolved = false"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    indexes = {item["name"] for item in inspect(bind).get_indexes("monitoring_alerts")}
    if "uq_monitoring_alerts_active_fingerprint" in indexes:
        op.drop_index("uq_monitoring_alerts_active_fingerprint", table_name="monitoring_alerts")
    if "ix_monitoring_alerts_active_fingerprint" not in indexes:
        op.create_index(
            "ix_monitoring_alerts_active_fingerprint",
            "monitoring_alerts",
            ["fingerprint", "resolved"],
        )
    columns = {c["name"] for c in inspect(bind).get_columns("scheduled_allocations")}
    if "released_at" in columns:
        op.drop_column("scheduled_allocations", "released_at")
