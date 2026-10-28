/* Types for the GreenScale AI backend API contract. */

export type WorkloadType =
  | "batch"
  | "web_service"
  | "ml_training"
  | "data_processing";

export type WorkloadPriority =
  | "low"
  | "normal"
  | "high"
  | "critical";

export type WorkloadStatus =
  | "pending"
  | "scheduled"
  | "running"
  | "completed"
  | "failed"
  | "deferred";

export type AlertSeverity = "warning" | "critical";
export type RegionLevel = "ok" | "warning" | "critical";
export type CarbonFreshness = "fresh" | "stale" | "missing";

export type SchedulingStatus =
  | "scheduled"
  | "no_eligible_region"
  | "no_capacity";

export interface CloudRegionResponse {
  id: number;
  provider: string;
  region: string;
  carbon_intensity: number;
  renewable_energy_pct: number;
  estimated_cost_usd_per_kwh: number;
  latency_ms: number;
  updated_at: string;
}

export interface CarbonReadingResponse {
  region_id: number;
  provider: string;
  region: string;
  carbon_intensity: number;
  renewable_energy_pct: number;
  updated_at: string;
}

export interface WorkloadCreate {
  name: string;
  workload_type: WorkloadType;
  priority?: WorkloadPriority;
  required_cpu_cores: number;
  required_memory_gb: number;
  max_latency_ms: number;
  carbon_aware?: boolean;
}

export interface WorkloadResponse {
  id: number;
  name: string;
  workload_type: WorkloadType;
  priority: WorkloadPriority;
  required_cpu_cores: number;
  required_memory_gb: number;
  max_latency_ms: number;
  carbon_aware: boolean;
  status: WorkloadStatus;
  created_at: string;
}

export interface OptimizationWeights {
  carbon?: number;
  renewable?: number;
  cost?: number;
  latency?: number;
}

export interface OptimizationRequest {
  workload_id: number;
  weights?: OptimizationWeights;
}

export interface RegionRejection {
  provider: string;
  region: string;
  reasons: string[];
}

export interface RegionRecommendation {
  rank: number;
  provider: string;
  region: string;
  score: number;
  carbon_intensity: number;
  renewable_energy_pct: number;
  estimated_cost_usd_per_kwh: number;
  latency_ms: number;
  available_cpu_cores: number;
  available_memory_gb: number;
  explanation: string[];
}

export interface OptimizationResponse {
  workload_id: number;
  status: string;
  scoring_note: string;
  recommended_region: RegionRecommendation | null;
  ranked_regions: RegionRecommendation[];
  rejected_regions: RegionRejection[];
}

export interface ScheduleRequest {
  workload_id: number;
}

export interface ScheduleResponse {
  workload_id: number;
  status: SchedulingStatus;
  allocation_id: number | null;
  provider: string | null;
  region: string | null;
  allocated_cpu_cores: number | null;
  allocated_memory_gb: number | null;
  scheduled_at: string | null;
  message: string;
}

export interface HealthSummaryResponse {
  region_count: number;
  open_alerts_by_severity: Record<string, number>;
  workloads_by_status: Record<string, number>;
  carbon_freshness: Record<string, number>;
}

export interface RegionMonitorResponse {
  id: number;
  provider: string;
  region: string;
  used_cpu_cores: number;
  total_cpu_cores: number;
  available_cpu_cores: number;
  cpu_utilisation_pct: number;
  used_memory_gb: number;
  total_memory_gb: number;
  available_memory_gb: number;
  memory_utilisation_pct: number;
  level: RegionLevel;
  carbon_freshness: CarbonFreshness;
  carbon_updated_at: string | null;
}

export interface WorkloadMonitorResponse {
  id: number;
  name: string;
  workload_type: WorkloadType;
  priority: WorkloadPriority;
  required_cpu_cores: number;
  required_memory_gb: number;
  max_latency_ms: number;
  carbon_aware: boolean;
  status: WorkloadStatus;
  created_at: string;
}

export interface StatusHistoryResponse {
  id: number;
  from_status: string;
  to_status: string;
  changed_at: string;
  reason: string | null;
}

export interface WorkloadDetailResponse extends WorkloadMonitorResponse {
  history: StatusHistoryResponse[];
}

export interface WorkloadPageResponse {
  items: WorkloadMonitorResponse[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface AlertResponse {
  id: number;
  alert_type: string;
  severity: AlertSeverity;
  region_id: number | null;
  workload_id: number | null;
  created_at: string;
  resolved: boolean;
  message: string;
  fingerprint: string;
}

export interface AlertPageResponse {
  items: AlertResponse[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface AlertResolveResponse {
  id: number;
  resolved: boolean;
}

export interface EvaluateResponse {
  created_count: number;
  skipped_count: number;
}

export interface WorkloadTransitionRequest {
  to_status: WorkloadStatus;
  reason?: string | null;
}

export interface ValidationError {
  loc: Array<string | number>;
  msg: string;
  type: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
}

export interface HTTPValidationError {
  detail?: ValidationError[] | string;
}

export type TransitionResponse = Record<string, unknown>;

export interface ApiListParams {
  page?: number;
  page_size?: number;
  status?: string;
  region?: string;
  created_from?: string;
  created_to?: string;
  severity?: string;
  resolved?: boolean;
  region_id?: number;
  type?: string;
}