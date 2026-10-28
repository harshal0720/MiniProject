from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import CloudRegion, ScheduledAllocation
from app.models.monitoring import WorkloadStatusHistory
from app.models.workload import Workload
from app.schemas.optimization import OptimizationRequest
from app.schemas.scheduling import ScheduleRequest, ScheduleResponse
from app.services.optimization import is_carbon_data_fresh, optimize_workload


def _no_capacity_or_no_eligible_region(
    session: Session,
    workload: Workload,
) -> str:
    """
    Distinguish temporary capacity exhaustion from a workload that cannot fit.

    Until total capacity is added in Stage 2, infer total capacity from
    available capacity plus persisted allocations managed by this service.
    """
    regions = list(
        session.scalars(
            select(CloudRegion).order_by(
                CloudRegion.provider,
                CloudRegion.region,
            )
        ).all()
    )

    for region in regions:
        # The latency limit is a hard constraint, regardless of priority.
        if region.latency_ms > workload.max_latency_ms:
            continue

        if workload.carbon_aware and not is_carbon_data_fresh(region):
            continue

        allocated_cpu = session.scalar(
            select(func.coalesce(func.sum(ScheduledAllocation.allocated_cpu_cores), 0))
            .where(ScheduledAllocation.region_id == region.id)
        )
        allocated_memory = session.scalar(
            select(
                func.coalesce(
                    func.sum(ScheduledAllocation.allocated_memory_gb),
                    0.0,
                )
            ).where(ScheduledAllocation.region_id == region.id)
        )

        total_cpu = region.available_cpu_cores + int(allocated_cpu or 0)
        total_memory = region.available_memory_gb + float(allocated_memory or 0.0)

        # The workload exceeds the region's inferred total capacity.
        if (
            total_cpu < workload.required_cpu_cores
            or total_memory < workload.required_memory_gb
        ):
            continue

        # It could fit in principle, but current free capacity is insufficient.
        if (
            region.available_cpu_cores < workload.required_cpu_cores
            or region.available_memory_gb < workload.required_memory_gb
        ):
            return "no_capacity"

    return "no_eligible_region"


def schedule_workload(
    session: Session,
    request: ScheduleRequest,
) -> ScheduleResponse:
    workload = session.get(Workload, request.workload_id)

    if workload is None:
        raise ValueError("Workload not found.")

    existing_allocation = session.scalar(
        select(ScheduledAllocation).where(
            ScheduledAllocation.workload_id == workload.id
        )
    )
    if existing_allocation is not None or workload.status == "scheduled":
        raise ValueError("Workload has already been scheduled.")

    optimization = optimize_workload(
        session,
        OptimizationRequest(workload_id=workload.id),
    )

    if optimization.status != "recommended":
        result_status = _no_capacity_or_no_eligible_region(session, workload)
        session.rollback()

        if result_status == "no_capacity":
            return ScheduleResponse(
                workload_id=workload.id,
                status="no_capacity",
                message=(
                    "Eligible region capacity is currently insufficient. "
                    "The workload remains unscheduled; retry after capacity "
                    "becomes available."
                ),
            )

        return ScheduleResponse(
            workload_id=workload.id,
            status="no_eligible_region",
            message=(
                "No region satisfies the workload's capacity, latency, "
                "and carbon-data eligibility requirements. The workload "
                "remains unscheduled."
            ),
        )

    # Attempt recommendations in rank order. A region can lose capacity
    # between optimization and reservation, so always check atomically.
    for recommendation in optimization.ranked_regions:
        region = session.scalar(
            select(CloudRegion).where(
                CloudRegion.provider == recommendation.provider,
                CloudRegion.region == recommendation.region,
            )
        )
        if region is None:
            continue

        # Recheck freshness at reservation time, not just optimization time.
        if workload.carbon_aware and not is_carbon_data_fresh(region):
            continue

        reservation = session.execute(
            update(CloudRegion)
            .where(
                CloudRegion.id == region.id,
                CloudRegion.available_cpu_cores >= workload.required_cpu_cores,
                CloudRegion.available_memory_gb >= workload.required_memory_gb,
                CloudRegion.latency_ms <= workload.max_latency_ms,
            )
            .values(
                available_cpu_cores=(
                    CloudRegion.available_cpu_cores
                    - workload.required_cpu_cores
                ),
                available_memory_gb=(
                    CloudRegion.available_memory_gb
                    - workload.required_memory_gb
                ),
            )
            .execution_options(synchronize_session=False)
        )

        if reservation.rowcount != 1:
            continue

        scheduled_at = datetime.now(timezone.utc)
        allocation = ScheduledAllocation(
            workload_id=workload.id,
            region_id=region.id,
            allocated_cpu_cores=workload.required_cpu_cores,
            allocated_memory_gb=workload.required_memory_gb,
            scheduled_at=scheduled_at,
        )
        previous_status = workload.status
        workload.status = "scheduled"
        session.add(allocation)
        session.add(WorkloadStatusHistory(
            workload_id=workload.id,
            from_status=previous_status,
            to_status="scheduled",
            changed_at=scheduled_at,
            reason="Scheduled via /api/schedule",
        ))

        try:
            session.commit()
            session.refresh(allocation)
        except IntegrityError as exc:
            session.rollback()
            raise ValueError(
                "Workload has already been scheduled or its allocation conflicts."
            ) from exc

        return ScheduleResponse(
            workload_id=workload.id,
            status="scheduled",
            allocation_id=allocation.id,
            provider=recommendation.provider,
            region=recommendation.region,
            allocated_cpu_cores=allocation.allocated_cpu_cores,
            allocated_memory_gb=allocation.allocated_memory_gb,
            scheduled_at=allocation.scheduled_at,
            message="Workload scheduled and capacity reserved successfully.",
        )

    session.rollback()
    return ScheduleResponse(
        workload_id=workload.id,
        status="no_capacity",
        message=(
            "Eligible regions were found, but none had reservable capacity. "
            "The workload remains unscheduled; retry after capacity changes."
        ),
    )


def get_allocation(
    session: Session,
    workload_id: int,
) -> ScheduledAllocation | None:
    return session.scalar(
        select(ScheduledAllocation).where(
            ScheduledAllocation.workload_id == workload_id
        )
    )
