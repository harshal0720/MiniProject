import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CloudRegion
from app.models.workload import Workload
from app.schemas.optimization import (
    OptimizationRequest,
    OptimizationResponse,
    RegionRecommendation,
    RegionRejection,
)


def _carbon_freshness_limit() -> timedelta:
    raw_minutes = os.getenv("CARBON_DATA_MAX_AGE_MINUTES", "15")
    try:
        minutes = float(raw_minutes)
    except ValueError as exc:
        raise ValueError(
            "CARBON_DATA_MAX_AGE_MINUTES must be a positive number."
        ) from exc

    if not 0 < minutes < float("inf"):
        raise ValueError(
            "CARBON_DATA_MAX_AGE_MINUTES must be a positive finite number."
        )

    return timedelta(minutes=minutes)


def is_carbon_data_fresh(
    region: CloudRegion,
    *,
    now: datetime | None = None,
) -> bool:
    """Return True only when a carbon value has a recent timestamp."""
    timestamp = region.carbon_updated_at
    if timestamp is None:
        return False

    current_time = now or datetime.now(timezone.utc)

    # SQLite may return naive datetimes even for timezone=True columns.
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    age = current_time - timestamp
    if age < timedelta(0):
        return False

    return age <= _carbon_freshness_limit()


def _normalized(values: list[float], lower_is_better: bool) -> list[float]:
    minimum = min(values)
    maximum = max(values)

    if maximum == minimum:
        return [1.0] * len(values)

    if lower_is_better:
        return [(maximum - value) / (maximum - minimum) for value in values]

    return [(value - minimum) / (maximum - minimum) for value in values]


def optimize_workload(
    session: Session,
    request: OptimizationRequest,
) -> OptimizationResponse:
    workload = session.get(Workload, request.workload_id)
    if workload is None:
        raise ValueError("Workload not found.")

    regions = list(
        session.scalars(
            select(CloudRegion).order_by(
                CloudRegion.provider,
                CloudRegion.region,
            )
        ).all()
    )

    rejected: list[RegionRejection] = []
    eligible: list[CloudRegion] = []

    for region in regions:
        reasons: list[str] = []

        if region.available_cpu_cores < workload.required_cpu_cores:
            reasons.append(
                f"Insufficient CPU: requires {workload.required_cpu_cores}, "
                f"available {region.available_cpu_cores} cores."
            )

        if region.available_memory_gb < workload.required_memory_gb:
            reasons.append(
                f"Insufficient memory: requires {workload.required_memory_gb:g}, "
                f"available {region.available_memory_gb:g} GB."
            )

        # This is a hard requirement, independent of workload priority.
        if region.latency_ms > workload.max_latency_ms:
            reasons.append(
                f"Latency {region.latency_ms:g} ms exceeds the "
                f"{workload.max_latency_ms:g} ms limit."
            )

        # Stale/missing carbon data must never be scored as clean.
        if workload.carbon_aware and not is_carbon_data_fresh(region):
            reasons.append(
                "Carbon data is missing, stale, or has an invalid timestamp."
            )

        if reasons:
            rejected.append(
                RegionRejection(
                    provider=region.provider,
                    region=region.region,
                    reasons=reasons,
                )
            )
        else:
            eligible.append(region)

    if not eligible:
        return OptimizationResponse(
            workload_id=workload.id,
            status="no_eligible_region",
            scoring_note=(
                "No region satisfies the workload's capacity, latency, "
                "and carbon-data eligibility requirements. No recommendation "
                "was made."
            ),
            recommended_region=None,
            ranked_regions=[],
            rejected_regions=rejected,
        )

    weights = request.weights.model_dump()
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError(
            "At least one optimization weight must be greater than zero."
        )

    normalized_weights = {
        key: value / total_weight for key, value in weights.items()
    }

    carbon_scores = _normalized(
        [region.carbon_intensity for region in eligible],
        lower_is_better=True,
    )
    renewable_scores = _normalized(
        [region.renewable_energy_pct for region in eligible],
        lower_is_better=False,
    )
    cost_scores = _normalized(
        [region.estimated_cost_usd_per_kwh for region in eligible],
        lower_is_better=True,
    )
    latency_scores = _normalized(
        [region.latency_ms for region in eligible],
        lower_is_better=True,
    )

    scored: list[tuple[float, int, CloudRegion]] = []
    for index, region in enumerate(eligible):
        component_scores = {
            "carbon": carbon_scores[index],
            "renewable": renewable_scores[index],
            "cost": cost_scores[index],
            "latency": latency_scores[index],
        }
        score = sum(
            component_scores[key] * normalized_weights[key]
            for key in component_scores
        )
        scored.append((score, index, region))

    # Preserve deterministic tie-breaking: score desc, provider, region.
    scored.sort(key=lambda item: (-item[0], item[2].provider, item[2].region))

    ranked: list[RegionRecommendation] = []
    for rank, (score, index, region) in enumerate(scored, start=1):
        components = {
            "carbon": carbon_scores[index],
            "renewable": renewable_scores[index],
            "cost": cost_scores[index],
            "latency": latency_scores[index],
        }
        contributions = {
            key: components[key] * normalized_weights[key]
            for key in components
        }
        explanation = [
            f"{key.title()} contributes {contribution * 100:.1f} points "
            f"(normalized component score {components[key] * 100:.1f}/100)."
            for key, contribution in contributions.items()
        ]

        ranked.append(
            RegionRecommendation(
                rank=rank,
                provider=region.provider,
                region=region.region,
                score=round(score * 100, 2),
                carbon_intensity=region.carbon_intensity,
                renewable_energy_pct=region.renewable_energy_pct,
                estimated_cost_usd_per_kwh=region.estimated_cost_usd_per_kwh,
                latency_ms=region.latency_ms,
                available_cpu_cores=region.available_cpu_cores,
                available_memory_gb=region.available_memory_gb,
                explanation=explanation,
            )
        )

    return OptimizationResponse(
        workload_id=workload.id,
        status="recommended",
        scoring_note=(
            "Scores are relative to currently eligible demo regions, not "
            "absolute performance predictions. Lower carbon, cost, and "
            "latency score better; higher renewable percentage scores better. "
            "Weights are normalized."
        ),
        recommended_region=ranked[0],
        ranked_regions=ranked,
        rejected_regions=rejected,
    )