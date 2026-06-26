import React, { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { METERING } from "../../config/meteringConstants";
import { useMeteringChartColors } from "../../hooks/useMeteringChartColors";
import type { MeteringGraph } from "../../types/metering";
import { buildRequestVolumeChartData } from "../../utils/meteringFormatters";
import MeteringChartPanel from "./MeteringChartPanel";
import MeteringSectionCard from "./MeteringSectionCard";

interface RequestVolumeSectionProps {
  graph?: MeteringGraph | null;
}

/**
 * Compact Y-axis tick label: 700 → "700", 350000 → "350K", 1000000 → "1M",
 * 1500000 → "1.5M". The axis range itself is auto-scaled by Recharts to the
 * data; this only controls how the (already dynamic) tick values are rendered
 * so large aggregated volumes read as compact units per the design.
 */
const formatRequestAxisTick = (v: number): string => {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1).replace(/\.0$/, "")}K`;
  return String(v);
};

const RequestVolumeSection: React.FC<RequestVolumeSectionProps> = ({ graph }) => {
  const colors = useMeteringChartColors();
  const section = METERING.SECTIONS.REQUEST_VOLUME;

  const chartData = useMemo(() => buildRequestVolumeChartData(graph), [graph]);

  return (
    <MeteringSectionCard
      title={section.TITLE}
      subtitle={section.SUBTITLE}
      sectionLabel
      bare
    >
      <MeteringChartPanel height={340} hasData={chartData.length > 0}>
        {(size) => (
          <BarChart
            width={size.width}
            height={size.height}
            data={chartData}
            margin={{ top: 8, right: 16, left: 8, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke={colors.axis} />
            <YAxis
              tick={{ fontSize: 11 }}
              stroke={colors.primaryStroke}
              tickFormatter={formatRequestAxisTick}
              label={{
                value: section.Y_AXIS_REQUESTS,
                angle: -90,
                position: "insideLeft",
                style: { fontSize: 10, fill: colors.primaryStroke, fontWeight: 600 },
              }}
            />
            <Tooltip
              contentStyle={{
                background: colors.tooltipBg,
                border: `1px solid ${colors.tooltipBorder}`,
                borderRadius: "8px",
                fontSize: "12px",
              }}
              formatter={(value: number, name: string) => [value.toLocaleString(), name]}
            />
            <Legend wrapperStyle={{ fontSize: "12px" }} />
            <Bar
              dataKey="successful"
              name={section.SERIES_SUCCESSFUL}
              stackId="requests"
              fill={colors.primaryStroke}
              radius={[0, 0, 0, 0]}
            />
            <Bar
              dataKey="failed"
              name={section.SERIES_FAILED}
              stackId="requests"
              fill={colors.failureStroke}
              radius={[2, 2, 0, 0]}
            />
          </BarChart>
        )}
      </MeteringChartPanel>
    </MeteringSectionCard>
  );
};

export default RequestVolumeSection;
