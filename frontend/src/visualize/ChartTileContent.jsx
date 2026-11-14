/**
 * frontend/src/visualize/ChartTileContent.jsx
 * Fetches chart data and renders tile content (chart, text, slicer, kpi).
 */

import React, { useState, useEffect } from "react";
import { getChartData } from "../api";
import { renderSharedChart } from "../ChartComponents";

const chartDataMemoryCache = new Map();

export async function fetchTileChartData(datasetId, chartConfig) {
  const { chartType, xCol, yCol, stackCol, agg } = chartConfig;
  if (!datasetId) return null;
  const isHeatmap = chartType === "heatmap";
  const isKPI = chartType === "kpi";
  if (!isHeatmap && !isKPI && !xCol) return null;

  const cacheKey = `${datasetId}:${chartType}:${xCol || ""}:${yCol || ""}:${stackCol || ""}:${agg || ""}`;
  if (chartDataMemoryCache.has(cacheKey)) {
    return chartDataMemoryCache.get(cacheKey);
  }

  let fetchY;
  if (chartType === "stacked_bar" || chartType === "stacked_bar_100") fetchY = stackCol;
  else if (chartType === "kpi") fetchY = yCol || xCol;
  else if (chartType === "box_plot" && yCol) fetchY = yCol;
  else fetchY = yCol || undefined;

  const res = await getChartData(datasetId, {
    chartType,
    x: xCol || undefined,
    y: fetchY,
    agg: agg === "average" ? "mean" : agg,
    useCleaned: true,
  });

  chartDataMemoryCache.set(cacheKey, res);
  return res;
}

export function ChartTileContent({ tile, datasetId, columns = [] }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const { kind, chartConfig, text, slicer, kpi } = tile;

  // Text tile
  if (kind === "text") {
    return (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          padding: "8px 12px",
          textAlign: text?.align || "left",
          fontSize: text?.size === "title" ? 22 : text?.size === "subtitle" ? 16 : 13,
          fontWeight: text?.bold ? 700 : 400,
          color: "#f4f4f5",
          wordBreak: "break-word",
        }}
      >
        {text?.value || "Enter text..."}
      </div>
    );
  }

  // Slicer tile placeholder
  if (kind === "slicer") {
    return (
      <div style={{ padding: 12, height: "100%", display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ fontSize: 12, color: "#a1a1aa" }}>
          Slicer: {slicer?.col || "(No column selected)"}
        </div>
        <select
          style={{
            background: "#18181b",
            border: "1px solid #3f3f46",
            color: "#f4f4f5",
            padding: "6px 8px",
            borderRadius: 6,
            fontSize: 12,
          }}
          disabled
        >
          <option>All items</option>
        </select>
      </div>
    );
  }

  // Chart fetching effect
  useEffect(() => {
    let active = true;
    if (!datasetId || !chartConfig) return;

    setLoading(true);
    setError(null);

    fetchTileChartData(datasetId, chartConfig)
      .then((res) => {
        if (active) {
          setData(res);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (active) {
          setError(err.message || "Failed to load chart data");
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [datasetId, chartConfig]);

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#71717a", fontSize: 12 }}>
        Loading chart...
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#f87171", fontSize: 12, padding: 12, textAlign: "center" }}>
        {error}
      </div>
    );
  }

  if (!data) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", color: "#71717a", fontSize: 12, gap: 4 }}>
        <span>Configure visual in DATA panel</span>
        <span style={{ fontSize: 10, color: "#52525b" }}>Select X / Y columns</span>
      </div>
    );
  }

  const chartElement = renderSharedChart(
    chartConfig.chartType,
    data,
    chartConfig.xCol,
    chartConfig.yCol,
    chartConfig.agg
  );

  return (
    <div style={{ width: "100%", height: "100%", position: "relative" }}>
      {chartElement}
    </div>
  );
}
