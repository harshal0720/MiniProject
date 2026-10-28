import { useCallback, useMemo, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip,
  XAxis, YAxis,
} from "recharts";
import { Activity, ArrowDown, ArrowUp, RefreshCw } from "lucide-react";
import { Badge, Card, EmptyState, ErrorState, Skeleton } from "../components/ui/primitives";
import { useApi } from "../hooks/useApi";
import { endpoints } from "../services/endpoints";
import type { CarbonReadingResponse, CloudRegionResponse } from "../types/api";

type SortKey =
  | "provider" | "region" | "carbon_intensity" | "renewable_energy_pct"
  | "estimated_cost_usd_per_kwh" | "latency_ms" | "updated_at";

interface RegionRow extends CloudRegionResponse {
  carbonUpdatedAt: string | null;
  freshness: "Fresh" | "Stale" | "Unavailable";
}

const VIOLET = "#a78bfa";
const CYAN = "#67e8f9";
const AXIS = "#8f879f";

function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "Unavailable";
  return value.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function formatTime(value: string | null): string {
  if (!value) return "Unavailable";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Unavailable" : date.toLocaleString();
}

function freshnessFor(reading: CarbonReadingResponse | undefined): RegionRow["freshness"] {
  if (!reading || !reading.updated_at) return "Unavailable";
  const timestamp = new Date(reading.updated_at).getTime();
  if (!Number.isFinite(timestamp)) return "Unavailable";
  return Date.now() - timestamp < 15 * 60 * 1000 ? "Fresh" : "Stale";
}

function FreshnessBadge({ value }: { value: RegionRow["freshness"] }) {
  const tone = value === "Fresh" ? "good" : value === "Stale" ? "warning" : "neutral";
  return <Badge tone={tone}>{value}</Badge>;
}

function ChartTooltip({
  active, payload, label, suffix,
}: {
  active?: boolean;
  payload?: Array<{ value?: number | string }>;
  label?: string;
  suffix: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="carbon-tooltip">
      <strong>{label}</strong>
      <span>{formatNumber(Number(payload[0].value))}{suffix}</span>
    </div>
  );
}

function RegionChart({
  title, data, dataKey, suffix, color,
}: {
  title: string;
  data: RegionRow[];
  dataKey: "carbon_intensity" | "renewable_energy_pct" | "estimated_cost_usd_per_kwh" | "latency_ms";
  suffix: string;
  color: string;
}) {
  return (
    <Card className="carbon-chart-card">
      <div className="carbon-chart-heading">
        <span className="micro-label">{title}</span>
        <span className="carbon-chart-dot" style={{ background: color }} />
      </div>
      <div className="carbon-chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 12, right: 8, left: -12, bottom: 24 }}>
            <CartesianGrid stroke="rgba(167,139,250,0.12)" vertical={false} />
            <XAxis
              dataKey="region"
              interval={0}
              angle={-16}
              textAnchor="end"
              height={54}
              tick={{ fill: AXIS, fontSize: 10 }}
              axisLine={{ stroke: "rgba(167,139,250,0.2)" }}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: AXIS, fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              width={48}
            />
            <Tooltip content={<ChartTooltip suffix={suffix} />} cursor={{ fill: "rgba(167,139,250,0.08)" }} />
            <Bar dataKey={dataKey} name={title} radius={[5, 5, 0, 0]} maxBarSize={42}>
              {data.map((row, index) => (
                <Cell key={`${row.id}-${index}`} fill={index % 2 === 0 ? color : CYAN} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

export function CarbonPage() {
  const regionsLoader = useCallback((_signal: AbortSignal) => endpoints.cloudRegions(), []);
  const carbonLoader = useCallback((_signal: AbortSignal) => endpoints.currentCarbon(), []);
  const regions = useApi<CloudRegionResponse[]>(regionsLoader);
  const carbon = useApi<CarbonReadingResponse[]>(carbonLoader);
  const [sortKey, setSortKey] = useState<SortKey>("provider");
  const [sortAsc, setSortAsc] = useState(true);

  const rows = useMemo<RegionRow[]>(() => {
    const readings = new Map((carbon.data ?? []).map((item) => [item.region_id, item]));
    return (regions.data ?? []).map((region) => {
      const reading = readings.get(region.id);
      return {
        ...region,
        carbonUpdatedAt: reading?.updated_at ?? null,
        freshness: freshnessFor(reading),
      };
    });
  }, [regions.data, carbon.data]);

  const sortedRows = useMemo(() => [...rows].sort((a, b) => {
    const left = a[sortKey];
    const right = b[sortKey];
    const result = typeof left === "number" && typeof right === "number"
      ? left - right
      : String(left ?? "").localeCompare(String(right ?? ""));
    return sortAsc ? result : -result;
  }), [rows, sortKey, sortAsc]);

  const loading = (regions.loading && !regions.data) || (carbon.loading && !carbon.data);
  const error = regions.error ?? carbon.error;
  const refresh = () => {
    regions.refetch();
    carbon.refetch();
  };

  const changeSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc((value) => !value);
    else {
      setSortKey(key);
      setSortAsc(true);
    }
  };

  const sortLabel = (key: SortKey, label: string) => (
    <button className="carbon-sort-button" onClick={() => changeSort(key)}>
      {label}
      {sortKey === key && (sortAsc ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}
    </button>
  );

  return (
    <div className="page-stack carbon-page">
      <div className="page-heading animate-enter">
        <div>
          <div className="eyebrow"><Activity size={15} /> SUSTAINABILITY SIGNALS</div>
          <h1>Carbon Intelligence</h1>
          <p>Compare regional carbon intensity, renewable energy, cost and latency.</p>
        </div>
        <button className="button button-secondary" onClick={refresh}>
          <RefreshCw size={15} /> Refresh
        </button>
      </div>

      <div className="carbon-demo-note">
        <strong>Illustrative demo data</strong>
        <span>Region values are illustrative demo data, not live provider telemetry.</span>
      </div>
      <p className="muted small">
        Freshness rule: fresh when updated less than 15 minutes ago; stale at 15 minutes or older;
        unavailable when no reading or timestamp exists.
      </p>

      {error && (
        <ErrorState
          title="Carbon data could not be loaded"
          detail={error.message}
          onRetry={refresh}
        />
      )}

      {loading && (
        <div className="carbon-chart-grid">
          {Array.from({ length: 4 }, (_, index) => (
            <Card className="carbon-chart-card" key={index}>
              <Skeleton className="carbon-skeleton-title" />
              <Skeleton className="carbon-skeleton-chart" />
            </Card>
          ))}
        </div>
      )}

      {!loading && !error && rows.length === 0 && (
        <EmptyState
          title="No cloud regions available"
          detail="The regions endpoint returned no records. Refresh after checking the backend."
        />
      )}

      {!loading && rows.length > 0 && (
        <>
          <div className="carbon-chart-grid">
            <RegionChart title="CARBON INTENSITY" data={rows} dataKey="carbon_intensity" suffix=" gCO2e/kWh" color={VIOLET} />
            <RegionChart title="RENEWABLE ENERGY" data={rows} dataKey="renewable_energy_pct" suffix="%" color={CYAN} />
            <RegionChart title="ESTIMATED COST" data={rows} dataKey="estimated_cost_usd_per_kwh" suffix=" USD/kWh" color={VIOLET} />
            <RegionChart title="REGION LATENCY" data={rows} dataKey="latency_ms" suffix=" ms" color={CYAN} />
          </div>

          <Card className="carbon-table-card">
            <div className="carbon-table-heading">
              <div>
                <h2>Regional comparison</h2>
                <p className="muted small">{rows.length} regions returned by the API</p>
              </div>
              <Badge tone="violet">Current snapshot</Badge>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{sortLabel("provider", "Provider")}</th>
                    <th>{sortLabel("region", "Region")}</th>
                    <th>{sortLabel("carbon_intensity", "Carbon intensity")}</th>
                    <th>{sortLabel("renewable_energy_pct", "Renewable %")}</th>
                    <th>{sortLabel("estimated_cost_usd_per_kwh", "Cost USD/kWh")}</th>
                    <th>{sortLabel("latency_ms", "Latency")}</th>
                    <th>{sortLabel("updated_at", "Last updated")}</th>
                    <th>Freshness</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedRows.map((row) => (
                    <tr key={row.id}>
                      <td>{row.provider}</td>
                      <td>{row.region}</td>
                      <td>{formatNumber(row.carbon_intensity, 1)} gCO2e/kWh</td>
                      <td>{formatNumber(row.renewable_energy_pct, 1)}%</td>
                      <td>${formatNumber(row.estimated_cost_usd_per_kwh, 4)}</td>
                      <td>{formatNumber(row.latency_ms, 0)} ms</td>
                      <td>{formatTime(row.carbonUpdatedAt)}</td>
                      <td><FreshnessBadge value={row.freshness} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}