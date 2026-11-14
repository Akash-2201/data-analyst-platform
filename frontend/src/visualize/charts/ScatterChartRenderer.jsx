/**
 * frontend/src/visualize/charts/ScatterChartRenderer.jsx
 * Custom Power BI-style Scatter Plot renderer.
 */

import React, { useMemo } from "react";
import {
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import { PALETTES } from "../constants";

export function ScatterChartRenderer({
  data,
  format = {},
  chartConfig = {},
  crossFilter = null,
  onPointClick = null,
  isInteractive = false,
}) {
  const chartData = useMemo(() => {
    if (!data || !Array.isArray(data.labels) || !Array.isArray(data.values)) {
      return [];
    }
    return data.labels.map((label, idx) => {
      const numX = parseFloat(label);
      const xVal = isNaN(numX) ? idx + 1 : numX;
      const yVal = typeof data.values[idx] === "number" ? data.values[idx] : 0;
      return { x: xVal, y: yVal, label: String(label) };
    });
  }, [data]);

  if (chartData.length === 0) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#71717a", fontSize: 12 }}>
        No scatter points to display
      </div>
    );
  }

  const paletteColors = PALETTES[format.palette] || PALETTES.violet;
  const primaryColor = format.color || paletteColors[0];

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ScatterChart margin={{ top: 12, right: 16, bottom: 24, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
        <XAxis
          dataKey="x"
          name={data.x_label || "X"}
          stroke="#71717a"
          fontSize={11}
          tickLine={false}
          tick={{ fill: "#a1a1aa", fontSize: 10 }}
        />
        <YAxis
          dataKey="y"
          name={data.y_label || "Y"}
          stroke="#71717a"
          fontSize={11}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v)}
        />
        <Tooltip
          cursor={{ strokeDasharray: "3 3" }}
          contentStyle={{
            backgroundColor: "#18181b",
            borderColor: "#3f3f46",
            borderRadius: 6,
            fontSize: 12,
            color: "#f4f4f5",
          }}
        />
        {format.showLegend && <Legend wrapperStyle={{ fontSize: 11, color: "#a1a1aa" }} />}
        <Scatter
          name={data.x_label || "Points"}
          data={chartData}
          fill={primaryColor}
          cursor={isInteractive ? "pointer" : "default"}
          onClick={(entry) => {
            if (isInteractive && onPointClick && entry) {
              onPointClick({ label: entry.label, value: entry.y });
            }
          }}
        />
      </ScatterChart>
    </ResponsiveContainer>
  );
}
