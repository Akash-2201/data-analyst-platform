/**
 * frontend/src/visualize/charts/KpiRenderer.jsx
 * Custom Power BI-style KPI Card renderer with Indian number formatting (en-IN).
 */

import React from "react";
import { formatIndianNumber } from "../utils";

export function KpiRenderer({
  data,
  kpi = {},
  chartConfig = {},
  format = {},
}) {
  let displayValue = "-";
  let metricLabel = chartConfig.agg ? chartConfig.agg.toUpperCase() : "METRIC";
  let colName = chartConfig.xCol || chartConfig.yCol || "Total Records";

  if (data) {
    if (data.value !== undefined && data.value !== null) {
      displayValue = typeof data.value === "number" ? formatIndianNumber(data.value) : String(data.value);
    } else if (Array.isArray(data.values) && data.values.length > 0) {
      const sum = data.values.reduce((acc, v) => acc + (typeof v === "number" ? v : 0), 0);
      displayValue = formatIndianNumber(sum);
    } else if (data.row_count !== undefined) {
      displayValue = formatIndianNumber(data.row_count);
    }
  }

  const prefix = kpi.prefix || "";
  const suffix = kpi.suffix || "";

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100%",
        padding: "16px 20px",
        textAlign: "center",
      }}
    >
      <div
        style={{
          fontSize: 12,
          fontWeight: 600,
          color: "#a1a1aa",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          marginBottom: 8,
        }}
      >
        {metricLabel} OF {colName}
      </div>

      <div
        style={{
          fontSize: 36,
          fontWeight: 800,
          color: format.color || "#8b5cf6",
          letterSpacing: "-0.02em",
          lineHeight: 1.1,
          wordBreak: "break-word",
        }}
      >
        {prefix}{displayValue}{suffix}
      </div>

      {data?.stats && (
        <div
          style={{
            marginTop: 10,
            fontSize: 11,
            color: "#71717a",
            display: "flex",
            gap: 12,
          }}
        >
          {data.stats.min !== undefined && <span>Min: {formatIndianNumber(data.stats.min)}</span>}
          {data.stats.max !== undefined && <span>Max: {formatIndianNumber(data.stats.max)}</span>}
          {data.stats.median !== undefined && <span>Med: {formatIndianNumber(data.stats.median)}</span>}
        </div>
      )}
    </div>
  );
}
