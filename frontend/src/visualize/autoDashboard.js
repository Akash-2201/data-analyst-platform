/**
 * frontend/src/visualize/autoDashboard.js
 * Rule-based smart recommendations and "Generate Dashboard" layout generator.
 */

import { CANVAS_W, CANVAS_H } from "./constants";
import { makePageId, makeTileId, createDefaultTile } from "./utils";

export function getSmartRecommendations(columns = []) {
  const recommendations = [];

  const categoricals = [];
  const numerics = [];
  const dates = [];
  let latCol = null;
  let lonCol = null;

  (columns || []).forEach((col) => {
    const name = typeof col === "string" ? col : col.name;
    const inferred = (col.inferred_type || col.dtype || "").toLowerCase();
    const nameLower = name.toLowerCase();
    const uniquePct = col.unique_pct ?? (col.unique_count && col.totalRows ? (col.unique_count / col.totalRows) * 100 : 50);

    if (nameLower.endsWith("_outlier") || nameLower.includes("_flag_") || nameLower.startsWith("is_")) {
      return;
    }

    if (nameLower.includes("lat")) latCol = name;
    else if (nameLower.includes("lon") || nameLower.includes("lng")) lonCol = name;

    if (inferred.includes("date") || inferred.includes("time") || nameLower.includes("date") || nameLower.includes("year")) {
      dates.push(name);
    } else if (inferred.includes("int") || inferred.includes("float") || inferred.includes("numeric") || col.numeric_stats) {
      if (uniquePct < 98) {
        numerics.push(name);
      }
    } else {
      if (uniquePct < 90) {
        categoricals.push({ name, uniqueCount: col.unique_count || 5 });
      }
    }
  });

  // Rule 1: Date + Numeric -> Line chart
  if (dates.length > 0 && numerics.length > 0) {
    recommendations.push({
      id: "rec-line",
      label: `Trend: ${numerics[0]} over ${dates[0]}`,
      chartType: "line",
      xCol: dates[0],
      yCol: numerics[0],
      agg: "sum",
      reason: "Date + Numeric detected",
    });
  }

  // Rule 2: Category + Numeric -> Bar chart
  if (categoricals.length > 0 && numerics.length > 0) {
    recommendations.push({
      id: "rec-bar",
      label: `${numerics[0]} by ${categoricals[0].name}`,
      chartType: "bar",
      xCol: categoricals[0].name,
      yCol: numerics[0],
      agg: "sum",
      reason: "Category + Metric distribution",
    });
  }

  // Rule 3: Low-cardinality category + Numeric -> Donut / Pie
  const lowCard = categoricals.find((c) => c.uniqueCount <= 8);
  if (lowCard && numerics.length > 0) {
    recommendations.push({
      id: "rec-donut",
      label: `Share of ${numerics[0]} by ${lowCard.name}`,
      chartType: "donut",
      xCol: lowCard.name,
      yCol: numerics[0],
      agg: "sum",
      reason: "Low-cardinality category detected",
    });
  }

  // Rule 4: Latitude + Longitude -> Map
  if (latCol && lonCol) {
    recommendations.push({
      id: "rec-map",
      label: `Geographic Map (${latCol}, ${lonCol})`,
      chartType: "map",
      xCol: lonCol,
      yCol: latCol,
      agg: "count",
      reason: "Coordinates detected",
    });
  }

  // Rule 5: Single Numeric -> Histogram
  if (numerics.length > 0) {
    recommendations.push({
      id: "rec-hist",
      label: `Distribution of ${numerics[0]}`,
      chartType: "histogram",
      xCol: numerics[0],
      yCol: "",
      agg: "count",
      reason: "Single numeric frequency",
    });
  }

  // Rule 6: Two Numerics -> Scatter Plot
  if (numerics.length >= 2) {
    recommendations.push({
      id: "rec-scatter",
      label: `Correlation: ${numerics[0]} vs ${numerics[1]}`,
      chartType: "scatter",
      xCol: numerics[0],
      yCol: numerics[1],
      agg: "none",
      reason: "Two numerics detected",
    });
  }

  return recommendations;
}

export function generateAutoDashboardPage(columns = [], existingPages = []) {
  const dates = [];
  const numerics = [];
  const categoricals = [];
  let latCol = null;
  let lonCol = null;

  (columns || []).forEach((col) => {
    const name = typeof col === "string" ? col : col.name;
    const inferred = (col.inferred_type || col.dtype || "").toLowerCase();
    const nameLower = name.toLowerCase();

    // Ignore flags and IDs
    if (nameLower.endsWith("_outlier") || nameLower.includes("_flag_") || nameLower.startsWith("is_")) return;
    if (nameLower === "id" || nameLower.endsWith("_id")) return;

    if (nameLower.includes("lat")) latCol = name;
    else if (nameLower.includes("lon") || nameLower.includes("lng")) lonCol = name;

    if (inferred.includes("date") || inferred.includes("time") || nameLower.includes("date") || nameLower.includes("year")) {
      dates.push(name);
    } else if (inferred.includes("int") || inferred.includes("float") || inferred.includes("numeric") || col.numeric_stats) {
      numerics.push(name);
    } else {
      categoricals.push(name);
    }
  });

  const tiles = [];
  let zIndex = 1;

  const primaryCol = numerics[0] || categoricals[0] || "ID";

  // 1. Top Row: 3 KPI Cards (y: 10, h: 120)
  // KPI 1: Total Records
  tiles.push(
    createDefaultTile("chart", {
      spot: { x: 10, y: 10 },
      w: 400,
      h: 120,
      z: zIndex++,
      title: "Total Records",
      chartConfig: { chartType: "kpi", xCol: primaryCol, yCol: primaryCol, agg: "count" },
    })
  );

  // KPI 2: Primary Numeric
  if (numerics.length > 0) {
    tiles.push(
      createDefaultTile("chart", {
        spot: { x: 430, y: 10 },
        w: 410,
        h: 120,
        z: zIndex++,
        title: `Total ${numerics[0]}`,
        chartConfig: { chartType: "kpi", xCol: numerics[0], yCol: numerics[0], agg: "sum" },
      })
    );
  }

  // KPI 3: Secondary Numeric (Average) or Category Count
  if (numerics.length > 1) {
    tiles.push(
      createDefaultTile("chart", {
        spot: { x: 860, y: 10 },
        w: 410,
        h: 120,
        z: zIndex++,
        title: `Average ${numerics[1]}`,
        chartConfig: { chartType: "kpi", xCol: numerics[1], yCol: numerics[1], agg: "avg" },
      })
    );
  } else if (numerics.length > 0) {
    tiles.push(
      createDefaultTile("chart", {
        spot: { x: 860, y: 10 },
        w: 410,
        h: 120,
        z: zIndex++,
        title: `Max ${numerics[0]}`,
        chartConfig: { chartType: "kpi", xCol: numerics[0], yCol: numerics[0], agg: "max" },
      })
    );
  }

  // 2. Middle Row: Trend Line + Category Bar (y: 140, h: 270)
  if (dates.length > 0 && numerics.length > 0) {
    tiles.push(
      createDefaultTile("chart", {
        spot: { x: 10, y: 140 },
        w: 630,
        h: 270,
        z: zIndex++,
        title: `${numerics[0]} Trend Over Time`,
        chartConfig: { chartType: "line", xCol: dates[0], yCol: numerics[0], agg: "sum" },
      })
    );
  }

  if (categoricals.length > 0 && numerics.length > 0) {
    const barX = dates.length > 0 ? 660 : 10;
    const barW = dates.length > 0 ? 610 : 1260;
    tiles.push(
      createDefaultTile("chart", {
        spot: { x: barX, y: 140 },
        w: barW,
        h: 270,
        z: zIndex++,
        title: `${numerics[0]} by ${categoricals[0]}`,
        chartConfig: { chartType: "bar", xCol: categoricals[0], yCol: numerics[0], agg: "sum", sort: "desc" },
      })
    );
  }

  // 3. Bottom Row: Donut Chart + Table or Map (y: 420, h: 290)
  if (categoricals.length > 1 && numerics.length > 0) {
    tiles.push(
      createDefaultTile("chart", {
        spot: { x: 10, y: 420 },
        w: 440,
        h: 290,
        z: zIndex++,
        title: `Share by ${categoricals[1]}`,
        chartConfig: { chartType: "donut", xCol: categoricals[1], yCol: numerics[0], agg: "sum" },
      })
    );
  }

  const rightVisualX = categoricals.length > 1 ? 470 : 10;
  const rightVisualW = categoricals.length > 1 ? 800 : 1260;

  if (latCol && lonCol) {
    tiles.push(
      createDefaultTile("chart", {
        spot: { x: rightVisualX, y: 420 },
        w: rightVisualW,
        h: 290,
        z: zIndex++,
        title: "Geographic Distribution",
        chartConfig: { chartType: "map", xCol: lonCol, yCol: latCol, agg: "count" },
      })
    );
  } else {
    // Table visual
    tiles.push(
      createDefaultTile("chart", {
        spot: { x: rightVisualX, y: 420 },
        w: rightVisualW,
        h: 290,
        z: zIndex++,
        title: "Data Table",
        chartConfig: { chartType: "table", xCol: categoricals[0] || primaryCol, yCol: numerics[0] || "", agg: "count" },
      })
    );
  }

  // Auto Dashboard page name (increments if exists)
  let baseName = "Auto Dashboard";
  let pageName = baseName;
  let counter = 2;
  while (existingPages.some((p) => p.name === pageName)) {
    pageName = `${baseName} ${counter++}`;
  }

  return {
    id: makePageId(),
    name: pageName,
    hidden: false,
    tiles,
    filters: [],
    crossFilter: null,
  };
}
