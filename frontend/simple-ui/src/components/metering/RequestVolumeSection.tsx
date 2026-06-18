import { SimpleGrid, useColorModeValue } from "@chakra-ui/react";
import React, { useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { MeteringGraph, RequestHealth } from "../../types/metering";
import {
  extractMeteringRequestsSeries,
  formatCompactNumber,
  formatMeteringTimestamp,
  formatSuccessRateDisplay,
  parseCompactTotal,
  parseSuccessRatePct,
} from "../../utils/meteringFormatters";
import MeteringChartPanel from "./MeteringChartPanel";
import MeteringSectionCard, { SummaryMetricCard } from "./MeteringSectionCard";

interface RequestVolumeSectionProps {
  graph?: MeteringGraph | null;
  requestHealth?: RequestHealth | null;
  totalRequests?: string | number | null;
  successRate?: string | number | null;
}

const RequestVolumeSection: React.FC<RequestVolumeSectionProps> = ({
  graph,
  requestHealth,
  totalRequests,
  successRate,
}) => {
  const gridColor = useColorModeValue("#E2E8F0", "#4A5568");
  const tooltipBg = useColorModeValue("white", "gray.700");

  const failureSeries = graph?.series?.find((s) => s.key === "failure_rate");

  const chartData = useMemo(() => {
    const requestsSeries = extractMeteringRequestsSeries(graph);
    if (!requestsSeries?.points?.length || !graph) return [];

    return requestsSeries.points.map((p, i) => ({
      label: formatMeteringTimestamp(p.ts, graph.step),
      requests: p.value,
      failureRate: failureSeries?.points[i]?.value ?? 0,
    }));
  }, [graph, failureSeries]);

  const total = requestHealth?.total_formatted ?? totalRequests ?? "—";
  const successPct = requestHealth?.success_rate_pct ?? parseSuccessRatePct(successRate);
  const rateDisplay = requestHealth
    ? `${requestHealth.success_rate_pct.toFixed(2)}%`
    : formatSuccessRateDisplay(successRate);
  const failedPct = requestHealth
    ? `${requestHealth.failure_rate_pct.toFixed(2)}%`
    : successPct != null
      ? `${(100 - successPct).toFixed(2)}%`
      : "—";

  const successfulValue = requestHealth?.successful_formatted ?? (() => {
    const totalNum = parseCompactTotal(totalRequests ?? total);
    return totalNum != null && successPct != null
      ? formatCompactNumber(totalNum * (successPct / 100))
      : "—";
  })();

  const failedValue = requestHealth?.failed_formatted ?? (() => {
    const totalNum = parseCompactTotal(totalRequests ?? total);
    return totalNum != null && successPct != null
      ? formatCompactNumber(totalNum * ((100 - successPct) / 100))
      : "—";
  })();

  const hasFailureSeries = Boolean(failureSeries?.points?.length);
  const yAxisLabel = hasFailureSeries ? "REQUESTS" : "RPS";

  return (
    <MeteringSectionCard
      title="Request volume & health"
      subtitle={
        hasFailureSeries
          ? "Total requests and failure rate over the selected period"
          : "Request rate (RPS) over the selected period"
      }
      sectionLabel
      bare
    >
      <SimpleGrid columns={{ base: 1, md: 3 }} spacing={4} mb={6}>
        <SummaryMetricCard label="Total requests" value={String(total)} leftBorderColor="gray.700" />
        <SummaryMetricCard
          label="Successful"
          value={successfulValue}
          helper={`${rateDisplay} success rate`}
          leftBorderColor="green.400"
          helperColor="green.600"
        />
        <SummaryMetricCard
          label="Failed"
          value={failedValue}
          helper={`${failedPct} failure rate`}
          leftBorderColor="orange.400"
          helperColor="orange.500"
        />
      </SimpleGrid>

      <MeteringChartPanel height={340} hasData={chartData.length > 0}>
        {(size) => (
          <ComposedChart
            width={size.width}
            height={size.height}
            data={chartData}
            margin={{ top: 8, right: hasFailureSeries ? 48 : 16, left: 8, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="#A0AEC0" />
            <YAxis
              yAxisId="requests"
              tick={{ fontSize: 11 }}
              stroke="#3182CE"
              tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(0)}K` : String(v))}
              label={{
                value: yAxisLabel,
                angle: -90,
                position: "insideLeft",
                style: { fontSize: 10, fill: "#3182CE", fontWeight: 600 },
              }}
            />
            {hasFailureSeries ? (
              <YAxis
                yAxisId="failure"
                orientation="right"
                tick={{ fontSize: 11 }}
                stroke="#E53E3E"
                tickFormatter={(v) => `${v}%`}
                domain={[0, 10]}
                label={{
                  value: "FAILURE RATE %",
                  angle: 90,
                  position: "insideRight",
                  style: { fontSize: 10, fill: "#E53E3E", fontWeight: 600 },
                }}
              />
            ) : null}
            <Tooltip
              contentStyle={{
                background: tooltipBg,
                border: "1px solid #E2E8F0",
                borderRadius: "8px",
                fontSize: "12px",
              }}
              formatter={(value: number, name: string) => [
                hasFailureSeries || name !== "Requests"
                  ? value
                  : `${value.toLocaleString()} req/s`,
                name,
              ]}
            />
            <Area
              yAxisId="requests"
              type="monotone"
              dataKey="requests"
              name={hasFailureSeries ? "Requests" : "RPS"}
              stroke="#3182CE"
              fill="#BEE3F8"
              fillOpacity={0.6}
              strokeWidth={2}
            />
            {hasFailureSeries ? (
              <Line
                yAxisId="failure"
                type="monotone"
                dataKey="failureRate"
                name="Failure rate %"
                stroke="#E53E3E"
                strokeWidth={2}
                dot={false}
              />
            ) : null}
          </ComposedChart>
        )}
      </MeteringChartPanel>
    </MeteringSectionCard>
  );
};

export default RequestVolumeSection;
