import React from "react";
import { XAxis } from "recharts";

interface MeteringChartTimeAxisProps {
  stroke: string;
  data: ReadonlyArray<{ label: string }>;
}

/** Sparse x-axis ticks — only renders labels where `label` is non-empty. */
const MeteringChartTimeAxis: React.FC<MeteringChartTimeAxisProps> = ({ stroke, data }) => (
  <XAxis
    dataKey="ts"
    stroke={stroke}
    tickLine={false}
    tick={({ x, y, index }) => {
      const label = data[index]?.label;
      if (!label) return <g />;
      return (
        <text x={x} y={y} dy={12} textAnchor="middle" fill={stroke} fontSize={11}>
          {label}
        </text>
      );
    }}
  />
);

export default MeteringChartTimeAxis;
