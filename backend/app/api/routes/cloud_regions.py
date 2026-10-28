from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.cloud_region import (
    CarbonReadingResponse,
    CloudRegionResponse,
)
from app.services.cloud_regions import (
    list_cloud_regions,
    list_current_carbon_readings,
)

router = APIRouter(tags=["Cloud Regions"])

DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get(
    "/api/cloud/regions",
    response_model=list[CloudRegionResponse],
)
def get_cloud_regions(
    session: DatabaseSession,
) -> list[CloudRegionResponse]:
    return list_cloud_regions(session)


@router.get(
    "/api/carbon/current",
    response_model=list[CarbonReadingResponse],
)
def get_current_carbon_readings(
    session: DatabaseSession,
) -> list[CarbonReadingResponse]:
    return list_current_carbon_readings(session)