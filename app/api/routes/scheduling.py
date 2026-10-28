from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Workload
from app.models.monitoring import WorkloadStatusHistory
from app.schemas.scheduling import ScheduleRequest, ScheduleResponse
from app.services.scheduling import schedule_workload
from app.services.monitoring import utc_now

router = APIRouter(prefix="/api/schedule", tags=["Scheduling"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=ScheduleResponse)
def schedule(payload: ScheduleRequest, session: DatabaseSession) -> ScheduleResponse:
    workload = session.get(Workload, payload.workload_id)
    previous_status = workload.status if workload is not None else None
    try:
        result = schedule_workload(session, payload)
        # The scheduling service intentionally remains unchanged. Record the
        # successful API-driven status change in the monitoring audit trail.
        if result.status == "scheduled" and previous_status != "scheduled":
            session.add(WorkloadStatusHistory(
                workload_id=payload.workload_id,
                from_status=previous_status or "pending",
                to_status="scheduled",
                changed_at=result.scheduled_at or utc_now(),
                reason="Scheduled via /api/schedule",
            ))
            session.commit()
        return result
    except ValueError as exc:
        session.rollback()
        message = str(exc)
        status_code = 404 if message == "Workload not found." else 409
        raise HTTPException(status_code=status_code, detail=message) from exc
