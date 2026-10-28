
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.optimization import OptimizationRequest, OptimizationResponse
from app.services.optimization import optimize_workload

router = APIRouter(prefix="/api/optimize", tags=["Optimization"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=OptimizationResponse)
def optimize(
    payload: OptimizationRequest,
    session: DatabaseSession,
) -> OptimizationResponse:
    try:
        return optimize_workload(session, payload)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if message == "Workload not found." else 422
        raise HTTPException(status_code=status_code, detail=message) from exc
