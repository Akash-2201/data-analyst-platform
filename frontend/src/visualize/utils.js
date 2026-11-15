/**
 * frontend/src/visualize/utils.js
 * Conversion, math, formatting, and layout utilities.
 */

import {
  CANVAS_W,
  CANVAS_H,
  CELL_SNAP,
  CELL_FREE,
  DEFAULT_TILE_W,
  DEFAULT_TILE_H,
  MIN_TILE_W,
  MIN_TILE_H,
  DEFAULT_FORMAT,
  DEFAULT_CHART_CONFIG,
} from "./constants";

export function makeId(prefix = "id") {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

export function makePageId() {
  return makeId("pg");
}

export function makeTileId(kind = "chart") {
  return makeId(`tile-${kind}`);
}

export function makeEmptyPage(name = "Page 1") {
  return {
    id: makePageId(),
    name,
    hidden: false,
    tiles: [],
    filters: [],
    crossFilter: null,
  };
}

export function makeInitialDashboard(datasetFilename = "Dashboard") {
  const firstPage = makeEmptyPage("Page 1");
  return {
    id: makeId("dash"),
    name: datasetFilename ? `${datasetFilename.replace(/\.[^/.]+$/, "")} Dashboard` : "Analytics Dashboard",
    activePageId: firstPage.id,
    mode: "edit",
    settings: {
      snap: true,
      showGrid: true,
      autoAlign: false,
    },
    pages: [firstPage],
    selectedTileIds: [],
    clipboard: null,
  };
}

export function getGridCell(snap = true) {
  return snap ? CELL_SNAP : CELL_FREE;
}

export function pxToGrid(px, snap = true) {
  const cell = getGridCell(snap);
  return Math.round(px / cell);
}

export function gridToPx(gridUnits, snap = true) {
  const cell = getGridCell(snap);
  return gridUnits * cell;
}

export function clamp(val, min, max) {
  return Math.max(min, Math.min(max, val));
}

export function clampTilePx(x, y, w, h) {
  const clampedW = clamp(w, MIN_TILE_W, CANVAS_W);
  const clampedH = clamp(h, MIN_TILE_H, CANVAS_H);
  const clampedX = clamp(x, 0, Math.max(0, CANVAS_W - clampedW));
  const clampedY = clamp(y, 0, Math.max(0, CANVAS_H - clampedH));
  return { x: clampedX, y: clampedY, w: clampedW, h: clampedH };
}

export function tileToRglLayout(tile, snap = true) {
  const cell = getGridCell(snap);
  const gx = Math.round(tile.x / cell);
  const gy = Math.round(tile.y / cell);
  const gw = Math.max(Math.round(MIN_TILE_W / cell), Math.round(tile.w / cell));
  const gh = Math.max(Math.round(MIN_TILE_H / cell), Math.round(tile.h / cell));

  return {
    i: tile.id,
    x: gx,
    y: gy,
    w: gw,
    h: gh,
    minW: Math.round(MIN_TILE_W / cell),
    minH: Math.round(MIN_TILE_H / cell),
  };
}

export function rglLayoutToTilePx(item, snap = true) {
  const cell = getGridCell(snap);
  const pxX = item.x * cell;
  const pxY = item.y * cell;
  const pxW = item.w * cell;
  const pxH = item.h * cell;
  return clampTilePx(pxX, pxY, pxW, pxH);
}

export function findFirstFreeSpot(tiles = [], w = DEFAULT_TILE_W, h = DEFAULT_TILE_H) {
  const step = 20;
  for (let y = 0; y <= CANVAS_H - h; y += step) {
    for (let x = 0; x <= CANVAS_W - w; x += step) {
      const collides = tiles.some((t) => {
        return x < t.x + t.w && x + w > t.x && y < t.y + t.h && y + h > t.y;
      });
      if (!collides) {
        return { x, y };
      }
    }
  }
  return { x: 0, y: 0 };
}

export function createDefaultTile(kind = "chart", options = {}) {
  const spot = options.spot || { x: 0, y: 0 };
  const w = options.w || (kind === "slicer" ? 280 : kind === "text" ? 440 : DEFAULT_TILE_W);
  const h = options.h || (kind === "slicer" ? 180 : kind === "text" ? 100 : DEFAULT_TILE_H);

  return {
    id: makeTileId(kind),
    kind,
    x: spot.x,
    y: spot.y,
    w,
    h,
    z: options.z || 1,
    groupId: null,
    title: options.title || (kind === "text" ? "Dashboard Title" : kind === "slicer" ? "Filter" : "New Chart"),
    chartConfig: {
      ...DEFAULT_CHART_CONFIG,
      ...(options.chartConfig || {}),
    },
    format: {
      ...DEFAULT_FORMAT,
      ...(options.format || {}),
    },
    interaction: "filter",
    text: {
      value: options.textValue || "Click to edit text",
      size: "title",
      align: "left",
      bold: true,
      ...(options.text || {}),
    },
    slicer: {
      col: options.slicerCol || "",
      type: "dropdown",
      selected: [],
      ...(options.slicer || {}),
    },
    kpi: {
      prefix: "",
      suffix: "",
      ...(options.kpi || {}),
    },
  };
}

export function formatIndianNumber(num) {
  if (num === null || num === undefined || isNaN(num)) return "-";
  const abs = Math.abs(num);
  if (abs >= 10000000) {
    return `${(num / 10000000).toFixed(2)} Cr`;
  }
  if (abs >= 100000) {
    return `${(num / 100000).toFixed(2)} L`;
  }
  return Number(num).toLocaleString("en-IN");
}

export function isStrictDateString(val) {
  if (val === null || val === undefined) return false;
  const s = String(val).trim();
  if (!s || /^\d+(\.\d+)?$/.test(s)) return false;

  // YYYY-MM-DD, YYYY/MM/DD
  const m1 = s.match(/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})/);
  if (m1) {
    const m = parseInt(m1[2], 10);
    const d = parseInt(m1[3], 10);
    return m >= 1 && m <= 12 && d >= 1 && d <= 31;
  }

  // DD-MM-YYYY, DD/MM/YYYY
  const m2 = s.match(/^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})/);
  if (m2) {
    const d = parseInt(m2[1], 10);
    const m = parseInt(m2[2], 10);
    return m >= 1 && m <= 12 && d >= 1 && d <= 31;
  }

  // ISO with T (e.g. 2026-09-16T10:30:00)
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s)) {
    return true;
  }

  // Month D, YYYY (e.g. "September 16, 2026")
  if (/^[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}/.test(s)) {
    return true;
  }

  return false;
}

export function classifyColumn(col) {
  const name = typeof col === "string" ? col : (col && col.name) || "";
  const nameLower = name.toLowerCase();
  const inferred = ((col && (col.inferred_type || col.dtype)) || "").toLowerCase();
  const samples = (col && col.sample_values) || [];

  // 1. Flags & Boolean
  if (
    nameLower.endsWith("_outlier") ||
    nameLower.includes("_flag_") ||
    nameLower.startsWith("is_") ||
    nameLower.startsWith("has_") ||
    inferred.includes("bool")
  ) {
    return { name, group: "Flags", subType: "boolean", isMeasure: false, defaultAgg: "count" };
  }

  // 2. Location: latitude / longitude coordinates
  if (
    /^lat(itude)?$/i.test(nameLower) ||
    /^(lon|lng|longitude)$/i.test(nameLower)
  ) {
    return { name, group: "LOCATION", subType: "coordinate", isMeasure: false, defaultAgg: "avg" };
  }

  // 3. Date: >= 80% non-blank values match strict date pattern
  const nonBlankSamples = samples.filter((v) => v !== null && v !== undefined && String(v).trim() !== "");
  if (nonBlankSamples.length > 0) {
    const dateCount = nonBlankSamples.filter(isStrictDateString).length;
    if (dateCount / nonBlankSamples.length >= 0.8) {
      return { name, group: "DATE", subType: "date", isMeasure: false, defaultAgg: "count" };
    }
  }
  if (inferred.includes("date") || inferred.includes("time")) {
    if (!samples.some((s) => /^\d+(\.\d+)?$/.test(String(s).trim()))) {
      return { name, group: "DATE", subType: "date", isMeasure: false, defaultAgg: "count" };
    }
  }

  // 4. Identifier / Phone / Code / Email -> TEXT / Identifier
  if (/(phone|mobile|contact)/i.test(nameLower)) {
    return { name, group: "TEXT/Identifier", subType: "Identifier", isMeasure: false, defaultAgg: "count" };
  }
  if (/(id|code|key|zip|pin)$/i.test(nameLower) || nameLower === "id") {
    return { name, group: "TEXT/Identifier", subType: "Identifier", isMeasure: false, defaultAgg: "count" };
  }
  if (nameLower.includes("email")) {
    return { name, group: "TEXT", subType: "text", isMeasure: false, defaultAgg: "count" };
  }

  // 5. Numerical measure vs numeric attribute
  const numericSamples = nonBlankSamples.filter((v) => {
    const clean = String(v).replace(/,/g, "").trim();
    return clean !== "" && !isNaN(Number(clean));
  });
  const isNumeric =
    (nonBlankSamples.length > 0 && numericSamples.length / nonBlankSamples.length >= 0.8) ||
    inferred.includes("int") ||
    inferred.includes("float") ||
    inferred.includes("numeric") ||
    inferred.includes("currency") ||
    !!(col && col.numeric_stats);

  if (isNumeric) {
    // Check if ID-like uniformly formatted number (e.g. 10-digit phone or zip)
    const isUniformLongDigits = nonBlankSamples.length > 0 && nonBlankSamples.every((v) => /^\d{10}$/.test(String(v).trim()));
    if (isUniformLongDigits) {
      return { name, group: "TEXT/Identifier", subType: "Identifier", isMeasure: false, defaultAgg: "count" };
    }

    const defaultAgg = /(age|rating|score|percent|rate|price)/i.test(nameLower) ? "avg" : "sum";
    const isMeasure = !/(age|phone|zip|pin|year|month|day|id)/i.test(nameLower);

    return {
      name,
      group: "NUMERICAL",
      subType: defaultAgg,
      isMeasure,
      defaultAgg,
    };
  }

  // 6. Otherwise TEXT
  return { name, group: "TEXT", subType: "text", isMeasure: false, defaultAgg: "count" };
}
