"""Track total CPU and memory capacity."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0002_total_capacity"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {c["name"] for c in inspect(bind).get_columns("cloud_regions")}

    if "total_cpu_cores" not in columns:
        op.add_column(
            "cloud_regions",
            sa.Column("total_cpu_cores", sa.Integer(), nullable=False, server_default="0"),
        )
    if "total_memory_gb" not in columns:
        op.add_column(
            "cloud_regions",
            sa.Column("total_memory_gb", sa.Float(), nullable=False, server_default="0.0"),
        )

    bind.execute(sa.text("""
        UPDATE cloud_regions
        SET total_cpu_cores = available_cpu_cores + COALESCE((
                SELECT SUM(a.allocated_cpu_cores)
                FROM scheduled_allocations AS a
                WHERE a.region_id = cloud_regions.id
            ), 0),
            total_memory_gb = available_memory_gb + COALESCE((
                SELECT SUM(a.allocated_memory_gb)
                FROM scheduled_allocations AS a
                WHERE a.region_id = cloud_regions.id
            ), 0)
    """))


def downgrade():
    bind = op.get_bind()
    columns = {c["name"] for c in inspect(bind).get_columns("cloud_regions")}
    with op.batch_alter_table("cloud_regions") as batch:
        if "total_memory_gb" in columns:
            batch.drop_column("total_memory_gb")
        if "total_cpu_cores" in columns:
            batch.drop_column("total_cpu_cores")