/**
 * frontend/src/visualize/charts/AreaChartRenderer.jsx
 * Custom Power BI-style Area Chart renderer.
 */

import React, { useMemo } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  LabelList,
} from "recharts";
import { PALETTES } from "../constants";

export function AreaChartRenderer({
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
  const gradId = `areaGrad-${Math.random().toString(36).slice(2, 7)}`;

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart
        data={chartData}
        margin={{ top: 12, right: 16, left: 0, bottom: 24 }}
        onClick={(e) => {
          if (isInteractive && onPointClick && e && e.activePayload && e.activePayload[0]) {
            const item = e.activePayload[0].payload;
            onPointClick({ label: item.name, value: item.value });
          }
        }}
      >
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={primaryColor} stopOpacity={0.4} />
            <stop offset="95%" stopColor={primaryColor} stopOpacity={0.0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--rpt-chart-grid, #27272a)" vertical={false} />
        <XAxis
          dataKey="name"
          stroke="var(--rpt-muted, #71717a)"
          fontSize={11}
          tickLine={false}
          tick={{ fill: "var(--rpt-chart-text, #a1a1aa)", fontSize: 10 }}
        />
        <YAxis
          stroke="var(--rpt-muted, #71717a)"
          fontSize={11}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v)}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "var(--rpt-tooltip-bg, #18181b)",
            borderColor: "var(--rpt-border, #3f3f46)",
            borderRadius: 6,
            fontSize: 12,
            color: "var(--rpt-tooltip-text, #f4f4f5)",
          }}
          itemStyle={{ color: primaryColor }}
        />
        {format.showLegend && <Legend wrapperStyle={{ fontSize: 11, color: "var(--rpt-chart-text, #a1a1aa)" }} />}
        <Area
          type="monotone"
          dataKey="value"
          stroke={primaryColor}
          strokeWidth={2}
          fillOpacity={1}
          fill={`url(#${gradId})`}
          cursor={isInteractive ? "pointer" : "default"}
        >
          {format.showLabels && (
            <LabelList dataKey="value" position="top" fill="var(--rpt-chart-text, #a1a1aa)" fontSize={10} />
          )}
        </Area>
      </AreaChart>
    </ResponsiveContainer>
  );
}
