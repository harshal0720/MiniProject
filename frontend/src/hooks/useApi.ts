import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../services/api";

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: ApiError | Error | null;
  refetch: () => void;
}
export function useApi<T>(loader: (signal: AbortSignal) => Promise<T>, pollMs?: number): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [revision, setRevision] = useState(0);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const refetch = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    let alive = true;
    let interval: number | undefined;
    const controller = new AbortController();
    const run = async () => {
      if (alive) { setLoading(true); setError(null); }
      try {
        const result = await loaderRef.current(controller.signal);
        if (alive) { setData(result); setError(null); }
      } catch (reason) {
        if (!alive || (reason instanceof DOMException && reason.name === "AbortError")) return;
        setError(reason instanceof Error ? reason : new Error("Unexpected error"));
      } finally {
        if (alive) setLoading(false);
      }
    };
    void run();
    if (pollMs && pollMs > 0) interval = window.setInterval(() => { void run(); }, pollMs);
    return () => {
      alive = false;
      controller.abort();
      if (interval !== undefined) window.clearInterval(interval);
    };
  }, [revision, pollMs]);
  return { data, loading, error, refetch };
}
export const useAsync = useApi;
export function usePolling<T>(loader: (signal: AbortSignal) => Promise<T>, intervalMs = 30000): AsyncState<T> {
  return useApi(loader, intervalMs);
}