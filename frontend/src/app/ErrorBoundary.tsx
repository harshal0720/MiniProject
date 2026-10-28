import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

export class ErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };
  static getDerivedStateFromError() { return { hasError: true }; }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error("GreenScale UI error:", error, info.componentStack); }
  render() {
    if (this.state.hasError) return <main className="fatal-state"><AlertTriangle size={28}/><h1>Something went wrong</h1><p>The interface hit an unexpected error.</p><button className="button button-primary" onClick={() => window.location.reload()}>Reload application</button></main>;
    return this.props.children;
  }
}