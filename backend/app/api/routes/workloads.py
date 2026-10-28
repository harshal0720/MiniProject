
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.workload import WorkloadCreate, WorkloadResponse
from app.services.workloads import create_workload, list_workloads


router = APIRouter(prefix="/api/workload", tags=["Workloads"])

DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/create",
    response_model=WorkloadResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_workload(
    payload: WorkloadCreate,
    session: DatabaseSession,
) -> WorkloadResponse:
    return create_workload(session, payload)


@router.get("/list", response_model=list[WorkloadResponse])
def get_workloads(session: DatabaseSession) -> list[WorkloadResponse]:
    return list_workloads(session)
