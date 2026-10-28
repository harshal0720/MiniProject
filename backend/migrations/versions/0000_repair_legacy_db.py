"""Repair the known legacy cloud_regions schema."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0000_repair_legacy_db"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if "cloud_regions" not in inspector.get_table_names():
        return

    columns = {c["name"] for c in inspector.get_columns("cloud_regions")}
    expected = {
        "id", "provider", "region", "carbon_intensity",
        "renewable_energy_pct", "estimated_cost_usd_per_kwh",
        "latency_ms", "updated_at", "available_cpu_cores",
        "available_memory_gb",
    }
    missing = expected - columns
    if missing:
        raise RuntimeError(
            "Unrecognized legacy cloud_regions schema; missing: "
            + ", ".join(sorted(missing))
        )

    if "carbon_updated_at" not in columns:
        with op.batch_alter_table("cloud_regions") as batch:
            batch.add_column(
                sa.Column("carbon_updated_at", sa.DateTime(timezone=True), nullable=True)
            )


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if "cloud_regions" not in inspector.get_table_names():
        return

    columns = {c["name"] for c in inspector.get_columns("cloud_regions")}
    if "carbon_updated_at" in columns:
        with op.batch_alter_table("cloud_regions") as batch:
            batch.drop_column("carbon_updated_at")