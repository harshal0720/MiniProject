import { useEffect, useState } from "react";
import {
  Activity, ChevronLeft, ChevronRight, Cloud, Gauge, Leaf, Menu,
  Network, Sparkles, X,
} from "lucide-react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { ToastViewport, type ToastMessage } from "../components/ui/primitives";
import { useSystemStatus } from "../features/system/useSystemStatus";
import { CommandCenter } from "../pages/CommandCenter";
import { NotFoundPage } from "../pages/NotFoundPage";
import { PlaceholderPage } from "../pages/PlaceholderPage";
import { WorkloadsPage } from "../pages/WorkloadsPage";
import { CarbonPage } from "../pages/CarbonPage";

const navItems = [
  { to: "/", label: "Command Center", icon: Gauge, end: true },
  { to: "/workloads", label: "Workloads", icon: Network },
  { to: "/carbon", label: "Carbon Intelligence", icon: Leaf },
  { to: "/observability", label: "Observability", icon: Activity },
  { to: "/optimization", label: "AI Optimization", icon: Sparkles },
];

function statusDotClass(tone: string): string {
  if (tone === "good") return "status-good";
  if (tone === "bad") return "status-bad";
  if (tone === "warning") return "status-warning";
  return "status-wait";
}

export function AppShell() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const location = useLocation();
  const system = useSystemStatus();

  useEffect(() => setMobileOpen(false), [location.pathname]);

  const dismissToast = (id: number) => {
    setToasts((items) => items.filter((item) => item.id !== id));
  };

  const totalAlerts = system.monitoring.data
    ? Object.values(system.monitoring.data.open_alerts_by_severity ?? {})
        .reduce((sum, count) => sum + count, 0)
    : null;

  const currentNav = [...navItems]
    .sort((a, b) => b.to.length - a.to.length)
    .find((item) => item.to === "/"
      ? location.pathname === "/"
      : location.pathname.startsWith(item.to));

  return (
    <div className="app-frame">
      {mobileOpen && <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}
      <aside className={`sidebar ${collapsed ? "sidebar-collapsed" : ""} ${mobileOpen ? "sidebar-mobile-open" : ""}`}>
        <div className="brand-row">
          <div className="brand-symbol"><Cloud size={21} /></div>
          {!collapsed && <div className="brand-copy"><strong>GreenScale<span> AI</span></strong><small>CLOUD OPERATIONS</small></div>}
          <button className="icon-button mobile-close" aria-label="Close navigation" onClick={() => setMobileOpen(false)}><X size={18} /></button>
        </div>

        <div className="nav-caption">{!collapsed && "PLATFORM"}</div>
        <nav aria-label="Main navigation" className="main-nav">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} title={collapsed ? label : undefined}
              className={({ isActive }) => `nav-link ${isActive ? "nav-active" : ""}`}>
              <Icon size={18} />
              {!collapsed && <span>{label}</span>}
              {!collapsed && to === "/observability" && <span className="nav-count">{totalAlerts ?? "\u2014"}</span>}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="sidebar-status" title={system.reason}>
            <span className={`status-dot ${statusDotClass(system.tone)}`} />
            {!collapsed && <div><strong>{system.label}</strong><small>{system.reason}</small></div>}
          </div>
          <button className="collapse-button" onClick={() => setCollapsed((value) => !value)}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
            {collapsed ? <ChevronRight size={17} /> : <><ChevronLeft size={17} /><span>Collapse sidebar</span></>}
          </button>
        </div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setMobileOpen(true)}><Menu size={20} /></button>
          <div className="breadcrumbs"><span>GREENSCALE /</span><strong>{currentNav?.label ?? "Not found"}</strong></div>
          <div className="topbar-actions">
            <div className="system-chip" title={system.reason} aria-label={`System status: ${system.label}. ${system.reason}`}>
              <span className={`status-dot ${statusDotClass(system.tone)}`} /><span>{system.label}</span>
            </div>
            <button className="icon-button" aria-label="Refresh system health" title="Refresh system health" onClick={system.refresh}><Activity size={17} /></button>
          </div>
        </header>

        <main className="page-content">
          <Routes>
            <Route path="/" element={<CommandCenter system={system} />} />
            <Route path="/workloads" element={<WorkloadsPage />} />

            <Route path="/carbon" element={<CarbonPage />} />
            <Route path="/observability" element={<PlaceholderPage title="Observability" eyebrow="SYSTEM SIGNALS" description="Monitoring health, regional utilization, workloads and alerts." icon={<Activity size={20} />} endpoint="/api/monitor/health" />} />
            <Route path="/optimization" element={<PlaceholderPage title="AI Optimization" eyebrow="PLACEMENT INTELLIGENCE" description="Optimization and scheduling controls will be connected in the next implementation stage." icon={<Sparkles size={20} />} endpoint="/api/optimize" />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </main>
      </div>
      <ToastViewport toasts={toasts} dismiss={dismissToast} />
    </div>
  );
}
