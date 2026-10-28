import { useCallback } from "react";
import { usePolling } from "../../hooks/useApi";
import { endpoints } from "../../services/endpoints";
import type { HealthSummaryResponse } from "../../types/api";
import {
  deriveSystemStatus,
  type ApiHealthSnapshot,
} from "./deriveSystemStatus";

export function useSystemStatus() {
  const apiLoader = useCallback(
    (_signal: AbortSignal) => endpoints.health(),
    [],
  );
  const monitorLoader = useCallback(
    (_signal: AbortSignal) => endpoints.monitorHealth(),
    [],
  );

  const apiHealth = usePolling<ApiHealthSnapshot>(apiLoader, 20000);
  const monitoring = usePolling<HealthSummaryResponse>(monitorLoader, 20000);

  const derived = deriveSystemStatus({
    apiLoading: apiHealth.loading,
    apiError: apiHealth.error,
    apiData: apiHealth.data,
    monitorLoading: monitoring.loading,
    monitorError: monitoring.error,
    monitorData: monitoring.data,
  });

  const refresh = () => {
    apiHealth.refetch();
    monitoring.refetch();
  };

  return {
    ...derived,
    monitoring,
    refresh,
  };
}

export type SystemStatusState = ReturnType<typeof useSystemStatus>;