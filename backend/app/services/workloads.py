
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.workload import Workload
from app.schemas.workload import WorkloadCreate


def create_workload(session: Session, payload: WorkloadCreate) -> Workload:
    workload = Workload(**payload.model_dump())

    session.add(workload)
    session.commit()
    session.refresh(workload)

    return workload


def list_workloads(session: Session) -> list[Workload]:
    statement = select(Workload).order_by(Workload.created_at.desc(), Workload.id.desc())
    return list(session.scalars(statement).all())
