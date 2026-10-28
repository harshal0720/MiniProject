import { useState, type ReactNode } from "react";
import { Activity, BellRing, Command, Leaf, Search } from "lucide-react";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  KpiCard,
  LoadingState,
} from "../components/ui/primitives";
import type { HealthSummaryResponse } from "../types/api";
import type { AsyncState } from "../hooks/useApi";
import type { SystemStatusState } from "../features/system/useSystemStatus";

interface CommandCenterProps {
  system: SystemStatusState;
}

function PageHeading({
  eyebrow,
  title,
  description,
  icon,
}: {
  eyebrow: string;
  title: string;
  description: string;
  icon?: ReactNode;
}) {
  return (
    <div className="page-heading animate-enter">
      <div>
        <div className="eyebrow">
          {icon}
          {eyebrow}
        </div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="heading-chip">
        <span className="status-dot status-violet" />
        Carbon-aware infrastructure
      </div>
    </div>
  );
}

function InfoIcon() {
  return <Search size={17} />;
}

function getBadgeTone(
  status: SystemStatusState["status"],
): "good" | "warning" | "critical" | "violet" {
  if (status === "healthy") return "good";
  if (status === "critical" || status === "offline") return "critical";
  if (status === "degraded") return "warning";
  return "violet";
}

export function CommandCenter({ system }: CommandCenterProps) {
  const [refreshing, setRefreshing] = useState(false);
  const health: AsyncState<HealthSummaryResponse> = system.monitoring;
  const data = health.data;

  const totalWorkloads = data
    ? Object.values(data.workloads_by_status ?? {}).reduce(
        (sum, count) => sum + count,
        0,
      )
    : null;

  const openAlerts = data
    ? Object.values(data.open_alerts_by_severity ?? {}).reduce(
        (sum, count) => sum + count,
        0,
      )
    : null;

  const freshness = data?.carbon_freshness;
  const freshCount = Number(freshness?.fresh ?? 0);
  const staleCount = Number(freshness?.stale ?? 0);
  const missingCount = Number(freshness?.missing ?? 0);
  const freshnessTotal = Number(
    freshness?.total ?? freshCount + staleCount + missingCount,
  );
  const freshnessTone =
    staleCount + missingCount > 0 ? "warning" : "good";

  const refresh = async () => {
    setRefreshing(true);
    system.refresh();
    window.setTimeout(() => setRefreshing(false), 500);
  };

  return (
    <div className="page-stack">
      <PageHeading
        eyebrow="COMMAND CENTER / OVERVIEW"
        title="Good evening, Operator."
        description="A clear view of workload health, regional capacity and carbon-aware operations."
        icon={<Command size={15} />}
      />

      <div className="hero-panel animate-enter">
        <div className="hero-grid" />
        <div className="hero-copy">
          <Badge tone="violet">GREENSCALE INTELLIGENCE</Badge>
          <h2>
            Cloud efficiency,
            <br />
            <span>by design.</span>
          </h2>
          <p>
            Coordinate workloads with a sharper view of capacity, carbon
            signals and system health.
          </p>
          <div className="hero-meta">
            <span title={system.reason}>
              <span
                className={`status-dot ${system.tone === "good" ? "status-good" : system.tone === "bad" ? "status-bad" : system.tone === "warning" ? "status-warning" : "status-wait"}`}
              />
              {system.label}
            </span>
            <span className="hero-separator" />
            <span>API-backed overview</span>
          </div>
        </div>
        <div className="orbital-art" aria-hidden="true">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="orbit-core">
            <Leaf size={34} />
          </div>
          <div className="orbit-node node-one" />
          <div className="orbit-node node-two" />
          <div className="orbit-node node-three" />
        </div>
      </div>

      <div className="section-heading">
        <div>
          <span className="eyebrow">SYSTEM SNAPSHOT</span>
          <h2>System snapshot</h2>
          <p className="muted-text">
            Demo data - region values are illustrative.
          </p>
        </div>
        <button
          className="button button-secondary"
          onClick={() => void refresh()}
          disabled={refreshing}
        >
          <Activity size={15} className={refreshing ? "spin" : ""} />
          Refresh health
        </button>
      </div>

      {health.loading && !data ? (
        <div className="kpi-grid">
          {[1, 2, 3, 4].map((number) => (
            <Card key={number}>
              <div className="skeleton h-3 w-24" />
              <div className="skeleton h-8 w-16 mt-5" />
              <div className="skeleton h-3 w-32 mt-4" />
            </Card>
          ))}
        </div>
      ) : health.error && !data ? (
        <ErrorState
          title="Monitoring API unavailable"
          detail={health.error.message}
          onRetry={health.refetch}
        />
      ) : data ? (
        <div className="kpi-grid">
          <KpiCard
            label="MONITORED REGIONS"
            value={data.region_count}
            detail="Regions in health summary"
            tone="violet"
          />
          <KpiCard
            label="WORKLOADS"
            value={totalWorkloads ?? "\u2014"}
            detail="Sum of returned status counts"
            tone="cyan"
          />
          <KpiCard
            label="OPEN ALERTS"
            value={openAlerts ?? "\u2014"}
            detail="Sum of returned severity counts"
            tone={openAlerts ? "good" : "violet"}
          />
          <KpiCard
            label="CARBON FRESHNESS"
            value={freshnessTotal}
            detail={`${freshCount} fresh \u00b7 ${staleCount} stale \u00b7 ${missingCount} missing`}
            tone={freshnessTone}
          />
        </div>
      ) : (
        <EmptyState
          title="No health data"
          detail="The health endpoint has not returned data yet."
        />
      )}

      <div className="content-grid">
        <Card>
          <div className="card-heading">
            <div>
              <span className="eyebrow">PLATFORM STATUS</span>
              <h3>Health summary</h3>
            </div>
            <Activity size={18} className="muted-icon" />
          </div>
          <div
            className="health-summary-row"
            title={system.reason}
          >
            <span>Overall status</span>
            <Badge tone={getBadgeTone(system.status)}>
              {system.label}
            </Badge>
          </div>
          {health.error && !data ? (
            <ErrorState
              detail="The monitoring health endpoint could not be reached."
              onRetry={health.refetch}
            />
          ) : data ? (
            <>
              <div className="health-summary-row">
                <span>Monitored regions</span>
                <strong className="mono">{data.region_count}</strong>
              </div>
              <div className="health-summary-row">
                <span>Workload states reported</span>
                <strong className="mono">
                  {Object.keys(data.workloads_by_status ?? {}).length}
                </strong>
              </div>
              <div className="health-summary-row">
                <span>Alert severity groups</span>
                <strong className="mono">
                  {Object.keys(data.open_alerts_by_severity ?? {}).length}
                </strong>
              </div>
            </>
          ) : (
            <LoadingState />
          )}
        </Card>

        <Card>
          <div className="card-heading">
            <div>
              <span className="eyebrow">DATA INTEGRITY</span>
              <h3>Signal boundaries</h3>
            </div>
            <BellRing size={18} className="muted-icon" />
          </div>
          <div className="notice-row">
            <span className="notice-icon">
              <InfoIcon />
            </span>
            <div>
              <strong>Carbon readings are current-state only</strong>
              <p>
                No carbon history endpoint is present, so no time-series trend
                is implied.
              </p>
            </div>
          </div>
          <div className="notice-row">
            <span className="notice-icon notice-green">
              <Leaf size={17} />
            </span>
            <div>
              <strong>Region values are illustrative</strong>
              <p>
                Demo values are not live cloud-provider telemetry.
              </p>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}