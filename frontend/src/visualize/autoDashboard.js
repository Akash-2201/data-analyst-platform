/**
 * frontend/src/visualize/autoDashboard.js
 * Rule-based smart recommendations and "Generate Dashboard" layout generator.
 */

import { CANVAS_W, CANVAS_H } from "./constants";
import { makePageId, makeTileId, createDefaultTile, classifyColumn } from "./utils";

export function getSmartRecommendations(columns = []) {
  const recommendations = [];

  const classified = (columns || []).map(classifyColumn);

  // 1. Measures (Amount, Quantity) - STRICTLY numeric measures, excluding Age, Phone, IDs, Coordinates
  const measures = classified.filter((c) => c.group === "NUMERICAL" && c.isMeasure);
  // Numeric attributes that are NOT measures (e.g. Age)
  const numericAttributes = classified.filter((c) => c.group === "NUMERICAL" && !c.isMeasure);

  // 2. Dates
  const dates = classified.filter((c) => c.group === "DATE");

  // 3. Categoricals (Text, excluding identifiers, with distinct value counts)
  const categoricals = [];
  (columns || []).forEach((rawCol) => {
    const info = classifyColumn(rawCol);
    if (info.group === "TEXT" && info.subType !== "Identifier") {
      const distinctCount = rawCol.unique_count ?? (rawCol.sample_values ? new Set(rawCol.sample_values).size : 5);
      categoricals.push({ ...info, distinctCount });
    }
  });

  // Coordinates
  const latCol = classified.find((c) => /^lat(itude)?$/i.test(c.name));
  const lonCol = classified.find((c) => /^(lon|lng|longitude)$/i.test(c.name));

  const primaryMeasure = measures[0]?.name || "Amount";

  // Recommendation 1: Line Chart (Date + Measure, Month Grain)
  if (dates.length > 0 && measures.length > 0) {
    recommendations.push({
      id: "rec-line",
      label: `${primaryMeasure} by ${dates[0].name} (month)`,
      chartType: "line",
      xCol: dates[0].name,
      yCol: primaryMeasure,
      agg: "sum",
      dateGrain: "month",
      reason: `Monthly trend of ${primaryMeasure} over time`,
    });
  }

  // Recommendation 2: Bar Chart (Category/Dimension + Measure)
  const barCat =
    categoricals.find((c) => /^(category|type|status|dept|segment|product)/i.test(c.name)) ||
    categoricals.find((c) => c.distinctCount <= 12 && !/name|email|phone/i.test(c.name) && c.name.toLowerCase() !== "city") ||
    categoricals.find((c) => c.distinctCount <= 12);
  if (barCat && measures.length > 0) {
    recommendations.push({
      id: "rec-bar",
      label: `${primaryMeasure} by ${barCat.name}`,
      chartType: "bar",
      xCol: barCat.name,
      yCol: primaryMeasure,
      agg: "sum",
      sort: "desc",
      reason: `Total ${primaryMeasure} by ${barCat.name}`,
    });
  }

  // Recommendation 3: Donut Chart (City/Distribution + Measure)
  const donutCat =
    categoricals.find((c) => /^(city|region|state|channel|device)/i.test(c.name) && c.name !== barCat?.name) ||
    categoricals.find((c) => c.distinctCount <= 8 && c.name !== barCat?.name) ||
    categoricals.find((c) => c.distinctCount <= 8);
  if (donutCat && measures.length > 0) {
    recommendations.push({
      id: "rec-donut",
      label: `${primaryMeasure} by ${donutCat.name}`,
      chartType: "donut",
      xCol: donutCat.name,
      yCol: primaryMeasure,
      agg: "sum",
      reason: `Share of ${primaryMeasure} across ${donutCat.name}`,
    });
  }

  // Recommendation 4: Histogram of a numeric attribute (like Age)
  const histAttr = numericAttributes[0]?.name || (measures.length > 1 ? measures[1].name : null);
  if (histAttr) {
    recommendations.push({
      id: "rec-hist",
      label: `Histogram of ${histAttr}`,
      chartType: "histogram",
      xCol: histAttr,
      yCol: "",
      agg: "count",
      reason: `Frequency distribution of ${histAttr}`,
    });
  }

  // Recommendation 5: Scatter (Two measures) - only if < 4
  if (measures.length >= 2 && recommendations.length < 4) {
    recommendations.push({
      id: "rec-scatter",
      label: `Correlation: ${measures[0].name} vs ${measures[1].name}`,
      chartType: "scatter",
      xCol: measures[0].name,
      yCol: measures[1].name,
      agg: "none",
      reason: `Measure correlation between ${measures[0].name} and ${measures[1].name}`,
    });
  }

  // Recommendation 6: Map - only if valid lat/lon exist and < 4
  if (latCol && lonCol && recommendations.length < 4) {
    recommendations.push({
      id: "rec-map",
      label: `Geographic Map (${latCol.name}, ${lonCol.name})`,
      chartType: "map",
      xCol: lonCol.name,
      yCol: latCol.name,
      agg: "count",
      reason: "Coordinates distribution",
    });
  }

  return recommendations.slice(0, 4);
}

export function generateAutoDashboardPage(columns = [], existingPages = []) {
  const classified = (columns || []).map(classifyColumn);
  const measures = classified.filter((c) => c.group === "NUMERICAL" && c.isMeasure);
  const numericAttributes = classified.filter((c) => c.group === "NUMERICAL" && !c.isMeasure);
  const dates = classified.filter((c) => c.group === "DATE");
  const categoricals = [];
  (columns || []).forEach((rawCol) => {
    const info = classifyColumn(rawCol);
    if (info.group === "TEXT" && info.subType !== "Identifier") {
      const distinctCount = rawCol.unique_count ?? (rawCol.sample_values ? new Set(rawCol.sample_values).size : 5);
      categoricals.push({ ...info, distinctCount });
    }
  });

  const latCol = classified.find((c) => /^lat(itude)?$/i.test(c.name));
  const lonCol = classified.find((c) => /^(lon|lng|longitude)$/i.test(c.name));

  const tiles = [];
  let zIndex = 1;

  const primaryMeasure = measures[0]?.name || "Amount";
  const secondaryMeasure = measures[1]?.name || null;
  const numAttr = numericAttributes[0]?.name || null;

  // 1. Top Row: 3 KPI Cards (y: 10, h: 120)
  // KPI 1: Total Records
  tiles.push(
    createDefaultTile("chart", {
      spot: { x: 10, y: 10 },
      w: 400,
      h: 120,
      z: zIndex++,
      title: "Total Records",
      chartConfig: { chartType: "kpi", xCol: primaryMeasure, yCol: primaryMeasure, agg: "count" },
    })
  );

  // KPI 2: Primary Measure (Amount)
  if (primaryMeasure) {
    tiles.push(
      createDefaultTile("chart", {
        spot: { x: 430, y: 10 },
        w: 410,
        h: 120,
        z: zIndex++,
        title: `Total ${primaryMeasure}`,
        chartConfig: { chartType: "kpi", xCol: primaryMeasure, yCol: primaryMeasure, agg: "sum" },
      })
    );
  }

  // KPI 3: Secondary Measure (Quantity) or Average Numeric Attribute (Age)
  if (secondaryMeasure) {
    tiles.push(
      createDefaultTile("chart", {
        spot: { x: 860, y: 10 },
        w: 410,
        h: 120,
        z: zIndex++,
        title: `Total ${secondaryMeasure}`,
        chartConfig: { chartType: "kpi", xCol: secondaryMeasure, yCol: secondaryMeasure, agg: "sum" },
      })
    );
  } else if (numAttr) {
    tiles.push(
      createDefaultTile("chart", {
        spot: { x: 860, y: 10 },
        w: 410,
        h: 120,
        z: zIndex++,
        title: `Average ${numAttr}`,
        chartConfig: { chartType: "kpi", xCol: numAttr, yCol: numAttr, agg: "avg" },
      })
    );
  }

  // 2. Middle Row: Trend Line + Category Bar (y: 140, h: 270)
  if (dates.length > 0 && primaryMeasure) {
    tiles.push(
      createDefaultTile("chart", {
        spot: { x: 10, y: 140 },
        w: 630,
        h: 270,
        z: zIndex++,
        title: `${primaryMeasure} by ${dates[0].name} (month)`,
        chartConfig: { chartType: "line", xCol: dates[0].name, yCol: primaryMeasure, agg: "sum", dateGrain: "month" },
      })
    );
  }

  const barCat =
    categoricals.find((c) => c.distinctCount <= 12 && c.name.toLowerCase() !== "city") ||
    categoricals.find((c) => c.distinctCount <= 12);
  if (barCat && primaryMeasure) {
    const barX = dates.length > 0 ? 660 : 10;
    const barW = dates.length > 0 ? 610 : 1260;
    tiles.push(
      createDefaultTile("chart", {
        spot: { x: barX, y: 140 },
        w: barW,
        h: 270,
        z: zIndex++,
        title: `${primaryMeasure} by ${barCat.name}`,
        chartConfig: { chartType: "bar", xCol: barCat.name, yCol: primaryMeasure, agg: "sum", sort: "desc" },
      })
    );
  }

  // 3. Bottom Row: Donut Chart + Histogram or Map (y: 420, h: 290)
  const donutCat =
    categoricals.find((c) => c.distinctCount <= 8 && c.name !== barCat?.name) ||
    categoricals.find((c) => c.distinctCount <= 8);
  if (donutCat && primaryMeasure) {
    tiles.push(
      createDefaultTile("chart", {
        spot: { x: 10, y: 420 },
        w: 440,
        h: 290,
        z: zIndex++,
        title: `${primaryMeasure} by ${donutCat.name}`,
        chartConfig: { chartType: "donut", xCol: donutCat.name, yCol: primaryMeasure, agg: "sum" },
      })
    );
  }

  const rightVisualX = donutCat ? 470 : 10;
  const rightVisualW = donutCat ? 800 : 1260;

  if (numAttr) {
    tiles.push(
      createDefaultTile("chart", {
        spot: { x: rightVisualX, y: 420 },
        w: rightVisualW,
        h: 290,
        z: zIndex++,
        title: `Histogram of ${numAttr}`,
        chartConfig: { chartType: "histogram", xCol: numAttr, yCol: "", agg: "count" },
      })
    );
  } else if (latCol && lonCol) {
    tiles.push(
      createDefaultTile("chart", {
        spot: { x: rightVisualX, y: 420 },
        w: rightVisualW,
        h: 290,
        z: zIndex++,
        title: "Geographic Distribution",
        chartConfig: { chartType: "map", xCol: lonCol.name, yCol: latCol.name, agg: "count" },
      })
    );
  }

  // Auto Dashboard page name
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
