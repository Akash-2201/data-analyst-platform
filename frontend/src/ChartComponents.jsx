/**
 * ChartComponents.jsx
 *
 * Verbatim extraction from App.jsx (lines 356–1570).
 * Contains: CHART_COLORS, CHART_GALLERY_TYPES, all renderShared* functions,
 * renderSharedChart, TYPE_ICON_MAP, getTypeInfo, isNumericType, isCategoricalType,
 * and ChartPanel.
 *
 * Zero logic changes — only the import/export wiring is new.
 * ChartBuilder (lines 1072–1271 in App.jsx) is NOT moved: it stays in App.jsx
 * because it is only used in the Clean tab and has no connection to VisualizeTab.
 */

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import {
  BarChart, Bar,
  LineChart, Line,
  ScatterChart, Scatter,
  PieChart, Pie, Cell,
  AreaChart, Area,
  Treemap,
  FunnelChart, Funnel, LabelList,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, ReferenceLine,
} from "recharts";
import { getChartData } from "./api";

// ---------------------------------------------------------------------------
// Chart colours — a curated palette that works on white
// ---------------------------------------------------------------------------
export const CHART_COLORS = [
  "#6366F1", "#38BDF8", "#34D399", "#FBBF24", "#A78BFA",
  "#F472B6", "#FB923C", "#2DD4BF", "#818CF8", "#F87171",
];

// ---------------------------------------------------------------------------
// Chart gallery — used by both old VisualizeWorkspace and new VisualizeTab
// ---------------------------------------------------------------------------
export const CHART_GALLERY_TYPES = [
  // Standard
  { id: "bar", name: "Bar Chart", icon: "📊", cat: "Standard", desc: "Category comparison" },
  { id: "line", name: "Line Chart", icon: "📈", cat: "Standard", desc: "Trends over time / sequence" },
  { id: "scatter", name: "Scatter Plot", icon: "🟣", cat: "Standard", desc: "Correlation between two metrics" },
  { id: "pie", name: "Pie Chart", icon: "🥧", cat: "Standard", desc: "Proportion of whole" },
  { id: "histogram", name: "Histogram", icon: "📶", cat: "Standard", desc: "Value frequency distribution" },
  { id: "box_plot", name: "Box Plot", icon: "📦", cat: "Standard", desc: "Quartiles, medians & outliers" },
  // Composition & Structure
  { id: "stacked_bar", name: "Stacked Bar", icon: "🧱", cat: "Composition", desc: "Multi-category segmented totals" },
  { id: "stacked_bar_100", name: "100% Stacked Bar", icon: "💯", cat: "Composition", desc: "Normalized percentage shares" },
  { id: "area", name: "Area Chart", icon: "🏔️", cat: "Composition", desc: "Cumulative filled volume trend" },
  { id: "treemap", name: "Treemap", icon: "🗂️", cat: "Composition", desc: "Hierarchical rectangle size breakdown" },
  // Flow & Performance
  { id: "waterfall", name: "Waterfall Chart", icon: "🌊", cat: "Flow & Performance", desc: "Sequential positive/negative impact" },
  { id: "funnel", name: "Funnel Chart", icon: "⏳", cat: "Flow & Performance", desc: "Sequential stage drop-off" },
  { id: "heatmap", name: "Correlation Heatmap", icon: "🌡️", cat: "Flow & Performance", desc: "All-numeric correlation matrix (-1 to +1)" },
  { id: "kpi", name: "KPI / Metric Card", icon: "💎", cat: "Flow & Performance", desc: "Single high-impact stat card" },
  // Forecasting
  { id: "forecast_line", name: "Forecast Line", icon: "🔮", cat: "Forecasting", desc: "Linear regression trend projection" },
  { id: "forecast_ci", name: "Forecast + CI", icon: "🎯", cat: "Forecasting", desc: "Trend with 95% confidence band" },
  { id: "forecast_actual", name: "Actual vs Forecast", icon: "⚖️", cat: "Forecasting", desc: "Historical fit & R² goodness score" },
  { id: "forecast_residual", name: "Forecast Residuals", icon: "📉", cat: "Forecasting", desc: "Prediction error variance" },
  // Spatial
  { id: "map", name: "Geographic Map", icon: "🗺️", cat: "Spatial", desc: "Latitude & longitude coordinate scatter" },
];

// ---------------------------------------------------------------------------
// Shared chart renderers — used by both ChartBuilder and ChartPanel
// ---------------------------------------------------------------------------

function renderSharedHistogram(chartData) {
  if (!chartData) return null;
  const { labels, values, x_label } = chartData;
  const data = labels.map((l, i) => ({ label: String(l), value: values[i] ?? 0 }));
  return (
    <ResponsiveContainer width="100%" height={340}>
      <BarChart data={data} margin={{ top: 8, right: 24, left: 8, bottom: 72 }} barCategoryGap={1}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
        <XAxis dataKey="label" tick={{ fontSize: 10, fill: "var(--ink-soft)" }} angle={-38} textAnchor="end" interval={0} />
        <YAxis tick={{ fontSize: 11, fill: "var(--ink-soft)" }} />
        <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} formatter={(v) => [v.toLocaleString(), "Count"]} />
        <Bar dataKey="value" name={x_label} fill="#6366F1" radius={[2, 2, 0, 0]} maxBarSize={60} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function renderSharedStackedBar(chartData, is100 = false) {
  if (!chartData || !chartData.series) return null;
  const { labels, series, raw_series } = chartData;
  const data = labels.map((label, i) => {
    const row = { label: String(label) };
    series.forEach((s) => { row[s.name] = s.data[i] ?? 0; });
    return row;
  });
  return (
    <ResponsiveContainer width="100%" height={340}>
      <BarChart data={data} margin={{ top: 8, right: 24, left: 8, bottom: 72 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
        <XAxis dataKey="label" tick={{ fontSize: 11, fill: "var(--ink-soft)" }} angle={-38} textAnchor="end" interval={0} />
        <YAxis
          tick={{ fontSize: 11, fill: "var(--ink-soft)" }}
          domain={is100 ? [0, 100] : ["auto", "auto"]}
          unit={is100 ? "%" : ""}
        />
        <Tooltip
          contentStyle={{ fontSize: 12, borderRadius: 4 }}
          formatter={(v, name, item) => {
            if (is100) {
              const rowIdx = labels.indexOf(item.payload.label);
              const rawS = raw_series?.find((s) => s.name === name);
              const rawCount = rawS?.data?.[rowIdx];
              return [`${v}% ${rawCount !== undefined ? `(${rawCount.toLocaleString()} items)` : ""}`, name];
            }
            return [v.toLocaleString(), name];
          }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {series.map((s, i) => (
          <Bar
            key={s.name}
            dataKey={s.name}
            stackId="a"
            fill={CHART_COLORS[i % CHART_COLORS.length]}
            radius={i === series.length - 1 ? [3, 3, 0, 0] : [0, 0, 0, 0]}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

function renderSharedArea(chartData) {
  if (!chartData) return null;
  const { labels, values, x_label, y_label } = chartData;
  const data = labels.map((l, i) => ({ label: String(l), value: values[i] ?? 0 }));
  return (
    <ResponsiveContainer width="100%" height={340}>
      <AreaChart data={data} margin={{ top: 8, right: 24, left: 8, bottom: 72 }}>
        <defs>
          <linearGradient id="areaFillGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#6366F1" stopOpacity={0.65} />
            <stop offset="95%" stopColor="#6366F1" stopOpacity={0.05} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
        <XAxis dataKey="label" tick={{ fontSize: 11, fill: "var(--ink-soft)" }} angle={-38} textAnchor="end" interval={0} />
        <YAxis tick={{ fontSize: 11, fill: "var(--ink-soft)" }} />
        <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} formatter={(v) => [typeof v === "number" ? v.toLocaleString() : v, y_label]} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Area type="monotone" dataKey="value" name={y_label} stroke="#6366F1" strokeWidth={2.5} fillOpacity={1} fill="url(#areaFillGrad)" />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function renderSharedTreemap(chartData) {
  if (!chartData) return null;
  const { labels, values } = chartData;
  const data = labels.map((l, i) => ({
    name: String(l),
    size: Math.max(0, values[i] ?? 0),
    value: values[i] ?? 0,
  })).filter((d) => d.size > 0);

  const CustomizedTreemapContent = (props) => {
    const { x, y, width, height, index, name, value } = props;
    if (width < 28 || height < 18) return null;
    return (
      <g>
        <rect
          x={x}
          y={y}
          width={width}
          height={height}
          style={{
            fill: CHART_COLORS[index % CHART_COLORS.length],
            stroke: "#fff",
            strokeWidth: 2,
            rx: 3,
            ry: 3,
          }}
        />
        {width > 44 && height > 28 && (
          <>
            <text x={x + width / 2} y={y + height / 2 - 4} textAnchor="middle" fill="#fff" fontSize={11} fontWeight={600}>
              {name.length > 14 ? `${name.slice(0, 12)}…` : name}
            </text>
            <text x={x + width / 2} y={y + height / 2 + 12} textAnchor="middle" fill="rgba(255,255,255,0.85)" fontSize={10}>
              {typeof value === "number" ? value.toLocaleString() : value}
            </text>
          </>
        )}
      </g>
    );
  };

  return (
    <ResponsiveContainer width="100%" height={340}>
      <Treemap
        data={data}
        dataKey="size"
        nameKey="name"
        stroke="#fff"
        content={<CustomizedTreemapContent />}
      >
        <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} formatter={(v) => [v.toLocaleString(), "Value"]} />
      </Treemap>
    </ResponsiveContainer>
  );
}

function renderSharedWaterfall(chartData) {
  if (!chartData || !chartData.items) return null;
  const { items, y_label } = chartData;
  return (
    <ResponsiveContainer width="100%" height={340}>
      <BarChart data={items} margin={{ top: 14, right: 24, left: 8, bottom: 72 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
        <XAxis dataKey="label" tick={{ fontSize: 11, fill: "var(--ink-soft)" }} angle={-38} textAnchor="end" interval={0} />
        <YAxis tick={{ fontSize: 11, fill: "var(--ink-soft)" }} />
        <Tooltip
          contentStyle={{ fontSize: 12, borderRadius: 4 }}
          formatter={(v, name, entry) => {
            const it = entry.payload;
            if (name === "base") return null;
            return [
              `${it.delta >= 0 ? "+" : ""}${it.delta.toLocaleString()} (Total: ${it.end.toLocaleString()})`,
              it.is_total ? "Final Total" : "Delta",
            ];
          }}
        />
        <Bar dataKey="base" stackId="wf" fill="transparent" />
        <Bar dataKey="span" stackId="wf" radius={[2, 2, 2, 2]}>
          {items.map((it, idx) => {
            let fill = "#2a9d8f";
            if (it.is_total) fill = "#1c6e8c";
            else if (!it.is_positive) fill = "#e05a4b";
            return <Cell key={idx} fill={fill} />;
          })}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function renderSharedFunnel(chartData) {
  if (!chartData) return null;
  const { labels, values } = chartData;
  const data = labels.map((l, i) => ({
    name: String(l),
    value: values[i] ?? 0,
    fill: CHART_COLORS[i % CHART_COLORS.length],
  }));

  return (
    <ResponsiveContainer width="100%" height={340}>
      <FunnelChart margin={{ top: 14, right: 30, left: 30, bottom: 14 }}>
        <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} formatter={(v) => [v.toLocaleString(), "Count"]} />
        <Funnel dataKey="value" data={data} isAnimationActive>
          <LabelList position="right" fill="var(--ink)" stroke="none" dataKey="name" fontSize={11} />
        </Funnel>
      </FunnelChart>
    </ResponsiveContainer>
  );
}

function renderSharedHeatmap(chartData) {
  if (!chartData || !chartData.matrix) return null;
  const { cols, matrix } = chartData;
  return (
    <div className="heatmap-container">
      <table className="heatmap-table">
        <thead>
          <tr>
            <th className="heatmap-corner"></th>
            {cols.map((c) => (
              <th key={c} className="heatmap-th" title={c}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cols.map((rowName, rIdx) => (
            <tr key={rowName}>
              <td className="heatmap-row-header" title={rowName}>
                {rowName}
              </td>
              {cols.map((colName, cIdx) => {
                const val = matrix[rIdx]?.[cIdx] ?? 0;
                const absVal = Math.min(1, Math.abs(val));
                let bg = "rgba(240, 238, 234, 0.4)";
                let textColor = "var(--ink)";
                if (val > 0.001) {
                  bg = `rgba(28, 110, 140, ${0.12 + absVal * 0.78})`;
                  if (absVal > 0.5) textColor = "#ffffff";
                } else if (val < -0.001) {
                  bg = `rgba(224, 90, 75, ${0.12 + absVal * 0.78})`;
                  if (absVal > 0.5) textColor = "#ffffff";
                }
                return (
                  <td
                    key={colName}
                    className="heatmap-cell"
                    style={{ backgroundColor: bg, color: textColor }}
                    title={`${rowName} ↔ ${colName}: ${val.toFixed(3)}`}
                  >
                    {val.toFixed(2)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderSharedKPI(chartData) {
  if (!chartData) return null;
  const { column, metric, value, stats } = chartData;
  const fmt = (v) => {
    if (v === null || v === undefined) return "—";
    if (typeof v === "number") {
      if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
      if (Math.abs(v) >= 1e3) return `${(v / 1e3).toFixed(1)}k`;
      return Number.isInteger(v) ? v.toLocaleString() : v.toFixed(2);
    }
    return String(v);
  };

  return (
    <div className="kpi-card-wrapper">
      <div className="kpi-metric-badge">{String(metric).toUpperCase()}</div>
      <div className="kpi-main-val">{fmt(value)}</div>
      <div className="kpi-col-name">{column}</div>

      {stats && (
        <div className="kpi-stats-grid">
          {stats.min !== undefined && (
            <div className="kpi-stat-item">
              <span className="kpi-stat-lbl">Min</span>
              <span className="kpi-stat-val">{fmt(stats.min)}</span>
            </div>
          )}
          {stats.median !== undefined && (
            <div className="kpi-stat-item">
              <span className="kpi-stat-lbl">Median</span>
              <span className="kpi-stat-val">{fmt(stats.median)}</span>
            </div>
          )}
          {stats.max !== undefined && (
            <div className="kpi-stat-item">
              <span className="kpi-stat-lbl">Max</span>
              <span className="kpi-stat-val">{fmt(stats.max)}</span>
            </div>
          )}
          <div className="kpi-stat-item">
            <span className="kpi-stat-lbl">Unique</span>
            <span className="kpi-stat-val">{stats.unique?.toLocaleString()}</span>
          </div>
          <div className="kpi-stat-item">
            <span className="kpi-stat-lbl">Count</span>
            <span className="kpi-stat-val">{stats.count?.toLocaleString()}</span>
          </div>
        </div>
      )}
    </div>
  );
}

function renderSharedForecastLine(chartData) {
  if (!chartData || !chartData.history) return null;
  const { history, future, metrics, y_label } = chartData;
  const combined = [
    ...history.map((h) => ({ date: h.date, actual: h.actual, forecast: null })),
    ...(history.length > 0 ? [{ date: history[history.length - 1].date, actual: history[history.length - 1].actual, forecast: history[history.length - 1].actual }] : []),
    ...future.map((f) => ({ date: f.date, actual: null, forecast: f.forecast })),
  ];
  return (
    <div style={{ width: "100%" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0 10px 6px" }}>
        <span className="forecast-header-badge">🔮 Simple Linear Trend Projection</span>
        <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--ink-soft)" }}>
          Slope: {metrics?.slope > 0 ? `+${metrics.slope}` : metrics?.slope}/step · Fit R²: {metrics?.r2}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={310}>
        <LineChart data={combined} margin={{ top: 8, right: 24, left: 8, bottom: 64 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
          <XAxis dataKey="date" tick={{ fontSize: 10, fill: "var(--ink-soft)" }} angle={-38} textAnchor="end" interval="preserveStartEnd" />
          <YAxis tick={{ fontSize: 11, fill: "var(--ink-soft)" }} />
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line type="monotone" dataKey="actual" name={`Historical ${y_label}`} stroke="#6366F1" strokeWidth={2.5} dot={{ r: 3, fill: "#6366F1" }} connectNulls={false} />
          <Line type="monotone" dataKey="forecast" name={`Projected Trend (+${future.length} pts)`} stroke="#F87171" strokeWidth={2.5} strokeDasharray="5 5" dot={{ r: 4, fill: "#F87171" }} connectNulls={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function renderSharedForecastCI(chartData) {
  if (!chartData || !chartData.history) return null;
  const { history, future, metrics, y_label } = chartData;
  const combined = [
    ...history.map((h) => ({ date: h.date, actual: h.actual, forecast: null, ci_lower: null, ci_upper: null })),
    ...(history.length > 0 ? [{
      date: history[history.length - 1].date,
      actual: history[history.length - 1].actual,
      forecast: history[history.length - 1].actual,
      ci_lower: history[history.length - 1].actual,
      ci_upper: history[history.length - 1].actual,
    }] : []),
    ...future.map((f) => ({
      date: f.date,
      actual: null,
      forecast: f.forecast,
      ci_lower: f.ci_lower,
      ci_upper: f.ci_upper,
    })),
  ];
  return (
    <div style={{ width: "100%" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0 10px 6px" }}>
        <span className="forecast-header-badge">🎯 Trend Projection ± 95% Confidence Band</span>
        <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--ink-soft)" }}>
          Std Error: {metrics?.se} · R²: {metrics?.r2}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={310}>
        <AreaChart data={combined} margin={{ top: 8, right: 24, left: 8, bottom: 64 }}>
          <defs>
            <linearGradient id="ciGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#F87171" stopOpacity={0.25} />
              <stop offset="95%" stopColor="#F87171" stopOpacity={0.05} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
          <XAxis dataKey="date" tick={{ fontSize: 10, fill: "var(--ink-soft)" }} angle={-38} textAnchor="end" interval="preserveStartEnd" />
          <YAxis tick={{ fontSize: 11, fill: "var(--ink-soft)" }} />
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Area type="monotone" dataKey="ci_upper" name="95% CI Upper" stroke="rgba(224, 90, 75, 0.4)" fill="url(#ciGrad)" />
          <Area type="monotone" dataKey="ci_lower" name="95% CI Lower" stroke="rgba(224, 90, 75, 0.4)" fill="#ffffff" />
          <Line type="monotone" dataKey="actual" name={`Historical ${y_label}`} stroke="#6366F1" strokeWidth={2.5} dot={{ r: 3, fill: "#6366F1" }} connectNulls={false} />
          <Line type="monotone" dataKey="forecast" name="Forecast Projection" stroke="#F87171" strokeWidth={2.5} strokeDasharray="5 5" dot={{ r: 4, fill: "#F87171" }} connectNulls={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function renderSharedForecastActual(chartData) {
  if (!chartData || !chartData.history) return null;
  const { history, metrics, y_label } = chartData;
  return (
    <div style={{ width: "100%" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0 10px 6px" }}>
        <span className="forecast-header-badge">⚖️ Historical Actual vs Regression Fit</span>
        <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--ink-soft)" }}>
          Goodness of Fit R²: <strong>{metrics?.r2}</strong>
        </span>
      </div>
      <ResponsiveContainer width="100%" height={310}>
        <LineChart data={history} margin={{ top: 8, right: 24, left: 8, bottom: 64 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
          <XAxis dataKey="date" tick={{ fontSize: 10, fill: "var(--ink-soft)" }} angle={-38} textAnchor="end" interval="preserveStartEnd" />
          <YAxis tick={{ fontSize: 11, fill: "var(--ink-soft)" }} />
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line type="monotone" dataKey="actual" name={`Actual ${y_label}`} stroke="#6366F1" strokeWidth={2.5} dot={{ r: 3, fill: "#6366F1" }} />
          <Line type="monotone" dataKey="fitted" name="Fitted Regression Line" stroke="#FBBF24" strokeWidth={2} strokeDasharray="4 4" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function renderSharedForecastResidual(chartData) {
  if (!chartData || !chartData.history) return null;
  const { history, metrics } = chartData;
  return (
    <div style={{ width: "100%" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0 10px 6px" }}>
        <span className="forecast-header-badge">📉 Residual Error (Actual − Fitted)</span>
        <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--ink-soft)" }}>
          Residual SE: {metrics?.se}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={310}>
        <BarChart data={history} margin={{ top: 8, right: 24, left: 8, bottom: 64 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
          <XAxis dataKey="date" tick={{ fontSize: 10, fill: "var(--ink-soft)" }} angle={-38} textAnchor="end" interval="preserveStartEnd" />
          <YAxis tick={{ fontSize: 11, fill: "var(--ink-soft)" }} />
          <ReferenceLine y={0} stroke="#888" strokeWidth={1.5} />
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} formatter={(v) => [v, "Residual Error"]} />
          <Bar dataKey="residual" name="Residual (Error)" radius={[2, 2, 2, 2]}>
            {history.map((entry, idx) => (
              <Cell key={idx} fill={entry.residual >= 0 ? "#1c6e8c" : "#e05a4b"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function renderSharedMap(chartData) {
  if (!chartData) return null;
  if (chartData.deferred) {
    return (
      <div className="map-deferred-card">
        <div className="map-deferred-icon">🗺️</div>
        <div className="map-deferred-title">Geographic Map Deferred</div>
        <div className="map-deferred-desc">{chartData.message}</div>
        <div className="map-deferred-note">
          To enable spatial plotting, ensure your dataset contains explicit latitude and longitude columns.
        </div>
      </div>
    );
  }
  const { points, x_label, y_label } = chartData;
  const scatterData = points.map((p) => ({
    x: p.lon,
    y: p.lat,
    label: p.label,
  }));
  return (
    <ResponsiveContainer width="100%" height={340}>
      <ScatterChart margin={{ top: 12, right: 24, left: 12, bottom: 40 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
        <XAxis dataKey="x" type="number" name={x_label} unit="°" tick={{ fontSize: 11 }} label={{ value: `Longitude (${x_label})`, position: "bottom", offset: 15, fontSize: 11 }} />
        <YAxis dataKey="y" type="number" name={y_label} unit="°" tick={{ fontSize: 11 }} label={{ value: `Latitude (${y_label})`, angle: -90, position: "left", offset: 0, fontSize: 11 }} />
        <Tooltip cursor={{ strokeDasharray: "3 3" }} content={({ payload }) => {
          if (!payload?.length) return null;
          const pt = payload[0]?.payload;
          return (
            <div className="chart-scatter-tooltip">
              <div className="chart-scatter-tooltip-label">{pt.label}</div>
              <div>Lat: {pt.y}°</div>
              <div>Lon: {pt.x}°</div>
            </div>
          );
        }} />
        <Scatter name="Locations" data={scatterData} fill="#6366F1" opacity={0.75} />
      </ScatterChart>
    </ResponsiveContainer>
  );
}

function renderSharedBoxPlot(chartData) {
  if (!chartData || !chartData.box_stats) return null;
  const { labels, box_stats, y_label } = chartData;

  const allVals = box_stats.flatMap((s) => [s.min, s.max]);
  const gMin = Math.min(...allVals);
  const gMax = Math.max(...allVals);
  const range = gMax - gMin || 1;

  const PAD_TOP = 20, PAD_BOT = 52, PAD_LEFT = 62, PAD_RIGHT = 20;
  const CHART_H = 320;
  const N = labels.length;
  const COL_W = Math.max(80, Math.min(160, Math.floor(540 / Math.max(N, 1))));
  const CHART_W = PAD_LEFT + N * COL_W + PAD_RIGHT;
  const PLOT_H = CHART_H - PAD_TOP - PAD_BOT;
  const BOX_HALF = Math.min(22, COL_W * 0.28);
  const toY = (v) => PAD_TOP + PLOT_H * (1 - (v - gMin) / range);
  const ticks = 5;
  const yTicks = Array.from({ length: ticks + 1 }, (_, i) => gMin + (range * i) / ticks);
  const fmtNum = (v) => {
    if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
    if (Math.abs(v) >= 1000) return `${(v / 1000).toFixed(1)}k`;
    return v % 1 === 0 ? String(v) : v.toFixed(1);
  };

  return (
    <div style={{ overflowX: "auto", padding: "8px 0" }}>
      <svg width={CHART_W} height={CHART_H} style={{ display: "block", minWidth: "100%" }}>
        {yTicks.map((tick, i) => (
          <line key={i} x1={PAD_LEFT} y1={toY(tick)} x2={CHART_W - PAD_RIGHT} y2={toY(tick)} stroke="#f0eeea" strokeWidth={1} />
        ))}
        <line x1={PAD_LEFT} y1={PAD_TOP} x2={PAD_LEFT} y2={PAD_TOP + PLOT_H} stroke="#ccc" strokeWidth={1} />
        {yTicks.map((tick, i) => (
          <g key={i}>
            <line x1={PAD_LEFT - 4} y1={toY(tick)} x2={PAD_LEFT} y2={toY(tick)} stroke="#aaa" strokeWidth={1} />
            <text x={PAD_LEFT - 8} y={toY(tick)} textAnchor="end" dominantBaseline="middle" fontSize={10} fill="#888">{fmtNum(tick)}</text>
          </g>
        ))}
        <text x={14} y={PAD_TOP + PLOT_H / 2} textAnchor="middle" fontSize={11} fill="#888"
          transform={`rotate(-90, 14, ${PAD_TOP + PLOT_H / 2})`}>{y_label}</text>

        {box_stats.map((stat, i) => {
          const cx = PAD_LEFT + (i + 0.5) * COL_W;
          const yQ1 = toY(stat.q1);
          const yQ3 = toY(stat.q3);
          const yMed = toY(stat.median);
          const yMin = toY(stat.min);
          const yMax = toY(stat.max);
          const capW = BOX_HALF * 0.6;
          const label = String(labels[i]);

          return (
            <g key={i}>
              <line x1={cx} y1={yQ3} x2={cx} y2={yMax} stroke="#6366F1" strokeWidth={1.5} />
              <line x1={cx - capW} y1={yMax} x2={cx + capW} y2={yMax} stroke="#6366F1" strokeWidth={1.5} />
              <line x1={cx} y1={yQ1} x2={cx} y2={yMin} stroke="#6366F1" strokeWidth={1.5} />
              <line x1={cx - capW} y1={yMin} x2={cx + capW} y2={yMin} stroke="#6366F1" strokeWidth={1.5} />
              <rect x={cx - BOX_HALF} y={yQ3} width={BOX_HALF * 2} height={Math.max(1, yQ1 - yQ3)}
                fill="rgba(28,110,140,0.13)" stroke="#6366F1" strokeWidth={1.5} rx={2} />
              <line x1={cx - BOX_HALF} y1={yMed} x2={cx + BOX_HALF} y2={yMed} stroke="#6366F1" strokeWidth={2.5} />
              <text x={cx + BOX_HALF + 4} y={yMed} dominantBaseline="middle" fontSize={9} fill="#6366F1">{fmtNum(stat.median)}</text>
              <text x={cx} y={PAD_TOP + PLOT_H + 18} textAnchor="middle" fontSize={11} fill="#666">
                {label.length > 13 ? `${label.slice(0, 12)}…` : label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function renderSharedChart(chartData, chartType) {
  if (!chartData) return null;
  if (chartType === "histogram") return renderSharedHistogram(chartData);
  if (chartType === "stacked_bar") return renderSharedStackedBar(chartData, false);
  if (chartType === "stacked_bar_100") return renderSharedStackedBar(chartData, true);
  if (chartType === "box_plot") return renderSharedBoxPlot(chartData);
  if (chartType === "area") return renderSharedArea(chartData);
  if (chartType === "treemap") return renderSharedTreemap(chartData);
  if (chartType === "waterfall") return renderSharedWaterfall(chartData);
  if (chartType === "funnel") return renderSharedFunnel(chartData);
  if (chartType === "heatmap") return renderSharedHeatmap(chartData);
  if (chartType === "kpi") return renderSharedKPI(chartData);
  if (chartType === "forecast_line") return renderSharedForecastLine(chartData);
  if (chartType === "forecast_ci") return renderSharedForecastCI(chartData);
  if (chartType === "forecast_actual") return renderSharedForecastActual(chartData);
  if (chartType === "forecast_residual") return renderSharedForecastResidual(chartData);
  if (chartType === "map") return renderSharedMap(chartData);

  const { labels, values, x_label, y_label } = chartData;

  if (chartType === "pie") {
    const slices = labels.slice(0, 10).map((l, i) => ({ name: String(l), value: values[i] ?? 0 }));
    return (
      <ResponsiveContainer width="100%" height={340}>
        <PieChart>
          <Pie data={slices} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={120}
            label={({ name, percent }) => `${name} (${(percent * 100).toFixed(1)}%)`} labelLine={false}>
            {slices.map((_, i) => (<Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />))}
          </Pie>
          <Tooltip formatter={(v) => [v.toLocaleString(), "Count"]} contentStyle={{ fontSize: 12, borderRadius: 4 }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
        </PieChart>
      </ResponsiveContainer>
    );
  }

  const data = labels.map((l, i) => ({ label: String(l), value: values[i] ?? 0 }));

  if (chartType === "bar") {
    return (
      <ResponsiveContainer width="100%" height={340}>
        <BarChart data={data} margin={{ top: 8, right: 24, left: 8, bottom: 72 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11, fill: "var(--ink-soft)" }} angle={-38} textAnchor="end" interval={0} />
          <YAxis tick={{ fontSize: 11, fill: "var(--ink-soft)" }} />
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} formatter={(v) => [typeof v === "number" ? v.toLocaleString() : v, y_label]} />
          <Bar dataKey="value" name={y_label} fill="#6366F1" radius={[3, 3, 0, 0]} maxBarSize={48} />
        </BarChart>
      </ResponsiveContainer>
    );
  }

  if (chartType === "line") {
    return (
      <ResponsiveContainer width="100%" height={340}>
        <LineChart data={data} margin={{ top: 8, right: 24, left: 8, bottom: 72 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
          <XAxis dataKey="label" tick={{ fontSize: 11, fill: "var(--ink-soft)" }} angle={-38} textAnchor="end" interval={0} />
          <YAxis tick={{ fontSize: 11, fill: "var(--ink-soft)" }} />
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} formatter={(v) => [typeof v === "number" ? v.toLocaleString() : v, y_label]} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line type="monotone" dataKey="value" name={y_label} stroke="#1c6e8c" strokeWidth={2.5} dot={{ r: 3, fill: "#1c6e8c" }} activeDot={{ r: 5 }} />
        </LineChart>
      </ResponsiveContainer>
    );
  }

  if (chartType === "scatter") {
    const scatterData = labels.map((l, i) => ({ x: i, y: values[i] ?? 0, label: String(l) }));
    return (
      <ResponsiveContainer width="100%" height={340}>
        <ScatterChart margin={{ top: 8, right: 24, left: 8, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
          <XAxis dataKey="x" type="number" name={x_label} tick={{ fontSize: 11 }} tickFormatter={(v) => String(labels[v] ?? v).slice(0, 12)} />
          <YAxis dataKey="y" type="number" name={y_label} tick={{ fontSize: 11 }} />
          <Tooltip cursor={{ strokeDasharray: "3 3" }} content={({ payload }) => {
            if (!payload?.length) return null;
            const pt = payload[0]?.payload;
            if (!pt) return null;
            return (<div className="chart-scatter-tooltip"><div className="chart-scatter-tooltip-label">{pt.label}</div><div>{y_label}: {typeof pt.y === "number" ? pt.y.toLocaleString() : pt.y}</div></div>);
          }} />
          <Scatter name={y_label} data={scatterData} fill="#6366F1" opacity={0.8} />
        </ScatterChart>
      </ResponsiveContainer>
    );
  }

  return null;
}

// ---------------------------------------------------------------------------
// Column type helpers — used by old VisualizeWorkspace sidebar and new VisualizeTab
// ---------------------------------------------------------------------------
export const TYPE_ICON_MAP = {
  numeric: { icon: "🔢", cls: "numeric", label: "num" },
  non_negative_numeric: { icon: "🔢", cls: "numeric", label: "num" },
  identifier: { icon: "🔢", cls: "numeric", label: "id" },
  categorical: { icon: "🏷️", cls: "categorical", label: "cat" },
  datetime: { icon: "📅", cls: "datetime", label: "date" },
  boolean: { icon: "🏷️", cls: "categorical", label: "bool" },
  email: { icon: "📝", cls: "text", label: "txt" },
  phone: { icon: "📝", cls: "text", label: "txt" },
  text: { icon: "📝", cls: "text", label: "txt" },
  free_text: { icon: "📝", cls: "text", label: "txt" },
  url: { icon: "📝", cls: "text", label: "txt" },
  address: { icon: "📝", cls: "text", label: "txt" },
  currency: { icon: "🔢", cls: "numeric", label: "curr" },
};

export function getTypeInfo(inferredType) {
  return TYPE_ICON_MAP[inferredType] || TYPE_ICON_MAP.text;
}

export function isNumericType(inferredType, dtype) {
  if (inferredType === "numeric" || inferredType === "non_negative_numeric") return true;
  if (["int64", "float64", "int32", "float32", "int16", "float16"].includes(dtype)) return true;
  return false;
}

export function isCategoricalType(inferredType, dtype) {
  return inferredType === "categorical" || dtype === "object";
}

// ---------------------------------------------------------------------------
// ChartPanel — a single independently-configurable chart slot in the Visualize workspace
// (verbatim from App.jsx lines 1279–1570; zero logic change)
// ---------------------------------------------------------------------------
export const ChartPanel = forwardRef(function ChartPanel(
  { id, index, datasetId, columns, onRemove, chartType: initialType, onSelectType, isFocused, onFocus, onConfigChange },
  ref
) {
  const panelRef = useRef(null);
  useImperativeHandle(ref, () => panelRef.current);

  const allCols = columns || [];
  const [chartType, setChartType] = useState(initialType || "bar");
  const [xCol, setXCol] = useState(allCols[0]?.name || "");
  const [yCol, setYCol] = useState(allCols.length > 1 ? allCols[1]?.name : allCols[0]?.name || "");
  const [stackCol, setStackCol] = useState(allCols.length > 1 ? allCols[1]?.name : "");
  const [agg, setAgg] = useState("count");
  const [chartData, setChartData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isDragOver, setIsDragOver] = useState(false);

  // Sync if parent updates initialType
  useEffect(() => {
    if (initialType && initialType !== chartType) {
      setChartType(initialType);
      doFetch({ chartType: initialType });
    }
  }, [initialType]);

  // Report config to parent for PDF title generation
  useEffect(() => {
    onConfigChange?.(id, { chartType, xCol, yCol, stackCol, agg });
  }, [id, chartType, xCol, yCol, stackCol, agg]);

  const isForecast = chartType.startsWith("forecast_");
  const isHeatmap = chartType === "heatmap";
  const isKPI = chartType === "kpi";
  const isMap = chartType === "map";
  const isHist = chartType === "histogram";
  const isBox = chartType === "box_plot";
  const isStack = chartType === "stacked_bar" || chartType === "stacked_bar_100";
  const isWaterfall = chartType === "waterfall";

  const needsY =
    isForecast ||
    chartType === "line" ||
    chartType === "scatter" ||
    chartType === "area" ||
    isWaterfall ||
    (chartType === "bar" && agg !== "count") ||
    (isKPI && (agg === "sum" || agg === "mean"));

  const needsStack = isStack;

  const doFetch = async (overrides = {}) => {
    const ct = overrides.chartType ?? chartType;
    const xc = overrides.xCol ?? xCol;
    const yc = overrides.yCol ?? yCol;
    const sc = overrides.stackCol ?? stackCol;
    const ag = overrides.agg ?? agg;

    if (!datasetId) return;
    const ctIsHeatmap = ct === "heatmap";
    const ctIsKPI = ct === "kpi";
    if (!ctIsHeatmap && !ctIsKPI && !xc) return;

    setLoading(true);
    setError(null);
    try {
      let fetchY;
      if (ct === "stacked_bar" || ct === "stacked_bar_100") fetchY = sc;
      else if (ct === "kpi") fetchY = yc || xc;
      else if (ct === "box_plot" && yc) fetchY = yc;
      else if (ct.startsWith("forecast_") || ct === "line" || ct === "scatter" || ct === "area" || ct === "waterfall" || (ct === "bar" && ag !== "count")) fetchY = yc;
      else if (ct === "map" && yc) fetchY = yc;
      else fetchY = undefined;

      const fetchX = xc || (ctIsKPI ? (yc || "") : "");

      const data = await getChartData(datasetId, {
        chartType: ct,
        x: fetchX,
        y: fetchY,
        agg: ag,
        useCleaned: true,
      });
      setChartData(data);
    } catch (err) {
      setError(err.message || "Failed to generate chart.");
      setChartData(null);
    } finally {
      setLoading(false);
    }
  };

  // Auto-fetch on mount
  useEffect(() => {
    if (datasetId && (xCol || isHeatmap)) {
      doFetch();
    }
  }, []);

  const handleTypeChange = (newType) => {
    setChartType(newType);
    onSelectType?.(newType);
    doFetch({ chartType: newType });
  };

  return (
    <div
      className={`viz-panel${isFocused ? " focused" : ""}${isDragOver ? " drag-over" : ""}`}
      ref={panelRef}
      onClick={onFocus}
      onDragOver={(e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "copy";
        setIsDragOver(true);
      }}
      onDragLeave={() => setIsDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setIsDragOver(false);
        const droppedType = e.dataTransfer.getData("text/plain");
        if (droppedType) {
          handleTypeChange(droppedType);
        }
      }}
    >
      <div className="viz-panel-header">
        <div className="viz-panel-ctrl" style={{ minWidth: 140 }}>
          <label className="chart-label">Chart Type</label>
          <select
            className="chart-select"
            value={chartType}
            onChange={(e) => handleTypeChange(e.target.value)}
          >
            {CHART_GALLERY_TYPES.map((t) => (
              <option key={t.id} value={t.id}>
                {t.icon} {t.name}
              </option>
            ))}
          </select>
        </div>

        {!isHeatmap && (
          <div className="viz-panel-ctrl">
            <label className="chart-label">
              {isHist
                ? "Numeric Column"
                : isKPI
                ? "Metric Column"
                : isForecast
                ? "Date Column"
                : isWaterfall
                ? "Step Column"
                : isMap
                ? "Longitude / ID"
                : "X Axis"}
            </label>
            <select
              className="chart-select"
              value={xCol}
              onChange={(e) => setXCol(e.target.value)}
            >
              {allCols.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {!isHeatmap && (needsY || isBox || isMap) && (
          <div className="viz-panel-ctrl">
            <label className="chart-label">
              {isBox
                ? "Group By (optional)"
                : isForecast
                ? "Numeric Metric (Y)"
                : isWaterfall
                ? "Value Delta (Y)"
                : isMap
                ? "Latitude Column"
                : "Y Axis"}
            </label>
            <select
              className="chart-select"
              value={yCol}
              onChange={(e) => setYCol(e.target.value)}
            >
              {isBox && <option value="">— None —</option>}
              {allCols.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {needsStack && (
          <div className="viz-panel-ctrl">
            <label className="chart-label">Stack by</label>
            <select
              className="chart-select"
              value={stackCol}
              onChange={(e) => setStackCol(e.target.value)}
            >
              {allCols.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {!isHist && !isBox && !isStack && !isForecast && !isHeatmap && !isWaterfall && !isMap && (
          <div className="viz-panel-ctrl" style={{ maxWidth: 90 }}>
            <label className="chart-label">Agg</label>
            <select
              className="chart-select"
              value={agg}
              onChange={(e) => setAgg(e.target.value)}
              disabled={chartType === "scatter" || chartType === "pie"}
            >
              <option value="count">Count</option>
              <option value="sum">Sum</option>
              <option value="mean">Mean</option>
            </select>
          </div>
        )}

        <button
          className="viz-panel-gen-btn"
          onClick={() => doFetch()}
          disabled={loading || (!isHeatmap && !xCol) || (needsY && !yCol) || (needsStack && !stackCol)}
          title="Generate chart"
        >
          {loading ? "…" : <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>}
        </button>

        <button
          className="viz-panel-remove-btn"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          title="Remove chart"
        >
          ✕
        </button>
      </div>

      <div className="viz-panel-body">
        {loading && (
          <div className="chart-loading">
            <div className="ledger-loading-track" style={{ width: 160 }}>
              <div className="ledger-loading-bar" />
            </div>
            <span className="chart-loading-label">Generating…</span>
          </div>
        )}
        {!loading && error && (
          <div className="viz-panel-error">
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Unable to render chart:</div>
            <div>{error}</div>
          </div>
        )}
        {!loading && !chartData && !error && (
          <div className="chart-empty" style={{ minHeight: 120 }}>
            Select parameters and click <strong>Go</strong>
          </div>
        )}
        {!loading && chartData && renderSharedChart(chartData, chartType)}
      </div>

      {chartData && !loading && (
        <div className="viz-panel-meta">
          {chartData.group_count !== undefined && `${chartData.group_count} groups · `}
          {chartData.row_count?.toLocaleString()} rows
          {chartData.metrics?.r2 !== undefined && ` · R² = ${chartData.metrics.r2}`}
        </div>
      )}
    </div>
  );
});

