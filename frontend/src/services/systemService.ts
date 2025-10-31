import http from "./http";

export interface HealthStatus {
  status: string;
  version: string;
  timestamp: string;
  dependencies: Record<string, string>;
}

export const fetchHealth = async (): Promise<HealthStatus> => {
  const { data } = await http.get<HealthStatus>("/health");
  return data;
};
