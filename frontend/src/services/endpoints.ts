import type {
  AlertPageResponse, AlertResolveResponse, ApiListParams, CarbonReadingResponse,
  CloudRegionResponse, EvaluateResponse, HealthSummaryResponse, OptimizationRequest,
  OptimizationResponse, RegionMonitorResponse, ScheduleRequest, ScheduleResponse,
  TransitionResponse, WorkloadCreate, WorkloadDetailResponse, WorkloadPageResponse,
  WorkloadResponse, WorkloadTransitionRequest,
} from "../types/api";
import { apiFetch, buildQuery } from "./api";

export const endpoints = {
  cloudRegions: () => apiFetch<CloudRegionResponse[]>("/api/cloud/regions"),
  currentCarbon: () => apiFetch<CarbonReadingResponse[]>("/api/carbon/current"),
  createWorkload: (body: WorkloadCreate) =>
    apiFetch<WorkloadResponse>("/api/workload/create", { method: "POST", body }),
  listWorkloads: () => apiFetch<WorkloadResponse[]>("/api/workload/list"),
  optimize: (body: OptimizationRequest) =>
    apiFetch<OptimizationResponse>("/api/optimize", { method: "POST", body }),
  schedule: (body: ScheduleRequest) =>
    apiFetch<ScheduleResponse>("/api/schedule", { method: "POST", body }),
  monitorHealth: () => apiFetch<HealthSummaryResponse>("/api/monitor/health"),
  monitorRegions: () => apiFetch<RegionMonitorResponse[]>("/api/monitor/regions"),
  monitorWorkloads: (params: ApiListParams = {}) =>
    apiFetch<WorkloadPageResponse>(`/api/monitor/workloads${buildQuery(params)}`),
  monitorWorkloadDetail: (workloadId: number) =>
    apiFetch<WorkloadDetailResponse>(`/api/monitor/workloads/${workloadId}`),
  transitionWorkload: (workloadId: number, body: WorkloadTransitionRequest) =>
    apiFetch<TransitionResponse>(`/api/monitor/workloads/${workloadId}/transition`, { method: "POST", body }),
  monitorAlerts: (params: ApiListParams = {}) =>
    apiFetch<AlertPageResponse>(`/api/monitor/alerts${buildQuery(params)}`),
  evaluateMonitoring: () =>
    apiFetch<EvaluateResponse>("/api/monitor/evaluate", { method: "POST" }),
  resolveAlert: (alertId: number) =>
    apiFetch<AlertResolveResponse>(`/api/monitor/alerts/${alertId}/resolve`, { method: "POST" }),
  root: () => apiFetch<{ project: string; status: string; message: string }>("/"),
  health: () => apiFetch<{ status: string; service: string; version: string }>("/api/health"),
};