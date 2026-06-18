import { SimpleGrid } from "@chakra-ui/react";
import React, { useMemo } from "react";
import { Area, AreaChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
import { getWindowLabel } from "../../utils/meteringFormatters";
import type { MeteringGraph, ThroughputData } from "../../types/metering";
import {
  extractMeteringRateChartData,
  formatMeteringPeakAt,
} from "../../utils/meteringFormatters";
import MeteringChartPanel from "./MeteringChartPanel";
import MeteringSectionCard, { InlineMetricCard } from "./MeteringSectionCard";

interface ThroughputLoadSectionProps {
  throughput?: ThroughputData | null;
  window?: string;
  requestVolumeGraph?: MeteringGraph | null;
  /** Optional 4th metric label/value (e.g. tenant total requests). */
  fourthMetric?: { label: string; value: string; helper: string };
}

const ThroughputLoadSection: React.FC<ThroughputLoadSectionProps> = ({
  throughput,
  window = "24h",
  requestVolumeGraph,
  fourthMetric,
}) => {
  const windowLabel = getWindowLabel(window as "1h" | "24h" | "7d" | "30d");

  const chartData = useMemo(
    () => extractMeteringRateChartData(requestVolumeGraph, window),
    [requestVolumeGraph, window],
  );

  return (
    <MeteringSectionCard
      title="Throughput & load"
      subtitle={`Request rate over the selected window · ${windowLabel}`}
      sectionLabel
    >
      <SimpleGrid columns={{ base: 1, sm: 2, lg: 4 }} spacing={4} mb={6}>
        <InlineMetricCard
          label="Avg RPS"
          value={throughput?.avg_rps ?? "—"}
          helper="requests per second"
          accent="orange.600"
        />
        <InlineMetricCard
          label="Peak RPS"
          value={throughput?.peak_rps ?? "—"}
          helper="highest in window"
        />
        <InlineMetricCard
          label="Peak at"
          value={formatMeteringPeakAt(throughput?.peak_at)}
          helper="time bucket of peak load"
          valueSize="lg"
        />
        {fourthMetric ? (
          <InlineMetricCard
            label={fourthMetric.label}
            value={fourthMetric.value}
            helper={fourthMetric.helper}
          />
        ) : null}
      </SimpleGrid>

      <MeteringChartPanel
        height={260}
        minWidth={280}
        title="Request rate trend"
        hasData={chartData.length > 0}
        emptyMessage="Request rate trend is not available for the selected window."
      >
        {(size) => (
          <AreaChart width={size.width} height={size.height} data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="#A0AEC0" />
            <YAxis
              tick={{ fontSize: 11 }}
              stroke="#3182CE"
              tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(0)}K` : String(v))}
            />
            <Tooltip
              contentStyle={{
                background: "white",
                border: "1px solid #E2E8F0",
                borderRadius: "8px",
                fontSize: "12px",
              }}
              formatter={(value: number) => [`${value.toLocaleString()} req/s`, "RPS"]}
              labelFormatter={(label) => `Time: ${label}`}
            />
            <Area
              type="monotone"
              dataKey="rps"
              name="RPS"
              stroke="#3182CE"
              fill="#BEE3F8"
              fillOpacity={0.65}
              strokeWidth={2}
            />
          </AreaChart>
        )}
      </MeteringChartPanel>
    </MeteringSectionCard>
  );
};

export default ThroughputLoadSection;
