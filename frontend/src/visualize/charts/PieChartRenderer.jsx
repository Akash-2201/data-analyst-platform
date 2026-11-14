/**
 * frontend/src/visualize/charts/PieChartRenderer.jsx
 * Custom Power BI-style Pie and Donut Chart renderer.
 */

import React, { useMemo } from "react";
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
} from "recharts";
import { PALETTES } from "../constants";

export function PieChartRenderer({
  data,
  format = {},
  chartConfig = {},
  isDonut = false,
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
  const donutMode = isDonut || chartConfig.chartType === "donut";

  return (
    <ResponsiveContainer width="100%" height="100%">
      <PieChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
        <Tooltip
          contentStyle={{
            backgroundColor: "#18181b",
            borderColor: "#3f3f46",
            borderRadius: 6,
            fontSize: 12,
            color: "#f4f4f5",
          }}
        />
        {format.showLegend && <Legend wrapperStyle={{ fontSize: 11, color: "#a1a1aa" }} />}
        <Pie
          data={chartData}
          dataKey="value"
          nameKey="name"
          cx="50%"
          cy="50%"
          innerRadius={donutMode ? "55%" : 0}
          outerRadius="80%"
          paddingAngle={donutMode ? 3 : 1}
          cursor={isInteractive ? "pointer" : "default"}
          onClick={(entry) => {
            if (isInteractive && onPointClick && entry) {
              onPointClick({ label: entry.name, value: entry.value });
            }
          }}
        >
          {chartData.map((entry, index) => {
            const isMatch = crossFilter ? crossFilter.value === entry.name : true;
            const sliceFill = crossFilter
              ? isMatch
                ? paletteColors[index % paletteColors.length]
                : "rgba(113, 113, 122, 0.25)"
              : paletteColors[index % paletteColors.length];
            return <Cell key={`slice-${index}`} fill={sliceFill} stroke="#18181b" strokeWidth={2} />;
          })}
        </Pie>
      </PieChart>
    </ResponsiveContainer>
  );
}
