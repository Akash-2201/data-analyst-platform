/**
 * frontend/src/visualize/ChartTileContent.jsx
 * Fetches chart data and renders tile content via ChartRouter (chart, text, slicer, kpi).
 */

import React, { useState, useEffect } from "react";
import { getChartData } from "../api";
import { ChartRouter } from "./charts/ChartRouter";
import { SlicerRenderer } from "./charts/SlicerRenderer";

const chartDataMemoryCache = new Map();

export async function fetchTileChartData(datasetId, chartConfig) {
  const { chartType, xCol, yCol, stackCol, agg } = chartConfig;
  if (!datasetId) return null;
  const isHeatmap = chartType === "heatmap";
  const isKPI = chartType === "kpi";
  const isTable = chartType === "table";
  if (!isHeatmap && !isKPI && !isTable && !xCol) return null;

  const cacheKey = `${datasetId}:${chartType}:${xCol || ""}:${yCol || ""}:${stackCol || ""}:${agg || ""}`;
  if (chartDataMemoryCache.has(cacheKey)) {
    return chartDataMemoryCache.get(cacheKey);
  }

  let fetchY;
  if (chartType === "stacked_bar" || chartType === "stacked_bar_100") fetchY = stackCol;
  else if (chartType === "kpi") fetchY = yCol || xCol;
  else if (chartType === "box_plot" && yCol) fetchY = yCol;
  else fetchY = yCol || undefined;

  let aggParam = agg;
  if (agg === "avg" || agg === "average") aggParam = "mean";
  else if (agg === "min" || agg === "max" || agg === "median") aggParam = "mean"; // backend query fallback

  const res = await getChartData(datasetId, {
    chartType,
    x: xCol || undefined,
    y: fetchY,
    agg: aggParam,
    useCleaned: true,
  });

  chartDataMemoryCache.set(cacheKey, res);
  return res;
}

class VisualErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  componentDidCatch(err) {
    console.warn("Visual render caught error:", err);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", color: "#a1a1aa", fontSize: 11, padding: 8, textAlign: "center" }}>
          <span>Visual Rendering Notice</span>
          <span style={{ fontSize: 9, color: "#71717a" }}>Configure valid X / Y columns</span>
        </div>
      );
    }
    return this.props.children;
  }
}

export function ChartTileContent({
  tile,
  datasetId,
  columns = [],
  crossFilter = null,
  onPointClick = null,
  isInteractive = false,
}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const { kind, chartConfig, format, text, slicer, kpi } = tile;

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
          color: "var(--rpt-text, #f4f4f5)",
          wordBreak: "break-word",
        }}
      >
        {text?.value || "Enter text..."}
      </div>
    );
  }

  // Slicer tile
  if (kind === "slicer") {
    return (
      <SlicerRenderer
        tile={tile}
        columns={columns}
        isInteractive={isInteractive}
      />
    );
  }

  // Chart data fetching
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
        Loading visual...
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

  return (
    <VisualErrorBoundary>
      <ChartRouter
        chartType={chartConfig.chartType}
        data={data}
        columns={columns}
        format={format}
        chartConfig={chartConfig}
        kpi={kpi}
        crossFilter={crossFilter}
        onPointClick={onPointClick}
        isInteractive={isInteractive}
      />
    </VisualErrorBoundary>
  );
}
