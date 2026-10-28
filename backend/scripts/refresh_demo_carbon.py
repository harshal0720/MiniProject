from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import CloudRegion
from app.services.cloud_regions import DEMO_REGIONS


def main() -> None:
    demo_region_names = [item["region"] for item in DEMO_REGIONS]
    now = datetime.now(timezone.utc)

    with Session(bind=engine) as session:
        result = session.execute(
            update(CloudRegion)
            .where(CloudRegion.region.in_(demo_region_names))
            .values(
                carbon_updated_at=now,
                updated_at=now,
            )
        )
        session.commit()

        print(f"Updated demo timestamps for {result.rowcount} region(s).")
        print("These are demo timestamps, not live carbon measurements.")


if __name__ == "__main__":
    main()
