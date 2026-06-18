import type {
  MeteringGraph,
  MeteringWindow,
  OverviewResponse,
  ServiceConsumptionResponse,
  TenantConsumptionResponse,
} from "../types/metering";
import { formatCompactNumber, getWindowLabel } from "../utils/meteringFormatters";

export { getWindowLabel } from "../utils/meteringFormatters";

export function buildMeteringRequestVolumeSeries(window: MeteringWindow): MeteringGraph {
  const pointCount = window === "1h" ? 12 : window === "24h" ? 24 : window === "7d" ? 7 : 30;
  const now = Math.floor(Date.now() / 1000);
  const stepSecs = window === "1h" ? 300 : window === "24h" ? 3600 : 86400;

  const requestsPoints = Array.from({ length: pointCount }, (_, i) => {
    const base = 35000 + Math.sin(i * 0.8) * 12000 + (i % 3) * 4000;
    return {
      ts: now - (pointCount - 1 - i) * stepSecs,
      value: Math.round(base + Math.random() * 5000),
    };
  });

  const failurePoints = requestsPoints.map((p) => ({
    ts: p.ts,
    value: Number((1.5 + Math.sin(p.ts) * 0.8).toFixed(2)),
  }));

  return {
    step: window === "1h" ? "5m" : window === "24h" ? "1h" : "1d",
    series: [
      { key: "requests", label: "Requests", points: requestsPoints },
      { key: "failure_rate", label: "Failure rate %", points: failurePoints },
    ],
  };
}

const TOP_TENANTS = [
  { tenant: "Ministry of Electronics & IT (MeitY)", requests: 195800, pct: 18.97 },
  { tenant: "Ministry of Education", requests: 153600, pct: 14.88 },
  { tenant: "IIIT Hyderabad", requests: 76400, pct: 7.4 },
  { tenant: "Tamil Nadu e-Governance Agency", requests: 65600, pct: 6.35 },
  { tenant: "IIT Madras", requests: 54900, pct: 5.32 },
];

export const MOCK_PREVIEW_TENANTS = [
  { id: "1", organisation: "Ministry of Electronics & IT (MeitY)", plan: "Enterprise" as const },
  { id: "2", organisation: "Ministry of Education", plan: "Enterprise" as const },
  { id: "3", organisation: "IIIT Hyderabad", plan: "Pro" as const },
  { id: "4", organisation: "Tamil Nadu e-Governance Agency", plan: "Enterprise" as const },
  { id: "5", organisation: "CDAC Pune", plan: "Pro" as const },
  { id: "6", organisation: "IIT Madras", plan: "Enterprise" as const },
  { id: "7", organisation: "Indian Railways (CRIS)", plan: "Enterprise" as const },
  { id: "8", organisation: "UIDAI (Aadhaar)", plan: "Enterprise" as const },
];

export function getMockOverview(
  window: MeteringWindow,
  isPlatformAdmin: boolean,
  organisation?: string | null,
): OverviewResponse {
  const chart = buildMeteringRequestVolumeSeries(window);

  if (!isPlatformAdmin) {
    return {
      scope: {
        role: "tenant_admin",
        tenant_id: "12",
        organisation: organisation ?? "IIIT Hyderabad",
        window,
      },
      kpis: [
        { key: "total_requests", label: "Total requests", value: "70.0K", pct_change: 4.2 },
        { key: "success_rate", label: "Success rate", value: "98.1%", pct_change: 0.3 },
        { key: "avg_rps", label: "Avg RPS (req/s)", value: "0.81", pct_change: 4.2 },
      ],
      active_tenants: [],
      request_volume: chart,
      throughput: { avg_rps: 0.81, peak_rps: 2.4, peak_at: "2026-06-18T10:30:00Z" },
      generated_at: new Date().toISOString(),
    };
  }

  return {
    scope: {
      role: "admin",
      tenant_id: null,
      organisation: null,
      window,
    },
    kpis: [
      { key: "total_requests", label: "Total requests", value: "1.03M", pct_change: 15.0 },
      { key: "success_rate", label: "Success rate", value: "97.56%", pct_change: 0.2 },
      { key: "avg_rps", label: "Avg RPS (req/s)", value: "11.953", pct_change: 15.0 },
      { key: "avg_requests_per_tenant", label: "Avg requests per tenant", value: "33.3K", pct_change: 15.0 },
    ],
    active_tenants: [
      { key: "active_24h", label: "Active tenants", value: 31 },
      { key: "active_7d", label: "Active tenants", value: 38 },
      { key: "active_30d", label: "Active tenants", value: 44 },
    ],
    platform_adoption: {
      total_tenants: 47,
      new_tenants_7d: 3,
      active_24h: 31,
      active_7d: 38,
      active_30d: 44,
    },
    usage_concentration: {
      top_tenants: TOP_TENANTS.map((t, i) => ({
        rank: i + 1,
        tenant: t.tenant,
        requests: t.requests,
        formatted_requests: `${(t.requests / 1000).toFixed(1)}K`,
        percentage: t.pct,
      })),
      others: { count: 42, requests: 447600, percentage: 47.21 },
      top_concentration_pct: 52.79,
      grand_total: 1030000,
    },
    request_volume: chart,
    throughput: { avg_rps: 10.972, peak_rps: 18.4, peak_at: "2026-06-18T14:00:00Z" },
    generated_at: new Date().toISOString(),
  };
}

export function getMockTenantConsumption(window: MeteringWindow): TenantConsumptionResponse {
  const tenants = [
    ...TOP_TENANTS,
    { tenant: "Bhashini", requests: 45200, pct: 4.77 },
    { tenant: "CDAC Pune", requests: 38100, pct: 4.02 },
    { tenant: "IIT Bombay", requests: 32000, pct: 3.38 },
    { tenant: "NIELIT", requests: 28500, pct: 3.01 },
    { tenant: "NIC", requests: 24100, pct: 2.54 },
  ];

  const serviceDefs: { key: string; display_name: string; weight: number }[] = [
    { key: "nmt", display_name: "NMT", weight: 0.226 },
    { key: "asr", display_name: "ASR", weight: 0.16 },
    { key: "tts", display_name: "TTS", weight: 0.128 },
    { key: "llm", display_name: "LLM", weight: 0.115 },
    { key: "ocr", display_name: "OCR", weight: 0.095 },
    { key: "transliteration", display_name: "Transliteration", weight: 0.08 },
    { key: "pipeline", display_name: "Pipeline", weight: 0.065 },
    { key: "ner", display_name: "NER", weight: 0.05 },
    { key: "language_detection", display_name: "Language Detection", weight: 0.035 },
    { key: "audio_language_detection", display_name: "Audio Language Detection", weight: 0.028 },
    { key: "speaker_diarization", display_name: "Speaker Diarization", weight: 0.018 },
  ];

  const buildServices = (total: number, rowIndex: number) => {
    const rowScale = Math.max(0.35, 1 - rowIndex * 0.07);
    const services: TenantConsumptionResponse["usage_by_service"][number]["services"] = {};
    serviceDefs.forEach((svc, svcIndex) => {
      const variance = 0.9 + ((rowIndex + svcIndex) % 5) * 0.05;
      const requests = Math.max(0, Math.round(total * svc.weight * rowScale * variance));
      services[svc.key] = {
        display_name: svc.display_name,
        requests,
        formatted_requests: formatCompactNumber(requests),
      };
    });
    return services;
  };

  return {
    scope: { role: "admin", tenant_id: null, organisation: null, window },
    tenant_ranking: tenants.map((t, i) => ({
      rank: i + 1,
      tenant: t.tenant,
      requests: t.requests,
      formatted_requests: `${(t.requests / 1000).toFixed(1)}K`,
      percentage: t.pct,
    })),
    usage_by_service: tenants.slice(0, 10).map((t, i) => ({
      rank: i + 1,
      tenant: t.tenant,
      organisation: t.tenant,
      services: buildServices(t.requests, i),
      total: t.requests,
      formatted_total: `${(t.requests / 1000).toFixed(1)}K`,
    })),
    throughput: { avg_rps: 11.953, peak_rps: 18.4, peak_at: "H-3" },
    generated_at: new Date().toISOString(),
  };
}

export function getMockServiceConsumption(
  window: MeteringWindow,
  isPlatformAdmin: boolean,
  organisation?: string | null,
): ServiceConsumptionResponse {
  const services = isPlatformAdmin
    ? [
        { service: "NMT", unit: "Characters translated", requests: 235100, native: 4.24, suffix: "Cr chars", success: 98.04, failed: 4608 },
        { service: "ASR", unit: "Audio minutes processed", requests: 184400, native: 9.24, suffix: "L min", success: 96.99, failed: 5548 },
        { service: "TTS", unit: "Characters synthesized", requests: 143000, native: 2.14, suffix: "Cr chars", success: 97.41, failed: 3704 },
        { service: "LLM", unit: "Tokens processed", requests: 132600, native: 0.95, suffix: "Cr tokens", success: 96.14, failed: 5118 },
        { service: "OCR", unit: "Images processed", requests: 102000, native: 2.14, suffix: "L images", success: 99.02, failed: 1000 },
        { service: "Transliteration", unit: "Characters processed", requests: 81500, native: 1.63, suffix: "Cr chars", success: 98.72, failed: 1043 },
        { service: "Pipeline", unit: "Jobs executed", requests: 60800, native: 60.8, suffix: "L jobs", success: 94.82, failed: 3150 },
        { service: "NER", unit: "Tokens processed", requests: 50400, native: 0.76, suffix: "Cr tokens", success: 97.55, failed: 1235 },
        { service: "Language Detection", unit: "Jobs executed", requests: 17900, native: 17.9, suffix: "L jobs", success: 99.12, failed: 158 },
        { service: "Audio Language Detection", unit: "Jobs executed", requests: 11700, native: 11.7, suffix: "L jobs", success: 98.45, failed: 181 },
        { service: "Speaker Diarization", unit: "Audio minutes processed", requests: 9700, native: 0.58, suffix: "L min", success: 96.18, failed: 370 },
      ]
    : [
        { service: "NMT", unit: "Characters translated", requests: 24500, native: 3.8, suffix: "M chars", success: 98.5, failed: 368 },
        { service: "ASR", unit: "Audio minutes processed", requests: 18200, native: 1140, suffix: "min", success: 97.1, failed: 528 },
        { service: "TTS", unit: "Characters synthesized", requests: 14100, native: 2.0, suffix: "M chars", success: 98.0, failed: 282 },
        { service: "LLM", unit: "Tokens processed", requests: 8200, native: 58, suffix: "M tokens", success: 96.2, failed: 312 },
        { service: "OCR", unit: "Images processed", requests: 5000, native: 1050, suffix: "images", success: 99.3, failed: 35 },
      ];

  return {
    scope: {
      role: isPlatformAdmin ? "admin" : "tenant_admin",
      tenant_id: isPlatformAdmin ? null : "12",
      organisation: isPlatformAdmin ? null : organisation ?? "IIIT Hyderabad",
      window,
    },
    service_breakdown: services.map((s) => ({
      service: s.service,
      metering_unit: s.unit,
      requests: s.requests,
      native_units: s.native,
      native_unit_suffix: s.suffix,
      success_pct: s.success,
      failed: s.failed,
      vs_prev_period_pct: Number((Math.random() * 10 - 2).toFixed(1)),
    })),
    throughput: {
      avg_rps: isPlatformAdmin ? 10.972 : 0.81,
      peak_rps: isPlatformAdmin ? 18.4 : 2.4,
      peak_at: "2026-06-18T14:00:00Z",
    },
    request_volume: buildMeteringRequestVolumeSeries(window),
    generated_at: new Date().toISOString(),
  };
}
