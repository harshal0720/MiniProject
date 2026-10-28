"""Add monitoring history/alerts and allow zero available CPU."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0003_monitoring"
down_revision = "0002_total_capacity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "workload_status_history" not in tables:
        op.create_table(
            "workload_status_history",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("workload_id", sa.Integer(), sa.ForeignKey("workloads.id", ondelete="CASCADE"), nullable=False),
            sa.Column("from_status", sa.String(20), nullable=False),
            sa.Column("to_status", sa.String(20), nullable=False),
            sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
        )
        op.create_index("ix_workload_status_history_workload_id", "workload_status_history", ["workload_id"])
    if "monitoring_alerts" not in tables:
        op.create_table(
            "monitoring_alerts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("alert_type", sa.String(60), nullable=False),
            sa.Column("severity", sa.String(20), nullable=False),
            sa.Column("region_id", sa.Integer(), sa.ForeignKey("cloud_regions.id", ondelete="SET NULL"), nullable=True),
            sa.Column("workload_id", sa.Integer(), sa.ForeignKey("workloads.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("fingerprint", sa.String(240), nullable=False),
        )
        for name, columns in (
            ("ix_monitoring_alerts_alert_type", ["alert_type"]),
            ("ix_monitoring_alerts_region_id", ["region_id"]),
            ("ix_monitoring_alerts_workload_id", ["workload_id"]),
            ("ix_monitoring_alerts_fingerprint", ["fingerprint"]),
            ("ix_monitoring_alerts_active_fingerprint", ["fingerprint", "resolved"]),
        ):
            op.create_index(name, "monitoring_alerts", columns)

    # Current scheduler may reserve all CPU cores. Model and schema must allow 0 free cores.
    checks = {item.get("name") for item in inspect(bind).get_check_constraints("cloud_regions")}
    if "ck_region_cpu_positive" in checks:
        with op.batch_alter_table("cloud_regions") as batch:
            batch.drop_constraint("ck_region_cpu_positive", type_="check")
            batch.create_check_constraint("ck_region_cpu_nonnegative", "available_cpu_cores >= 0")


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    checks = {item.get("name") for item in inspect(bind).get_check_constraints("cloud_regions")}
    if "ck_region_cpu_nonnegative" in checks:
        zero_cpu = bind.execute(sa.text(
            "SELECT COUNT(*) FROM cloud_regions WHERE available_cpu_cores = 0"
        )).scalar_one()
        if zero_cpu:
            raise RuntimeError(
                "Cannot downgrade 0003_monitoring: cloud_regions contains rows "
                "with available_cpu_cores = 0. Restore positive free CPU or keep "
                "the current migration head before retrying."
            )
        with op.batch_alter_table("cloud_regions") as batch:
            batch.drop_constraint("ck_region_cpu_nonnegative", type_="check")
            batch.create_check_constraint("ck_region_cpu_positive", "available_cpu_cores >= 1")
    if "monitoring_alerts" in tables:
        for name in (
            "ix_monitoring_alerts_active_fingerprint", "ix_monitoring_alerts_fingerprint",
            "ix_monitoring_alerts_workload_id", "ix_monitoring_alerts_region_id",
            "ix_monitoring_alerts_alert_type",
        ):
            op.drop_index(name, table_name="monitoring_alerts")
        op.drop_table("monitoring_alerts")
    if "workload_status_history" in tables:
        op.drop_index("ix_workload_status_history_workload_id", table_name="workload_status_history")
        op.drop_table("workload_status_history")
