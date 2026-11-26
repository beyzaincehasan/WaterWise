import type {
  AnomalyDetectRequest,
  AnomalyLogItem,
  AnomalyPredictionResponse,
  ApartmentListItem,
  ApartmentStatsResponse,
  DailyConsumptionItem,
  DemoSimulateRequest,
  DemoSimulateResponse,
  FixtureBreakdownItem,
  HealthResponse,
} from './types';

const BASE_URL: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000';

type QueryValue = string | number | boolean | null | undefined;

function buildQuery(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '') {
      search.set(key, String(value));
    }
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    });
  } catch {
    throw new Error('Backend’e ulaşılamadı. Sunucunun 8000 portunda çalıştığından emin ol.');
  }

  if (!response.ok) {
    let message = `İstek başarısız oldu (${response.status})`;
    try {
      const body: unknown = await response.json();
      if (body && typeof body === 'object') {
        const record = body as Record<string, unknown>;
        const detail = record.detail ?? record.error;
        if (typeof detail === 'string') message = detail;
        else if (detail) message = JSON.stringify(detail);
      }
    } catch {
      /* gövde JSON değil, varsayılan mesaj kalsın */
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
}

const apt = (id: string) => `/api/v1/apartments/${encodeURIComponent(id)}`;

export const api = {
  health: () => request<HealthResponse>('/health'),

  apartments: () => request<ApartmentListItem[]>('/api/v1/apartments'),

  stats: (id: string) => request<ApartmentStatsResponse>(`${apt(id)}/stats`),

  dailyConsumption: (id: string, startDate?: string, endDate?: string) =>
    request<DailyConsumptionItem[]>(
      `${apt(id)}/daily-consumption${buildQuery({ start_date: startDate, end_date: endDate })}`,
    ),

  fixtureBreakdown: (id: string, startDate?: string, endDate?: string) =>
    request<FixtureBreakdownItem[]>(
      `${apt(id)}/fixture-breakdown${buildQuery({ start_date: startDate, end_date: endDate })}`,
    ),

  evaluateRange: (id: string, startTime: string, endTime: string) =>
    request<AnomalyPredictionResponse[]>(
      `${apt(id)}/evaluate-range${buildQuery({ start_time: startTime, end_time: endTime })}`,
    ),

  anomalies: (params: {
    apartmentId?: string;
    status?: 'Anormal' | 'Şüpheli';
    limit?: number;
  }) =>
    request<AnomalyLogItem[]>(
      `/api/v1/anomalies${buildQuery({
        apartment_id: params.apartmentId,
        status: params.status,
        limit: params.limit ?? 50,
      })}`,
    ),

  detect: (body: AnomalyDetectRequest) =>
    request<AnomalyPredictionResponse>('/api/v1/anomalies/detect', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  simulateDemo: (body: DemoSimulateRequest) =>
    request<DemoSimulateResponse>('/api/v1/anomalies/simulate-demo', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
};
