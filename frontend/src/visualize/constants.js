/**
 * frontend/src/visualize/constants.js
 * Core constants, default settings, and color palettes for the Power BI Dashboard Builder.
 */

export const CANVAS_W = 1920;
export const CANVAS_H = 1080;
export const DEFAULT_PAGE_W = 1920;
export const DEFAULT_PAGE_H = 1080;
export const MIN_PAGE_W = 640;
export const MIN_PAGE_H = 360;
export const MAX_PAGE_W = 4000;
export const MAX_PAGE_H = 4000;

export const PAGE_SIZE_PRESETS = [
  { id: "16:9-1080", label: "16:9 (1920 × 1080) Full HD", w: 1920, h: 1080 },
  { id: "16:9-720", label: "16:9 (1280 × 720) HD", w: 1280, h: 720 },
  { id: "16:9-1440", label: "16:9 (2560 × 1440) 2K QHD", w: 2560, h: 1440 },
  { id: "4:3-1200", label: "4:3 (1600 × 1200)", w: 1600, h: 1200 },
  { id: "tall-1080", label: "Tall (1080 × 1920) Mobile / Story", w: 1080, h: 1920 },
  { id: "custom", label: "Custom Size", w: null, h: null },
];

export const CELL_SNAP = 20; // 20px cell when snap to grid is ON
export const CELL_FREE = 4;  // 4px cell when snap is OFF

export const DEFAULT_TILE_W = 640;
export const DEFAULT_TILE_H = 360;
export const MIN_TILE_W = 120;
export const MIN_TILE_H = 80;

export const PALETTES = {
  emerald: ["#10b981", "#3b82f6", "#f59e0b", "#ec4899", "#8b5cf6", "#06b6d4"],
  violet: ["#8b5cf6", "#ec4899", "#3b82f6", "#10b981", "#f59e0b", "#6366f1"],
  sunset: ["#f43f5e", "#fb923c", "#facc15", "#38bdf8", "#818cf8", "#a855f7"],
  ocean: ["#0284c7", "#0ea5e9", "#06b6d4", "#14b8a6", "#3b82f6", "#6366f1"],
};

export const DEFAULT_FORMAT = {
  showTitle: true,
  titleAlign: "left",
  fontSize: 14,
  fontStyle: "normal",
  showLegend: true,
  showLabels: false,
  palette: "violet",
  color: "#8b5cf6",
  bg: "#18181b", // zinc-900
  border: true,
  borderColor: "#27272a", // zinc-800
  radius: 8,
  showXTitle: true,
  showYTitle: true,
};

export const DEFAULT_CHART_CONFIG = {
  chartType: "bar",
  xCol: "",
  yCol: "",
  stackCol: "",
  agg: "sum",
  sort: "none",
  dateGrain: "month",
};

export const VISUALIZATION_TYPES = [
  { id: "bar", label: "Bar Chart", icon: "bar-chart-2" },
  { id: "line", label: "Line Chart", icon: "trending-up" },
  { id: "area", label: "Area Chart", icon: "activity" },
  { id: "pie", label: "Pie Chart", icon: "pie-chart" },
  { id: "donut", label: "Donut Chart", icon: "disc" },
  { id: "scatter", label: "Scatter Plot", icon: "crosshair" },
  { id: "histogram", label: "Histogram", icon: "bar-chart" },
  { id: "box_plot", label: "Box Plot", icon: "sliders" },
  { id: "heatmap", label: "Heatmap", icon: "grid" },
  { id: "table", label: "Table", icon: "table" },
  { id: "kpi", label: "KPI Card", icon: "hash" },
  { id: "map", label: "Map", icon: "map-pin" },
  { id: "slicer", label: "Slicer", icon: "filter" },
  { id: "text", label: "Text / Title", icon: "type" },
];

export const MORE_VISUALIZATION_TYPES = [
  { id: "stacked_bar", label: "Stacked Bar", icon: "layers" },
  { id: "stacked_bar_100", label: "100% Stacked Bar", icon: "percent" },
  { id: "treemap", label: "Treemap", icon: "layout" },
  { id: "waterfall", label: "Waterfall", icon: "bar-chart" },
  { id: "funnel", label: "Funnel", icon: "filter" },
  { id: "forecast_line", label: "Forecast Trend", icon: "trending-up" },
  { id: "forecast_ci", label: "Forecast + Conf. Interval", icon: "shield" },
  { id: "forecast_actual", label: "Forecast vs Actual", icon: "check-circle" },
  { id: "forecast_residual", label: "Forecast Residuals", icon: "help-circle" },
];
