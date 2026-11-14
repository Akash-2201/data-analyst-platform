/**
 * frontend/src/visualize/charts/ChartRouter.jsx
 * Dispatches to custom Power BI-style renderers or falls back to renderSharedChart.
 */

import React from "react";
import { BarChartRenderer } from "./BarChartRenderer";
import { LineChartRenderer } from "./LineChartRenderer";
import { AreaChartRenderer } from "./AreaChartRenderer";
import { PieChartRenderer } from "./PieChartRenderer";
import { ScatterChartRenderer } from "./ScatterChartRenderer";
import { HistogramChartRenderer } from "./HistogramChartRenderer";
import { KpiRenderer } from "./KpiRenderer";
import { TableRenderer } from "./TableRenderer";
import { renderSharedChart } from "../../ChartComponents";

export function ChartRouter({
  chartType,
  data,
  columns = [],
  format = {},
  chartConfig = {},
  kpi = {},
  crossFilter = null,
  onPointClick = null,
  isInteractive = false,
}) {
  if (!data) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#71717a", fontSize: 12 }}>
        No chart data available
      </div>
    );
  }

  switch (chartType) {
    case "bar":
      return (
        <BarChartRenderer
          data={data}
          format={format}
          chartConfig={chartConfig}
          crossFilter={crossFilter}
          onPointClick={onPointClick}
          isInteractive={isInteractive}
        />
      );

    case "line":
      return (
        <LineChartRenderer
          data={data}
          format={format}
          chartConfig={chartConfig}
          crossFilter={crossFilter}
          onPointClick={onPointClick}
          isInteractive={isInteractive}
        />
      );

    case "area":
      return (
        <AreaChartRenderer
          data={data}
          format={format}
          chartConfig={chartConfig}
          crossFilter={crossFilter}
          onPointClick={onPointClick}
          isInteractive={isInteractive}
        />
      );

    case "pie":
      return (
        <PieChartRenderer
          data={data}
          format={format}
          chartConfig={chartConfig}
          isDonut={false}
          crossFilter={crossFilter}
          onPointClick={onPointClick}
          isInteractive={isInteractive}
        />
      );

    case "donut":
      return (
        <PieChartRenderer
          data={data}
          format={format}
          chartConfig={chartConfig}
          isDonut={true}
          crossFilter={crossFilter}
          onPointClick={onPointClick}
          isInteractive={isInteractive}
        />
      );

    case "scatter":
      return (
        <ScatterChartRenderer
          data={data}
          format={format}
          chartConfig={chartConfig}
          crossFilter={crossFilter}
          onPointClick={onPointClick}
          isInteractive={isInteractive}
        />
      );

    case "histogram":
      return (
        <HistogramChartRenderer
          data={data}
          format={format}
          chartConfig={chartConfig}
          crossFilter={crossFilter}
          onPointClick={onPointClick}
          isInteractive={isInteractive}
        />
      );

    case "kpi":
      return (
        <KpiRenderer
          data={data}
          kpi={kpi}
          chartConfig={chartConfig}
          format={format}
        />
      );

    case "table":
      return (
        <TableRenderer
          data={data}
          columns={columns}
          crossFilter={crossFilter}
          onPointClick={onPointClick}
          isInteractive={isInteractive}
        />
      );

    // Existing renderSharedChart for Heatmap, Box Plot, Map, Treemap, Waterfall, Funnel, Forecast
    case "heatmap":
    case "box_plot":
    case "map":
    case "treemap":
    case "waterfall":
    case "funnel":
    case "stacked_bar":
    case "stacked_bar_100":
    case "forecast_line":
    case "forecast_ci":
    case "forecast_actual":
    case "forecast_residual":
    default:
      return (
        <div style={{ width: "100%", height: "100%", position: "relative" }}>
          {renderSharedChart(
            chartType,
            data,
            chartConfig.xCol,
            chartConfig.yCol,
            chartConfig.agg
          )}
        </div>
      );
  }
}
