"""Create the pre-total-capacity schema."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0001_baseline"
down_revision = "0000_repair_legacy_db"
branch_labels = None
depends_on = None


def _tables():
    return set(inspect(op.get_bind()).get_table_names())


def upgrade():
    if "cloud_regions" not in _tables():
        op.create_table(
            "cloud_regions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("provider", sa.String(80), nullable=False),
            sa.Column("region", sa.String(120), nullable=False),
            sa.Column("carbon_intensity", sa.Float(), nullable=False),
            sa.Column("carbon_updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("renewable_energy_pct", sa.Float(), nullable=False),
            sa.Column("estimated_cost_usd_per_kwh", sa.Float(), nullable=False),
            sa.Column("latency_ms", sa.Float(), nullable=False),
            sa.Column("available_cpu_cores", sa.Integer(), nullable=False),
            sa.Column("available_memory_gb", sa.Float(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("carbon_intensity >= 0", name="ck_carbon_intensity_nonnegative"),
            sa.CheckConstraint(
                "renewable_energy_pct >= 0 AND renewable_energy_pct <= 100",
                name="ck_renewable_energy_pct_range",
            ),
            sa.CheckConstraint("estimated_cost_usd_per_kwh >= 0", name="ck_cost_nonnegative"),
            sa.CheckConstraint("latency_ms >= 0", name="ck_latency_nonnegative"),
            sa.CheckConstraint("available_cpu_cores >= 1", name="ck_region_cpu_positive"),
            sa.CheckConstraint("available_memory_gb > 0", name="ck_region_memory_positive"),
        )
        op.create_index("ix_cloud_regions_id", "cloud_regions", ["id"])
        op.create_index("ix_cloud_regions_provider", "cloud_regions", ["provider"])
        op.create_index("ix_cloud_regions_region", "cloud_regions", ["region"], unique=True)

    if "workloads" not in _tables():
        op.create_table(
            "workloads",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("workload_type", sa.String(40), nullable=False),
            sa.Column("priority", sa.String(20), nullable=False),
            sa.Column("required_cpu_cores", sa.Integer(), nullable=False),
            sa.Column("required_memory_gb", sa.Float(), nullable=False),
            sa.Column("max_latency_ms", sa.Float(), nullable=False),
            sa.Column("carbon_aware", sa.Boolean(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("required_cpu_cores >= 1", name="ck_workload_cpu_positive"),
            sa.CheckConstraint("required_memory_gb > 0", name="ck_workload_memory_positive"),
            sa.CheckConstraint("max_latency_ms > 0", name="ck_workload_latency_positive"),
        )
        op.create_index("ix_workloads_name", "workloads", ["name"])

    if "scheduled_allocations" not in _tables():
        op.create_table(
            "scheduled_allocations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("workload_id", sa.Integer(), nullable=False),
            sa.Column("region_id", sa.Integer(), nullable=False),
            sa.Column("allocated_cpu_cores", sa.Integer(), nullable=False),
            sa.Column("allocated_memory_gb", sa.Float(), nullable=False),
            sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("allocated_cpu_cores >= 1", name="ck_allocation_cpu_positive"),
            sa.CheckConstraint("allocated_memory_gb > 0", name="ck_allocation_memory_positive"),
            sa.ForeignKeyConstraint(["workload_id"], ["workloads.id"]),
            sa.ForeignKeyConstraint(["region_id"], ["cloud_regions.id"]),
            sa.UniqueConstraint("workload_id", name="uq_allocation_workload"),
        )
        op.create_index(
            "ix_scheduled_allocations_workload_id",
            "scheduled_allocations", ["workload_id"],
        )
        op.create_index(
            "ix_scheduled_allocations_region_id",
            "scheduled_allocations", ["region_id"],
        )


def downgrade():
    # Destructive for application data; use only on a disposable test database.
    tables = _tables()
    if "scheduled_allocations" in tables:
        op.drop_table("scheduled_allocations")
    if "workloads" in tables:
        op.drop_table("workloads")
    if "cloud_regions" in tables:
        op.drop_table("cloud_regions")