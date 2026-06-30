import React, { useMemo } from "react";
import { XAxis } from "recharts";

interface MeteringChartTimeAxisProps {
  stroke: string;
  data: ReadonlyArray<{ label: string }>;
}

interface MeteringChartTimeAxisTickProps {
  x?: number;
  y?: number;
  index?: number;
  stroke: string;
  labels: ReadonlyArray<string>;
}

const MeteringChartTimeAxisTick: React.FC<MeteringChartTimeAxisTickProps> = ({
  x = 0,
  y = 0,
  index,
  stroke,
  labels,
}) => {
  const label = index != null ? labels[index] : undefined;
  if (!label) return <g />;
  return (
    <text x={x} y={y} dy={12} textAnchor="middle" fill={stroke} fontSize={11}>
      {label}
    </text>
  );
};

/** Sparse x-axis ticks — only renders labels where `label` is non-empty. */
const MeteringChartTimeAxis: React.FC<MeteringChartTimeAxisProps> = ({ stroke, data }) => {
  const labels = useMemo(() => data.map((point) => point.label), [data]);

  return (
    <XAxis
      dataKey="ts"
      stroke={stroke}
      tickLine={false}
      tick={<MeteringChartTimeAxisTick stroke={stroke} labels={labels} />}
    />
  );
};

export default MeteringChartTimeAxis;
