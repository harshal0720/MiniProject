import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowUpRight, Plus, RefreshCw, Search, X } from "lucide-react";
import {
  Badge,
  Card,
  DataTable,
  Drawer,
  EmptyState,
  ErrorState,
  LoadingState,
  Modal,
} from "../components/ui/primitives";
import { ApiError } from "../services/api";
import { endpoints } from "../services/endpoints";
import type {
  WorkloadCreate,
  WorkloadDetailResponse,
  WorkloadMonitorResponse,
  WorkloadStatus,
  WorkloadType,
  WorkloadPriority,
} from "../types/api";

const statuses: WorkloadStatus[] = [
  "pending", "scheduled", "running", "completed", "failed", "deferred",
];
const types: WorkloadType[] = [
  "batch", "web_service", "ml_training", "data_processing",
];
const priorities: WorkloadPriority[] = ["low", "normal", "high", "critical"];

function tone(value: string): "neutral" | "good" | "warning" | "critical" | "violet" | "cyan" {
  if (value === "running" || value === "completed" || value === "scheduled") return "good";
  if (value === "failed" || value === "critical") return "critical";
  if (value === "pending" || value === "deferred" || value === "high") return "warning";
  if (value === "normal" || value === "ml_training") return "violet";
  if (value === "web_service") return "cyan";
  return "neutral";
}

function localTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "An unexpected error occurred.";
}

export function WorkloadsPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<WorkloadMonitorResponse[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [pages, setPages] = useState(0);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState<WorkloadStatus | "all">("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [createOpen, setCreateOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<WorkloadDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [form, setForm] = useState<WorkloadCreate>({
    name: "",
    workload_type: "web_service",
    priority: "normal",
    required_cpu_cores: 2,
    required_memory_gb: 4,
    max_latency_ms: 250,
    carbon_aware: true,
  });
  const [nextStatus, setNextStatus] = useState<WorkloadStatus>("running");
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await endpoints.monitorWorkloads({
        page,
        page_size: pageSize,
        ...(filter === "all" ? {} : { status: filter }),
      });
      setItems(result.items);
      setPages(result.pages);
      setTotal(result.total);
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, filter, refreshKey]);

  useEffect(() => {
    void load();
  }, [load]);

  const loadDetail = useCallback(async (id: number) => {
    setSelectedId(id);
    setDetail(null);
    setDetailError(null);
    setActionError(null);
    setDetailLoading(true);
    try {
      const result = await endpoints.monitorWorkloadDetail(id);
      setDetail(result);
      setNextStatus(result.status === "pending" ? "scheduled" : "running");
    } catch (err) {
      setDetailError(messageOf(err));
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const visibleItems = items.filter((item) =>
    item.name.toLowerCase().includes(search.trim().toLowerCase()),
  );

  const updateForm = <K extends keyof WorkloadCreate>(
    key: K,
    value: WorkloadCreate[K],
  ) => {
    setForm((current) => ({ ...current, [key]: value }));
    setFieldErrors((current) => ({ ...current, [key]: "" }));
  };

  const validate = (): boolean => {
    const errors: Record<string, string> = {};
    if (!form.name.trim() || form.name.length > 120) {
      errors.name = "Name must contain 1 to 120 characters.";
    }
    if (!types.includes(form.workload_type)) errors.workload_type = "Select a valid type.";
    if (!priorities.includes(form.priority ?? "normal")) errors.priority = "Select a valid priority.";
    if (!Number.isInteger(form.required_cpu_cores) ||
        form.required_cpu_cores < 1 || form.required_cpu_cores > 1024) {
      errors.required_cpu_cores = "CPU cores must be an integer from 1 to 1024.";
    }
    if (!Number.isFinite(form.required_memory_gb) ||
        form.required_memory_gb <= 0 || form.required_memory_gb > 4096) {
      errors.required_memory_gb = "Memory must be greater than 0 and at most 4096 GB.";
    }
    if (!Number.isFinite(form.max_latency_ms) ||
        form.max_latency_ms <= 0 || form.max_latency_ms > 60000) {
      errors.max_latency_ms = "Latency must be greater than 0 and at most 60000 ms.";
    }
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const createWorkload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError("");
    if (!validate()) return;
    setSaving(true);
    try {
      await endpoints.createWorkload({
        ...form,
        name: form.name.trim(),
        priority: form.priority ?? "normal",
        carbon_aware: form.carbon_aware ?? true,
      });
      setCreateOpen(false);
      setForm({
        name: "",
        workload_type: "web_service",
        priority: "normal",
        required_cpu_cores: 2,
        required_memory_gb: 4,
        max_latency_ms: 250,
        carbon_aware: true,
      });
      setPage(1);
      setRefreshKey((value) => value + 1);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        setFormError(err.message);
        const parsed: Record<string, string> = {};
        err.fields.forEach((entry) => {
          const colon = entry.indexOf(":");
          if (colon > 0) parsed[entry.slice(0, colon)] = entry.slice(colon + 1).trim();
        });
        setFieldErrors((current) => ({ ...current, ...parsed }));
      } else {
        setFormError(messageOf(err));
      }
    } finally {
      setSaving(false);
    }
  };

  const transition = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (selectedId === null) return;
    setSaving(true);
    setActionError(null);
    try {
      await endpoints.transitionWorkload(selectedId, {
        to_status: nextStatus,
        reason: reason.trim() || null,
      });
      setRefreshKey((value) => value + 1);
      await loadDetail(selectedId);
    } catch (err) {
      setActionError(messageOf(err));
    } finally {
      setSaving(false);
    }
  };

  const fieldClass = "field-control";
  const closeDetail = () => {
    setSelectedId(null);
    setDetail(null);
    setDetailError(null);
    setActionError(null);
  };

  return (
    <div className="page-stack">
      <div className="page-heading">
        <div>
          <div className="eyebrow">COMPUTE CONTROL</div>
          <h1>Workloads</h1>
          <p>Create workloads, review status history, and manage transitions.</p>
        </div>
        <button className="button button-primary" onClick={() => setCreateOpen(true)}>
          <Plus size={16} /> Create workload
        </button>
      </div>

      <div className="kpi-grid">
        <Card><span className="micro-label">TOTAL MATCHING API RECORDS</span><div className="kpi-value">{total}</div></Card>
        <Card><span className="micro-label">CURRENT PAGE</span><div className="kpi-value">{page} / {Math.max(pages, 1)}</div></Card>
        <Card><span className="micro-label">PAGE SIZE</span><div className="kpi-value">{pageSize}</div></Card>
      </div>

      <Card>
        <div className="section-heading">
          <div>
            <h2>Workload inventory</h2>
            <p className="muted-text">Searches this page only. Status filters are sent to the API.</p>
          </div>
          <button className="button button-secondary" onClick={() => setRefreshKey((v) => v + 1)}>
            <RefreshCw size={15} /> Refresh
          </button>
        </div>

        <div className="workload-toolbar">
          <label className="workload-search">
            <Search size={16} />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search this page by name" />
          </label>
          <label className="workload-page-size">
            <span>Rows</span>
            <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}>
              {[10, 20, 50].map((size) => <option key={size} value={size}>{size}</option>)}
            </select>
          </label>
        </div>

        <div className="workload-filters" aria-label="Filter workloads by status">
          <button className={filter === "all" ? "filter-chip active" : "filter-chip"} onClick={() => { setFilter("all"); setPage(1); }}>All</button>
          {statuses.map((status) => (
            <button key={status} className={filter === status ? "filter-chip active" : "filter-chip"} onClick={() => { setFilter(status); setPage(1); }}>
              {status.replace("_", " ")}
            </button>
          ))}
        </div>

        {loading ? <LoadingState label="Loading workloads" /> : error ? (
          <ErrorState detail={error} onRetry={() => setRefreshKey((v) => v + 1)} />
        ) : visibleItems.length === 0 ? (
          <EmptyState title={search ? "No matching workloads on this page" : "No workloads yet"} detail={search ? "Try another name or clear the search." : "Create a workload to begin using the real API-backed workflow."} />
        ) : (
          <DataTable headers={["Name", "Type", "Priority", "Status", "CPU", "Memory GB", "Max latency", "Carbon-aware", "Created"]}>
            {visibleItems.map((item) => (
              <tr key={item.id} className="workload-row" tabIndex={0} onClick={() => void loadDetail(item.id)} onKeyDown={(e) => { if (e.key === "Enter") void loadDetail(item.id); }}>
                <td><strong>{item.name}</strong><small className="table-subtext">ID {item.id}</small></td>
                <td>{item.workload_type.replace("_", " ")}</td>
                <td><Badge tone={tone(item.priority)}>{item.priority}</Badge></td>
                <td><Badge tone={tone(item.status)}>{item.status}</Badge></td>
                <td>{item.required_cpu_cores}</td>
                <td>{item.required_memory_gb}</td>
                <td>{item.max_latency_ms} ms</td>
                <td><Badge tone={item.carbon_aware ? "good" : "neutral"}>{item.carbon_aware ? "Yes" : "No"}</Badge></td>
                <td>{localTime(item.created_at)}</td>
              </tr>
            ))}
          </DataTable>
        )}

        <div className="workload-pagination">
          <span className="muted-text">{total} total records</span>
          <div>
            <button className="button button-secondary" disabled={page <= 1 || loading} onClick={() => setPage((v) => Math.max(1, v - 1))}>Previous</button>
            <span>Page {page} of {Math.max(pages, 1)}</span>
            <button className="button button-secondary" disabled={page >= pages || loading} onClick={() => setPage((v) => v + 1)}>Next</button>
          </div>
        </div>
      </Card>

      {createOpen && (
        <Modal title="Create workload" onClose={() => setCreateOpen(false)}>
          <form className="workload-form" onSubmit={(e) => void createWorkload(e)} noValidate>
            <label>Name<input className={fieldClass} maxLength={120} value={form.name} onChange={(e) => updateForm("name", e.target.value)} />{fieldErrors.name && <small className="field-error">{fieldErrors.name}</small>}</label>
            <div className="workload-form-grid">
              <label>Workload type<select className={fieldClass} value={form.workload_type} onChange={(e) => updateForm("workload_type", e.target.value as WorkloadType)}>{types.map((v) => <option key={v} value={v}>{v}</option>)}</select>{fieldErrors.workload_type && <small className="field-error">{fieldErrors.workload_type}</small>}</label>
              <label>Priority<select className={fieldClass} value={form.priority ?? "normal"} onChange={(e) => updateForm("priority", e.target.value as WorkloadPriority)}>{priorities.map((v) => <option key={v} value={v}>{v}</option>)}</select>{fieldErrors.priority && <small className="field-error">{fieldErrors.priority}</small>}</label>
              <label>CPU cores<input className={fieldClass} type="number" min={1} max={1024} step={1} value={form.required_cpu_cores} onChange={(e) => updateForm("required_cpu_cores", Number(e.target.value))} />{fieldErrors.required_cpu_cores && <small className="field-error">{fieldErrors.required_cpu_cores}</small>}</label>
              <label>Memory (GB)<input className={fieldClass} type="number" min={0.01} max={4096} step="any" value={form.required_memory_gb} onChange={(e) => updateForm("required_memory_gb", Number(e.target.value))} />{fieldErrors.required_memory_gb && <small className="field-error">{fieldErrors.required_memory_gb}</small>}</label>
              <label>Max latency (ms)<input className={fieldClass} type="number" min={0.01} max={60000} step="any" value={form.max_latency_ms} onChange={(e) => updateForm("max_latency_ms", Number(e.target.value))} />{fieldErrors.max_latency_ms && <small className="field-error">{fieldErrors.max_latency_ms}</small>}</label>
            </div>
            <label className="workload-checkbox"><input type="checkbox" checked={form.carbon_aware ?? true} onChange={(e) => updateForm("carbon_aware", e.target.checked)} /> Carbon-aware scheduling</label>
            {formError && <div className="form-error" role="alert">{formError}</div>}
            <div className="modal-actions"><button type="button" className="button button-secondary" onClick={() => setCreateOpen(false)}>Cancel</button><button className="button button-primary" disabled={saving}>{saving ? "Creating..." : "Create workload"}</button></div>
          </form>
        </Modal>
      )}

      {selectedId !== null && (
        <Drawer title={detail?.name ?? `Workload ${selectedId}`} onClose={closeDetail}>
          {detailLoading ? <LoadingState label="Loading workload details" /> : detailError ? <ErrorState detail={detailError} onRetry={() => void loadDetail(selectedId)} /> : detail ? (
            <div className="workload-detail">
              <div className="workload-detail-badges"><Badge tone={tone(detail.status)}>{detail.status}</Badge><Badge tone={tone(detail.priority)}>{detail.priority}</Badge></div>
              <div className="workload-detail-grid">
                <div><span>Type</span><strong>{detail.workload_type}</strong></div>
                <div><span>CPU cores</span><strong>{detail.required_cpu_cores}</strong></div>
                <div><span>Memory</span><strong>{detail.required_memory_gb} GB</strong></div>
                <div><span>Max latency</span><strong>{detail.max_latency_ms} ms</strong></div>
                <div><span>Carbon-aware</span><strong>{detail.carbon_aware ? "Yes" : "No"}</strong></div>
                <div><span>Created</span><strong>{localTime(detail.created_at)}</strong></div>
              </div>
              <div className="workload-detail-actions">
                <button className="button button-secondary" onClick={() => navigate(`/optimization?workload=${detail.id}`)}>Optimize <ArrowUpRight size={14} /></button>
                <button className="button button-secondary" onClick={() => navigate(`/optimization?workload=${detail.id}`)}>Schedule <ArrowUpRight size={14} /></button>
              </div>
              <h3>Transition status</h3>
              <form className="workload-form" onSubmit={(e) => void transition(e)}>
                <label>New status<select className={fieldClass} value={nextStatus} onChange={(e) => setNextStatus(e.target.value as WorkloadStatus)}>{statuses.map((v) => <option key={v} value={v}>{v}</option>)}</select></label>
                <label>Reason (optional)<textarea className={fieldClass} maxLength={2000} rows={3} value={reason} onChange={(e) => setReason(e.target.value)} /><small className="muted-text">{reason.length}/2000</small></label>
                {actionError && <div className="form-error" role="alert">{actionError}</div>}
                <button className="button button-primary" disabled={saving}>{saving ? "Updating..." : "Apply transition"}</button>
              </form>
              <h3>Status history</h3>
              {detail.history.length === 0 ? <p className="muted-text">No status history recorded yet.</p> : (
                <ol className="history-timeline">
                  {detail.history.map((entry) => (
                    <li key={entry.id}>
                      <strong>{entry.from_status} {"->"} {entry.to_status}</strong>
                      <time>{localTime(entry.changed_at)}</time>
                      {entry.reason && <p>{entry.reason}</p>}
                    </li>
                  ))}
                </ol>
              )}
              <button className="icon-button" aria-label="Close details" onClick={closeDetail}><X size={16} /> Close</button>
            </div>
          ) : null}
        </Drawer>
      )}
    </div>
  );
}