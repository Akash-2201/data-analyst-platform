/**
 * frontend/src/visualize/charts/BarChartRenderer.jsx
 * Custom Power BI-style Bar Chart renderer.
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
  Legend,
  Cell,
  LabelList,
} from "recharts";
import { PALETTES } from "../constants";

export function BarChartRenderer({
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
    const items = data.labels.map((label, idx) => ({
      name: String(label ?? ""),
      value: typeof data.values[idx] === "number" ? data.values[idx] : 0,
    }));

    if (chartConfig.sort === "desc") {
      items.sort((a, b) => b.value - a.value);
    } else if (chartConfig.sort === "asc") {
      items.sort((a, b) => a.value - b.value);
    }
    return items;
  }, [data, chartConfig.sort]);

  if (chartData.length === 0) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#71717a", fontSize: 12 }}>
        No data to display
      </div>
    );
  }

  const paletteColors = PALETTES[format.palette] || PALETTES.violet;
  const primaryColor = format.color || paletteColors[0];

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart
        data={chartData}
        margin={{ top: 12, right: 16, left: 0, bottom: 24 }}
        onClick={(e) => {
          if (isInteractive && onPointClick && e && e.activePayload && e.activePayload[0]) {
            const item = e.activePayload[0].payload;
            onPointClick({ label: item.name, value: item.value });
          }
        }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
        <XAxis
          dataKey="name"
          stroke="#71717a"
          fontSize={11}
          tickLine={false}
          interval={0}
          tick={({ x, y, payload }) => (
            <text
              x={x}
              y={y + 10}
              fill="#a1a1aa"
              fontSize={10}
              textAnchor="middle"
              width={60}
            >
              {payload.value.length > 10 ? `${payload.value.slice(0, 10)}…` : payload.value}
            </text>
          )}
        />
        <YAxis
          stroke="#71717a"
          fontSize={11}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v)}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "#18181b",
            borderColor: "#3f3f46",
            borderRadius: 6,
            fontSize: 12,
            color: "#f4f4f5",
          }}
          itemStyle={{ color: primaryColor }}
        />
        {format.showLegend && <Legend wrapperStyle={{ fontSize: 11, color: "#a1a1aa" }} />}
        <Bar
          dataKey="value"
          fill={primaryColor}
          radius={[4, 4, 0, 0]}
          cursor={isInteractive ? "pointer" : "default"}
        >
          {format.showLabels && (
            <LabelList dataKey="value" position="top" fill="#a1a1aa" fontSize={10} />
          )}
          {chartData.map((entry, index) => {
            const isMatch = crossFilter ? crossFilter.value === entry.name : true;
            const barFill = crossFilter
              ? isMatch
                ? primaryColor
                : "rgba(113, 113, 122, 0.3)" // Dim non-matching in highlight mode
              : paletteColors[index % paletteColors.length];
            return <Cell key={`cell-${index}`} fill={barFill} />;
          })}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
