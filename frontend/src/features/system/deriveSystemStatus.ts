export type SystemStatus =
  | "checking"
  | "offline"
  | "critical"
  | "degraded"
  | "healthy";

export type SystemTone = "neutral" | "bad" | "warning" | "good";

export interface ApiHealthSnapshot {
  status: string;
  service: string;
  version: string;
}

export interface MonitoringSnapshot {
  open_alerts_by_severity: Record<string, number>;
  carbon_freshness: Record<string, number>;
}

export interface SystemStatusInput {
  apiLoading: boolean;
  apiError: unknown;
  apiData: ApiHealthSnapshot | null;
  monitorLoading: boolean;
  monitorError: unknown;
  monitorData: MonitoringSnapshot | null;
}

export interface DerivedSystemStatus {
  status: SystemStatus;
  label: string;
  reason: string;
  tone: SystemTone;
}

export function deriveSystemStatus(
  input: SystemStatusInput,
): DerivedSystemStatus {
  if (input.apiError) {
    return {
      status: "offline",
      label: "Backend offline",
      reason: "The basic backend health endpoint could not be reached.",
      tone: "bad",
    };
  }

  if (input.apiLoading && !input.apiData) {
    return {
      status: "checking",
      label: "Checking...",
      reason: "Checking backend and monitoring health.",
      tone: "neutral",
    };
  }

  if (input.apiData && input.apiData.status.toLowerCase() !== "healthy") {
    return {
      status: "degraded",
      label: "Degraded",
      reason: `Backend health reports: ${input.apiData.status}.`,
      tone: "warning",
    };
  }

  if (input.monitorError) {
    return {
      status: "degraded",
      label: "Degraded: monitoring unavailable",
      reason: "The backend is reachable, but the monitoring health endpoint failed.",
      tone: "warning",
    };
  }

  if (input.monitorLoading && !input.monitorData) {
    return {
      status: "checking",
      label: "Checking...",
      reason: "Backend responded; waiting for monitoring health.",
      tone: "neutral",
    };
  }

  if (!input.monitorData) {
    return {
      status: "degraded",
      label: "Degraded: monitoring unavailable",
      reason: "The monitoring health endpoint returned no usable summary.",
      tone: "warning",
    };
  }

  const critical = Number(
    input.monitorData.open_alerts_by_severity.critical ?? 0,
  );
  const warnings = Number(
    input.monitorData.open_alerts_by_severity.warning ?? 0,
  );
  const stale = Number(input.monitorData.carbon_freshness.stale ?? 0);
  const missing = Number(input.monitorData.carbon_freshness.missing ?? 0);

  if (critical > 0) {
    return {
      status: "critical",
      label: "Critical",
      reason: `${critical} critical alert(s) are open.`,
      tone: "bad",
    };
  }

  if (warnings > 0 || stale > 0 || missing > 0) {
    const reasons: string[] = [];
    if (warnings > 0) reasons.push(`${warnings} warning alert(s)`);
    if (stale > 0) reasons.push(`${stale} stale carbon reading(s)`);
    if (missing > 0) reasons.push(`${missing} missing carbon reading(s)`);

    return {
      status: "degraded",
      label: "Degraded",
      reason: reasons.join("; ") + ".",
      tone: "warning",
    };
  }

  return {
    status: "healthy",
    label: "Healthy",
    reason: "Backend and monitoring signals are healthy.",
    tone: "good",
  };
}

/*
Plain TypeScript examples:
- API request pending, no data -> Checking... / neutral
- API request errors -> Backend offline / bad
- API healthy, monitor request errors -> Degraded: monitoring unavailable / warning
- API healthy, critical alerts = 1 -> Critical / bad
- API healthy, missing carbon readings = 4 -> Degraded / warning
- API healthy, no alerts and all readings fresh -> Healthy / good
*/