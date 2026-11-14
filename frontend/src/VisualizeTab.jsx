/**
 * frontend/src/VisualizeTab.jsx
 * Thin wrapper mounting the modular Power BI-style Dashboard Builder.
 */

import React from "react";
import { DashboardShell } from "./visualize/DashboardShell";
import { ChartTileContent } from "./visualize/ChartTileContent";
import { makeInitialDashboard } from "./visualize/utils";

export function makeInitialReportState(name) {
  return makeInitialDashboard(name);
}

export default function VisualizeTab({
  datasetId,
  columns = [],
  datasetFilename = "Dashboard",
  userId = "default",
}) {
  return (
    <DashboardShell
      datasetId={datasetId}
      columns={columns}
      datasetFilename={datasetFilename}
      userId={userId}
      renderTileContent={(tile) => (
        <ChartTileContent
          tile={tile}
          datasetId={datasetId}
          columns={columns}
        />
      )}
    />
  );
}
