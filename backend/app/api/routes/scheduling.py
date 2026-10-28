from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Workload
from app.schemas.scheduling import ScheduleRequest, ScheduleResponse
from app.services.scheduling import schedule_workload

router = APIRouter(prefix="/api/schedule", tags=["Scheduling"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=ScheduleResponse)
def schedule(payload: ScheduleRequest, session: DatabaseSession) -> ScheduleResponse:
    try:
        # The service commits allocation, capacity reservation, workload status,
        # and audit history atomically.
        return schedule_workload(session, payload)
    except ValueError as exc:
        session.rollback()
        message = str(exc)
        status_code = 404 if message == "Workload not found." else 409
        raise HTTPException(status_code=status_code, detail=message) from exc
