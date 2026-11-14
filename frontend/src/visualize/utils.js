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
