/**
 * frontend/src/visualize/charts/HistogramChartRenderer.jsx
 * Custom Power BI-style Histogram renderer.
 */

import React, { useMemo } from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  LabelList,
} from "recharts";
import { PALETTES } from "../constants";

export function HistogramChartRenderer({
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
    return data.labels.map((binLabel, idx) => ({
      bin: String(binLabel ?? ""),
      count: typeof data.values[idx] === "number" ? data.values[idx] : 0,
    }));
  }, [data]);

  if (chartData.length === 0) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#71717a", fontSize: 12 }}>
        No histogram data available
      </div>
    );
  }

  const paletteColors = PALETTES[format.palette] || PALETTES.violet;
  const primaryColor = format.color || paletteColors[0];

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart
        data={chartData}
        margin={{ top: 12, right: 16, bottom: 24, left: 0 }}
        barCategoryGap={1}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="var(--rpt-chart-grid, #27272a)" vertical={false} />
        <XAxis
          dataKey="bin"
          stroke="var(--rpt-muted, #71717a)"
          fontSize={10}
          tickLine={false}
          tick={{ fill: "var(--rpt-chart-text, #a1a1aa)", fontSize: 9 }}
        />
        <YAxis
          stroke="var(--rpt-muted, #71717a)"
          fontSize={11}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "var(--rpt-tooltip-bg, #18181b)",
            borderColor: "var(--rpt-border, #3f3f46)",
            borderRadius: 6,
            fontSize: 12,
            color: "var(--rpt-tooltip-text, #f4f4f5)",
          }}
        />
        <Bar
          dataKey="count"
          fill={primaryColor}
          radius={[2, 2, 0, 0]}
          cursor={isInteractive ? "pointer" : "default"}
          onClick={(entry) => {
            if (isInteractive && onPointClick && entry) {
              onPointClick({ label: entry.bin, value: entry.count });
            }
          }}
        >
          {format.showLabels && (
            <LabelList dataKey="count" position="top" fill="#a1a1aa" fontSize={10} />
          )}
          {chartData.map((entry, index) => {
            const isMatch = crossFilter ? crossFilter.value === entry.bin : true;
            return (
              <Cell
                key={`hist-bar-${index}`}
                fill={crossFilter && !isMatch ? "rgba(113, 113, 122, 0.3)" : primaryColor}
              />
            );
          })}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
