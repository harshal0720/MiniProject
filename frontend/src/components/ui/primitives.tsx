import { useEffect, useState, type ReactNode } from "react";
import { AlertTriangle, Check, Info, LoaderCircle, X } from "lucide-react";

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={`glass-card ${className}`}>{children}</section>;
}

export type BadgeTone =
  | "neutral"
  | "good"
  | "warning"
  | "critical"
  | "bad"
  | "violet"
  | "cyan";

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: BadgeTone;
}) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />;
}

export function EmptyState({
  title,
  detail,
}: {
  title: string;
  detail: string;
}) {
  return (
    <div className="state-panel">
      <Info size={20} />
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  );
}

export function ErrorState({
  title = "Unable to load data",
  detail,
  onRetry,
}: {
  title?: string;
  detail: string;
  onRetry?: () => void;
}) {
  return (
    <div className="state-panel state-error" role="alert">
      <AlertTriangle size={20} />
      <strong>{title}</strong>
      <p>{detail}</p>
      {onRetry && (
        <button className="button button-secondary" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export type KpiTone = "violet" | "cyan" | "good" | "warning" | "bad";

export function KpiCard({
  label,
  value,
  detail,
  tone = "violet",
}: {
  label: string;
  value: string | number;
  detail?: string;
  tone?: KpiTone;
}) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const frame = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  return (
    <Card className="kpi-card">
      <div className="kpi-top">
        <span className="micro-label">{label}</span>
        <span className={`kpi-mark mark-${tone}`} />
      </div>
      <div className={`kpi-value ${visible ? "kpi-value-in" : ""}`}>
        {value}
      </div>
      {detail && <p className="muted small">{detail}</p>}
    </Card>
  );
}

export interface ToastMessage {
  id: number;
  title: string;
  detail?: string;
  tone?: "good" | "warning" | "critical";
}

export function ToastViewport({
  toasts,
  dismiss,
}: {
  toasts: ToastMessage[];
  dismiss: (id: number) => void;
}) {
  return (
    <div className="toast-viewport" aria-live="polite">
      {toasts.map((toast) => (
        <div
          className={`toast toast-${toast.tone ?? "good"}`}
          key={toast.id}
        >
          <Check size={17} />
          <div>
            <strong>{toast.title}</strong>
            {toast.detail && <p>{toast.detail}</p>}
          </div>
          <button
            aria-label="Dismiss notification"
            onClick={() => dismiss(toast.id)}
          >
            <X size={16} />
          </button>
        </div>
      ))}
    </div>
  );
}

export function LoadingState({ label = "Loading data" }: { label?: string }) {
  return (
    <div className="loading-state">
      <LoaderCircle className="spin" size={18} />
      {label}
    </div>
  );
}

export function DataTable({
  headers,
  children,
}: {
  headers: string[];
  children: ReactNode;
}) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {headers.map((header) => (
              <th key={header} scope="col">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className="modal-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
      >
        <div className="modal-heading">
          <h2 id="modal-title">{title}</h2>
          <button
            className="icon-button"
            onClick={onClose}
            aria-label="Close dialog"
          >
            <X size={18} />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}

export const Drawer = Modal;