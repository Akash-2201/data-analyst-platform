/**
 * VisualizeTab.jsx — Power BI-style Multi-Page Report Canvas
 *
 * Implements:
 * - Multi-page report state model (owned by App.jsx, persists across tab switches)
 * - Bottom tab bar: add, rename, duplicate, delete, reorder
 * - Fixed 16:9 canvas (1280×720) with CSS-transform scaling & transformScale prop
 * - react-grid-layout: cols=24, rowHeight=22, compactType={null}, preventCollision={true}
 * - Chart tiles: renderSharedChart with ResponsiveContainer filled cleanly via React.cloneElement
 * - Text tiles: editable text with title/subtitle/body fontSize, align, bold
 * - Inspector sidebar for selected tile (chart gallery + axis dropdowns, text formatting)
 * - Tile hover toolbar (edit, duplicate, delete)
 * - Undo/Redo history stack
 * - Multi-page landscape PDF export via html2canvas & jsPDF with progress indicator
 * - Mobile responsive safety
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactGridLayout from "react-grid-layout";
import html2canvas from "html2canvas";
import { jsPDF } from "jspdf";
import "react-grid-layout/css/styles.css";
import "./VisualizeTab.css";
import { getChartData } from "./api";
import {
  CHART_GALLERY_TYPES,
  renderSharedChart,
} from "./ChartComponents";

// ---------------------------------------------------------------------------
// Canvas & Grid Constants (16:9 at 1280×720 logical px)
// ---------------------------------------------------------------------------
export const CANVAS_W = 1280;
export const CANVAS_H = 720;
export const GRID_COLS = 24;
export const GRID_ROW_HEIGHT = 22; // 24 * (22 + 8) + 8 = 728px ~ 720px
export const GRID_MARGIN = [8, 8];

// ---------------------------------------------------------------------------
// State Factory Helpers
// ---------------------------------------------------------------------------
export function makePageId() {
  return `pg-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

export function makeTileId(kind = "chart") {
  return `tile-${kind}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

export function makeEmptyPage(name = "Page 1") {
  return { id: makePageId(), name, tiles: [] };
}

export function makeInitialReportState() {
  const firstPage = makeEmptyPage("Page 1");
  return {
    activePageId: firstPage.id,
    pages: [firstPage],
  };
}

// ---------------------------------------------------------------------------
// Shared Chart Data Fetching
// ---------------------------------------------------------------------------
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
  else if (
    chartType.startsWith("forecast_") ||
    chartType === "line" ||
    chartType === "scatter" ||
    chartType === "area" ||
    chartType === "waterfall" ||
    (chartType === "bar" && agg !== "count")
  )
    fetchY = yCol;
  else if (chartType === "map" && yCol) fetchY = yCol;
  else fetchY = undefined;

  const fetchX = xCol || (isKPI ? (yCol || "") : "");

  const data = await getChartData(datasetId, {
    chartType,
    x: fetchX,
    y: fetchY,
    agg,
    useCleaned: true,
  });

  chartDataMemoryCache.set(cacheKey, data);
  return data;
}

// ---------------------------------------------------------------------------
// Chart Tile Content
// ---------------------------------------------------------------------------
function ChartTileContent({ tile, datasetId, chartDataOverride }) {
  const [data, setData] = useState(chartDataOverride || null);
  const [loading, setLoading] = useState(!chartDataOverride);
  const [error, setError] = useState(null);

  const { chartConfig } = tile;

  useEffect(() => {
    if (chartDataOverride) {
      setData(chartDataOverride);
      setLoading(false);
      return;
    }

    let active = true;
    if (!datasetId) {
      setLoading(false);
      return;
    }

    const isHeatmap = chartConfig.chartType === "heatmap";
    const isKPI = chartConfig.chartType === "kpi";
    if (!isHeatmap && !isKPI && !chartConfig.xCol) {
      setData(null);
      setLoading(false);
      return;
    }

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
          setError(err.message || "Failed to generate chart.");
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [
    chartDataOverride,
    datasetId,
    chartConfig.chartType,
    chartConfig.xCol,
    chartConfig.yCol,
    chartConfig.stackCol,
    chartConfig.agg,
  ]);

  if (loading) {
    return (
      <div className="rpt-tile-loading">
        <div className="ledger-loading-track" style={{ width: 140 }}>
          <div className="ledger-loading-bar" />
        </div>
        <span style={{ fontSize: 11, opacity: 0.8 }}>Generating chart…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rpt-tile-error">
        <div style={{ fontWeight: 600, fontSize: 12 }}>Unable to render chart</div>
        <div style={{ fontSize: 11, opacity: 0.85 }}>{error}</div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="rpt-tile-placeholder">
        <span>Click to select chart parameters</span>
      </div>
    );
  }

  let rendered = renderSharedChart(data, chartConfig.chartType);
  if (React.isValidElement(rendered) && rendered.props?.height) {
    rendered = React.cloneElement(rendered, { height: "100%" });
  }

  return <div className="rpt-tile-chart-container">{rendered}</div>;
}

// ---------------------------------------------------------------------------
// Text Tile Content
// ---------------------------------------------------------------------------
function TextTileContent({ tile, isSelected, onUpdate }) {
  const fontSizeClass =
    tile.fontSize === "title"
      ? "rpt-text-title"
      : tile.fontSize === "subtitle"
      ? "rpt-text-subtitle"
      : "rpt-text-body";

  const textAlign = tile.align || "left";
  const fontWeight = tile.bold ? "bold" : "normal";

  return (
    <div className={`rpt-text-tile ${fontSizeClass}`} style={{ textAlign, fontWeight }}>
      {isSelected ? (
        <textarea
          className="rpt-text-tile-input"
          value={tile.text}
          onChange={(e) => onUpdate({ text: e.target.value })}
          placeholder="Enter text..."
          autoFocus
        />
      ) : (
        <div className="rpt-text-tile-display">
          {tile.text || <span className="rpt-text-placeholder">Double-click or edit in sidebar</span>}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main VisualizeTab Component
// ---------------------------------------------------------------------------
export default function VisualizeTab({
  reportState,
  setReportState,
  datasetId,
  columns = [],
  datasetFilename,
}) {
  const allCols = useMemo(() => columns || [], [columns]);

  // Derived state
  const { activePageId, pages } = reportState;
  const activePage = useMemo(
    () => pages.find((p) => p.id === activePageId) ?? pages[0] ?? makeEmptyPage(),
    [pages, activePageId]
  );

  // Selection & UI state
  const [selectedTileId, setSelectedTileId] = useState(null);
  const selectedTile = useMemo(
    () => activePage?.tiles?.find((t) => t.id === selectedTileId) ?? null,
    [activePage, selectedTileId]
  );

  // Tab renaming & confirmation
  const dragTabIdx = useRef(null);
  const [renamingPageId, setRenamingPageId] = useState(null);
  const [renameValue, setRenameValue] = useState("");
  const [deleteConfirmId, setDeleteConfirmId] = useState(null);

  // Canvas scaling
  const canvasAreaRef = useRef(null);
  const [canvasScale, setCanvasScale] = useState(1);

  // Undo / Redo history stacks
  const pastRef = useRef([]);
  const futureRef = useRef([]);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);

  // PDF Export state
  const [isExporting, setIsExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState({ current: 0, total: 0 });
  const [exportError, setExportError] = useState(null);
  const exportStageRef = useRef(null);
  const [exportStagePage, setExportStagePage] = useState(null);

  // ── History management ────────────────────────────────────────────────────
  const pushHistory = useCallback(
    (currentState = reportState) => {
      pastRef.current = [...pastRef.current.slice(-49), JSON.parse(JSON.stringify(currentState))];
      futureRef.current = [];
      setCanUndo(true);
      setCanRedo(false);
    },
    [reportState]
  );

  const handleUndo = useCallback(() => {
    if (pastRef.current.length === 0) return;
    const prev = pastRef.current.pop();
    futureRef.current.push(JSON.parse(JSON.stringify(reportState)));
    setReportState(prev);
    setCanUndo(pastRef.current.length > 0);
    setCanRedo(true);
    setSelectedTileId(null);
  }, [reportState, setReportState]);

  const handleRedo = useCallback(() => {
    if (futureRef.current.length === 0) return;
    const next = futureRef.current.pop();
    pastRef.current.push(JSON.parse(JSON.stringify(reportState)));
    setReportState(next);
    setCanUndo(true);
    setCanRedo(futureRef.current.length > 0);
    setSelectedTileId(null);
  }, [reportState, setReportState]);

  // ── Keyboard shortcuts: Undo (Ctrl+Z) / Redo (Ctrl+Y or Ctrl+Shift+Z) ────
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Don't trigger if user is actively typing in an input or textarea
      const tag = e.target.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea") return;

      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === "z") {
        e.preventDefault();
        handleUndo();
      } else if (
        ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") ||
        ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "z")
      ) {
        e.preventDefault();
        handleRedo();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleUndo, handleRedo]);

  // ── Canvas auto-scaling ───────────────────────────────────────────────────
  useEffect(() => {
    const updateScale = () => {
      if (!canvasAreaRef.current) return;
      const { clientWidth, clientHeight } = canvasAreaRef.current;
      const availW = Math.max(320, clientWidth - 36);
      const availH = Math.max(240, clientHeight - 36);
      const scaleW = availW / CANVAS_W;
      const scaleH = availH / CANVAS_H;
      // Fit within both dimensions so 16:9 canvas is fully visible
      const s = Math.min(1, Math.min(scaleW, scaleH));
      setCanvasScale(Number(s.toFixed(3)));
    };

    updateScale();
    const ro = new ResizeObserver(updateScale);
    if (canvasAreaRef.current) ro.observe(canvasAreaRef.current);
    window.addEventListener("resize", updateScale);

    return () => {
      ro.disconnect();
      window.removeEventListener("resize", updateScale);
    };
  }, [selectedTileId]); // re-measure when sidebar toggles

  // ── Page operations ───────────────────────────────────────────────────────
  const setPages = useCallback(
    (updater) => {
      setReportState((prev) => ({
        ...prev,
        pages: typeof updater === "function" ? updater(prev.pages) : updater,
      }));
    },
    [setReportState]
  );

  const handleAddPage = () => {
    pushHistory();
    const newPage = makeEmptyPage(`Page ${pages.length + 1}`);
    setReportState((prev) => ({
      ...prev,
      pages: [...prev.pages, newPage],
      activePageId: newPage.id,
    }));
    setSelectedTileId(null);
  };

  const handleStartRename = (page) => {
    setRenamingPageId(page.id);
    setRenameValue(page.name);
  };

  const handleCommitRename = () => {
    if (!renamingPageId) return;
    const trimmed = renameValue.trim();
    if (trimmed) {
      pushHistory();
      setPages((prev) =>
        prev.map((p) => (p.id === renamingPageId ? { ...p, name: trimmed } : p))
      );
    }
    setRenamingPageId(null);
  };

  const handleDuplicatePage = (page) => {
    pushHistory();
    const copy = {
      ...page,
      id: makePageId(),
      name: `${page.name} (copy)`,
      tiles: page.tiles.map((t) => ({
        ...t,
        id: makeTileId(t.kind),
      })),
    };
    setReportState((prev) => {
      const idx = prev.pages.findIndex((p) => p.id === page.id);
      const newPages = [...prev.pages];
      newPages.splice(idx + 1, 0, copy);
      return { ...prev, pages: newPages, activePageId: copy.id };
    });
    setSelectedTileId(null);
  };

  const handleDeletePage = (pageId) => {
    if (pages.length === 1) return;
    pushHistory();
    setReportState((prev) => {
      const idx = prev.pages.findIndex((p) => p.id === pageId);
      const newPages = prev.pages.filter((p) => p.id !== pageId);
      const newActive =
        prev.activePageId === pageId
          ? newPages[Math.max(0, idx - 1)]?.id ?? newPages[0]?.id
          : prev.activePageId;
      return { pages: newPages, activePageId: newActive };
    });
    setDeleteConfirmId(null);
    setSelectedTileId(null);
  };

  const handleTabDragStart = (idx) => {
    dragTabIdx.current = idx;
  };

  const handleTabDrop = (targetIdx) => {
    const fromIdx = dragTabIdx.current;
    if (fromIdx === null || fromIdx === targetIdx) return;
    pushHistory();
    setPages((prev) => {
      const arr = [...prev];
      const [moved] = arr.splice(fromIdx, 1);
      arr.splice(targetIdx, 0, moved);
      return arr;
    });
    dragTabIdx.current = null;
  };

  // ── Tile operations ───────────────────────────────────────────────────────
  const handleAddTitle = () => {
    pushHistory();
    const newTile = {
      id: makeTileId("text"),
      kind: "text",
      layout: { x: 0, y: 0, w: 12, h: 2, minW: 3, minH: 1 },
      text: "Dashboard Title",
      fontSize: "title",
      align: "left",
      bold: true,
    };
    setPages((prev) =>
      prev.map((p) => (p.id === activePageId ? { ...p, tiles: [...p.tiles, newTile] } : p))
    );
    setSelectedTileId(newTile.id);
  };

  const handleAddChart = (chartType = "bar") => {
    pushHistory();
    const maxY = activePage.tiles.reduce(
      (max, t) => Math.max(max, (t.layout?.y || 0) + (t.layout?.h || 0)),
      0
    );

    const defaultX = allCols[0]?.name || "";
    const defaultY = allCols.length > 1 ? allCols[1]?.name : allCols[0]?.name || "";
    const defaultStack = allCols.length > 2 ? allCols[2]?.name : "";

    const newTile = {
      id: makeTileId("chart"),
      kind: "chart",
      layout: {
        x: 0,
        y: Math.min(maxY, 14),
        w: 12,
        h: 10,
        minW: 6,
        minH: 5,
      },
      chartConfig: {
        chartType,
        xCol: defaultX,
        yCol: defaultY,
        stackCol: defaultStack,
        agg: "count",
      },
    };

    setPages((prev) =>
      prev.map((p) => (p.id === activePageId ? { ...p, tiles: [...p.tiles, newTile] } : p))
    );
    setSelectedTileId(newTile.id);
  };

  const handleDuplicateTile = (tile) => {
    pushHistory();
    const copy = {
      ...JSON.parse(JSON.stringify(tile)),
      id: makeTileId(tile.kind),
      layout: {
        ...tile.layout,
        x: Math.min(tile.layout.x + 1, GRID_COLS - tile.layout.w),
        y: Math.min(tile.layout.y + 1, 14),
      },
    };
    setPages((prev) =>
      prev.map((p) => (p.id === activePageId ? { ...p, tiles: [...p.tiles, copy] } : p))
    );
    setSelectedTileId(copy.id);
  };

  const handleDeleteTile = (tileId) => {
    pushHistory();
    setPages((prev) =>
      prev.map((p) =>
        p.id === activePageId
          ? { ...p, tiles: p.tiles.filter((t) => t.id !== tileId) }
          : p
      )
    );
    if (selectedTileId === tileId) setSelectedTileId(null);
  };

  const handleUpdateTile = (tileId, updates) => {
    setPages((prev) =>
      prev.map((p) =>
        p.id === activePageId
          ? {
              ...p,
              tiles: p.tiles.map((t) => (t.id === tileId ? { ...t, ...updates } : t)),
            }
          : p
      )
    );
  };

  const handleUpdateChartConfig = (tileId, configUpdates) => {
    pushHistory();
    setPages((prev) =>
      prev.map((p) =>
        p.id === activePageId
          ? {
              ...p,
              tiles: p.tiles.map((t) =>
                t.id === tileId
                  ? {
                      ...t,
                      chartConfig: { ...t.chartConfig, ...configUpdates },
                    }
                  : t
              ),
            }
          : p
      )
    );
  };

  // Layout change from ReactGridLayout
  const handleLayoutChange = (newLayout) => {
    setPages((prev) =>
      prev.map((p) => {
        if (p.id !== activePageId) return p;
        return {
          ...p,
          tiles: p.tiles.map((tile) => {
            const item = newLayout.find((l) => l.i === tile.id);
            if (!item) return tile;
            return {
              ...tile,
              layout: {
                ...tile.layout,
                x: item.x,
                y: item.y,
                w: item.w,
                h: item.h,
              },
            };
          }),
        };
      })
    );
  };

  const handleDragOrResizeStop = () => {
    pushHistory();
  };

  // Convert tiles into react-grid-layout layout array
  const currentGridLayout = useMemo(() => {
    return (activePage?.tiles || []).map((t) => ({
      i: t.id,
      x: t.layout?.x ?? 0,
      y: t.layout?.y ?? 0,
      w: t.layout?.w ?? 12,
      h: t.layout?.h ?? 10,
      minW: t.layout?.minW ?? 3,
      minH: t.layout?.minH ?? 2,
    }));
  }, [activePage]);

  // ── Multi-Page Landscape PDF Export ───────────────────────────────────────
  const handleDownloadReport = async () => {
    if (pages.length === 0 || isExporting) return;
    setIsExporting(true);
    setExportError(null);
    setExportProgress({ current: 0, total: pages.length });

    try {
      // Step 1: Pre-fetch all chart data across all pages so offscreen capture has 0 loading spinners
      for (let pIdx = 0; pIdx < pages.length; pIdx++) {
        const page = pages[pIdx];
        setExportProgress({ current: pIdx + 1, total: pages.length });
        for (const tile of page.tiles) {
          if (tile.kind === "chart" && tile.chartConfig) {
            try {
              await fetchTileChartData(datasetId, tile.chartConfig);
            } catch {
              // ignore pre-fetch errors, renderSharedChart fallback handles it
            }
          }
        }
      }

      // Step 2: Initialize jsPDF landscape 16:9
      const pdf = new jsPDF({
        orientation: "landscape",
        unit: "px",
        format: [CANVAS_W, CANVAS_H],
      });

      // Step 3: Capture each page sequentially off-screen
      for (let i = 0; i < pages.length; i++) {
        const page = pages[i];
        setExportProgress({ current: i + 1, total: pages.length });
        setExportStagePage(page);

        // Wait for offscreen DOM and Recharts SVG layout to settle
        await new Promise((resolve) => setTimeout(resolve, 450));

        if (!exportStageRef.current) {
          throw new Error("Export container unavailable");
        }

        const canvas = await html2canvas(exportStageRef.current, {
          scale: 2,
          useCORS: true,
          logging: false,
          backgroundColor: "#ffffff",
          windowWidth: CANVAS_W,
          windowHeight: CANVAS_H,
        });

        const imgData = canvas.toDataURL("image/png");
        if (i === 0) {
          pdf.addImage(imgData, "PNG", 0, 0, CANVAS_W, CANVAS_H, undefined, "FAST");
        } else {
          pdf.addPage([CANVAS_W, CANVAS_H], "landscape");
          pdf.addImage(imgData, "PNG", 0, 0, CANVAS_W, CANVAS_H, undefined, "FAST");
        }
      }

      // Step 4: Save file
      const rawName = datasetFilename ? datasetFilename.replace(/\.[^/.]+$/, "") : "dataset";
      pdf.save(`${rawName}_dashboard.pdf`);
    } catch (err) {
      console.error("PDF Export error:", err);
      setExportError(err.message || "Failed to generate report PDF.");
    } finally {
      setIsExporting(false);
      setExportStagePage(null);
    }
  };

  // Helper flags for chart inspector
  const activeChartConfig = selectedTile?.chartConfig;
  const isForecast = activeChartConfig?.chartType?.startsWith("forecast_");
  const isHeatmap = activeChartConfig?.chartType === "heatmap";
  const isKPI = activeChartConfig?.chartType === "kpi";
  const isMap = activeChartConfig?.chartType === "map";
  const isHist = activeChartConfig?.chartType === "histogram";
  const isBox = activeChartConfig?.chartType === "box_plot";
  const isStack =
    activeChartConfig?.chartType === "stacked_bar" ||
    activeChartConfig?.chartType === "stacked_bar_100";
  const isWaterfall = activeChartConfig?.chartType === "waterfall";

  const needsY =
    isForecast ||
    activeChartConfig?.chartType === "line" ||
    activeChartConfig?.chartType === "scatter" ||
    activeChartConfig?.chartType === "area" ||
    isWaterfall ||
    (activeChartConfig?.chartType === "bar" && activeChartConfig?.agg !== "count") ||
    (isKPI && (activeChartConfig?.agg === "sum" || activeChartConfig?.agg === "mean"));

  const needsStack = isStack;

  return (
    <div className="rpt-root">
      {/* ── Top Toolbar ── */}
      <div className="rpt-toolbar">
        <div className="rpt-toolbar-left">
          <span className="rpt-toolbar-title">
            {datasetFilename ? `📊 ${datasetFilename}` : "Report"}
          </span>
        </div>
        <div className="rpt-toolbar-actions">
          <button className="rpt-toolbar-btn" onClick={handleAddTitle} title="Add title / text box">
            + Title
          </button>
          <button
            className="rpt-toolbar-btn"
            onClick={() => handleAddChart("bar")}
            title="Add chart visual"
          >
            + Chart
          </button>
          <div className="rpt-toolbar-divider" />
          <button
            className="rpt-toolbar-btn"
            onClick={handleUndo}
            disabled={!canUndo}
            title="Undo layout or visual changes"
          >
            ↩ Undo
          </button>
          <button
            className="rpt-toolbar-btn"
            onClick={handleRedo}
            disabled={!canRedo}
            title="Redo visual changes"
          >
            ↪ Redo
          </button>
          <div className="rpt-toolbar-divider" />
          <button
            className="rpt-toolbar-btn rpt-toolbar-btn--primary"
            onClick={handleDownloadReport}
            disabled={isExporting}
            title="Export all report pages into a high-res landscape PDF"
          >
            {isExporting ? "Exporting…" : "⬇ Download report"}
          </button>
        </div>
      </div>

      {/* ── Main Area: Canvas + Inspector Sidebar ── */}
      <div className="rpt-main-area">
        {/* Canvas Area */}
        <div
          className="rpt-canvas-area"
          ref={canvasAreaRef}
          onClick={() => setSelectedTileId(null)}
        >
          <div
            className="rpt-canvas-scaler-wrapper"
            style={{
              width: CANVAS_W * canvasScale,
              height: CANVAS_H * canvasScale,
            }}
          >
            <div
              className="rpt-canvas"
              style={{
                width: CANVAS_W,
                height: CANVAS_H,
                transform: `scale(${canvasScale})`,
                transformOrigin: "top left",
              }}
              data-page-id={activePage?.id}
            >
              {/* Dot Grid */}
              <div className="rpt-canvas-dots" aria-hidden="true" />

              {/* Empty State */}
              {activePage && activePage.tiles.length === 0 && (
                <div className="rpt-canvas-empty">
                  <div className="rpt-canvas-empty-icon">📐</div>
                  <div className="rpt-canvas-empty-title">Canvas is empty</div>
                  <div className="rpt-canvas-empty-hint">
                    Click <strong>+ Title</strong> or <strong>+ Chart</strong> in the toolbar above to
                    start designing your dashboard page.
                  </div>
                </div>
              )}

              {/* React-Grid-Layout Canvas */}
              {activePage && activePage.tiles.length > 0 && (
                <ReactGridLayout
                  className="rpt-grid"
                  layout={currentGridLayout}
                  cols={GRID_COLS}
                  rowHeight={GRID_ROW_HEIGHT}
                  width={CANVAS_W}
                  margin={GRID_MARGIN}
                  containerPadding={GRID_MARGIN}
                  compactType={null}
                  preventCollision={true}
                  isBounded={true}
                  transformScale={canvasScale}
                  onLayoutChange={handleLayoutChange}
                  onDragStop={handleDragOrResizeStop}
                  onResizeStop={handleDragOrResizeStop}
                  draggableHandle=".rpt-tile-drag-handle"
                  draggableCancel=".rpt-tile-no-drag"
                  resizeHandles={["s", "w", "e", "n", "sw", "nw", "se", "ne"]}
                >
                  {activePage.tiles.map((tile) => (
                    <div
                      key={tile.id}
                      className={`rpt-tile rpt-tile--${tile.kind}${
                        selectedTileId === tile.id ? " rpt-tile--selected" : ""
                      }`}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedTileId(tile.id);
                      }}
                    >
                      {/* Header & Drag Handle */}
                      <div className="rpt-tile-header rpt-tile-drag-handle">
                        <div className="rpt-tile-title-bar">
                          <span className="rpt-tile-kind-badge">
                            {tile.kind === "chart"
                              ? tile.chartConfig?.chartType?.toUpperCase() || "CHART"
                              : "TEXT"}
                          </span>
                          {tile.kind === "chart" && (
                            <span className="rpt-tile-axis-info">
                              {tile.chartConfig?.xCol}
                              {tile.chartConfig?.yCol ? ` vs ${tile.chartConfig.yCol}` : ""}
                            </span>
                          )}
                        </div>

                        {/* Hover Action Toolbar */}
                        <div
                          className="rpt-tile-actions rpt-tile-no-drag"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            className="rpt-tile-action-btn"
                            title="Edit visual settings"
                            onClick={() => setSelectedTileId(tile.id)}
                          >
                            ✏️
                          </button>
                          <button
                            className="rpt-tile-action-btn"
                            title="Duplicate visual"
                            onClick={() => handleDuplicateTile(tile)}
                          >
                            ⧉
                          </button>
                          <button
                            className="rpt-tile-action-btn rpt-tile-action-btn--danger"
                            title="Delete visual"
                            onClick={() => handleDeleteTile(tile.id)}
                          >
                            🗑
                          </button>
                        </div>
                      </div>

                      {/* Tile Body */}
                      <div className="rpt-tile-body">
                        {tile.kind === "chart" ? (
                          <ChartTileContent tile={tile} datasetId={datasetId} />
                        ) : (
                          <TextTileContent
                            tile={tile}
                            isSelected={selectedTileId === tile.id}
                            onUpdate={(updates) => handleUpdateTile(tile.id, updates)}
                          />
                        )}
                      </div>
                    </div>
                  ))}
                </ReactGridLayout>
              )}
            </div>
          </div>
        </div>

        {/* ── Right Inspector Sidebar (Power BI Format Pane) ── */}
        {selectedTile && (
          <div className="rpt-inspector-sidebar" onClick={(e) => e.stopPropagation()}>
            <div className="rpt-inspector-header">
              <span className="rpt-inspector-title">
                {selectedTile.kind === "chart" ? "📊 Chart Settings" : "📝 Text Settings"}
              </span>
              <button
                className="rpt-inspector-close"
                onClick={() => setSelectedTileId(null)}
                title="Close settings"
              >
                ✕
              </button>
            </div>

            <div className="rpt-inspector-body">
              {/* Chart Visual Settings */}
              {selectedTile.kind === "chart" && activeChartConfig && (
                <>
                  {/* Chart Type Gallery */}
                  <div className="rpt-inspector-section">
                    <label className="rpt-inspector-label">Visual Type</label>
                    <div className="rpt-inspector-gallery-grid">
                      {CHART_GALLERY_TYPES.map((t) => (
                        <button
                          key={t.id}
                          className={`rpt-inspector-gallery-btn${
                            activeChartConfig.chartType === t.id ? " active" : ""
                          }`}
                          onClick={() => handleUpdateChartConfig(selectedTile.id, { chartType: t.id })}
                          title={t.name}
                        >
                          <span className="rpt-inspector-gallery-icon">{t.icon}</span>
                          <span className="rpt-inspector-gallery-name">{t.name}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Primary Axis / Column */}
                  {!isHeatmap && (
                    <div className="rpt-inspector-section">
                      <label className="rpt-inspector-label">
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
                        className="rpt-inspector-select"
                        value={activeChartConfig.xCol || ""}
                        onChange={(e) =>
                          handleUpdateChartConfig(selectedTile.id, { xCol: e.target.value })
                        }
                      >
                        {allCols.map((c) => (
                          <option key={c.name} value={c.name}>
                            {c.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}

                  {/* Secondary Axis / Column */}
                  {!isHeatmap && (needsY || isBox || isMap) && (
                    <div className="rpt-inspector-section">
                      <label className="rpt-inspector-label">
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
                        className="rpt-inspector-select"
                        value={activeChartConfig.yCol || ""}
                        onChange={(e) =>
                          handleUpdateChartConfig(selectedTile.id, { yCol: e.target.value })
                        }
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

                  {/* Stack Column */}
                  {needsStack && (
                    <div className="rpt-inspector-section">
                      <label className="rpt-inspector-label">Stack by</label>
                      <select
                        className="rpt-inspector-select"
                        value={activeChartConfig.stackCol || ""}
                        onChange={(e) =>
                          handleUpdateChartConfig(selectedTile.id, { stackCol: e.target.value })
                        }
                      >
                        {allCols.map((c) => (
                          <option key={c.name} value={c.name}>
                            {c.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}

                  {/* Aggregation */}
                  {!isHist && !isBox && !isStack && !isForecast && !isHeatmap && !isWaterfall && !isMap && (
                    <div className="rpt-inspector-section">
                      <label className="rpt-inspector-label">Aggregation</label>
                      <select
                        className="rpt-inspector-select"
                        value={activeChartConfig.agg || "count"}
                        onChange={(e) =>
                          handleUpdateChartConfig(selectedTile.id, { agg: e.target.value })
                        }
                        disabled={
                          activeChartConfig.chartType === "scatter" ||
                          activeChartConfig.chartType === "pie"
                        }
                      >
                        <option value="count">Count</option>
                        <option value="sum">Sum</option>
                        <option value="mean">Mean</option>
                      </select>
                    </div>
                  )}
                </>
              )}

              {/* Text Tile Settings */}
              {selectedTile.kind === "text" && (
                <>
                  <div className="rpt-inspector-section">
                    <label className="rpt-inspector-label">Content</label>
                    <textarea
                      className="rpt-inspector-input"
                      rows={3}
                      value={selectedTile.text || ""}
                      onChange={(e) =>
                        handleUpdateTile(selectedTile.id, { text: e.target.value })
                      }
                      placeholder="Enter heading or description..."
                    />
                  </div>

                  <div className="rpt-inspector-section">
                    <label className="rpt-inspector-label">Font Size</label>
                    <div className="rpt-inspector-btn-group">
                      {["title", "subtitle", "body"].map((size) => (
                        <button
                          key={size}
                          className={`rpt-inspector-btn${
                            (selectedTile.fontSize || "title") === size ? " active" : ""
                          }`}
                          onClick={() => handleUpdateTile(selectedTile.id, { fontSize: size })}
                        >
                          {size.charAt(0).toUpperCase() + size.slice(1)}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="rpt-inspector-section">
                    <label className="rpt-inspector-label">Alignment</label>
                    <div className="rpt-inspector-btn-group">
                      {[
                        { id: "left", label: "Left" },
                        { id: "center", label: "Center" },
                        { id: "right", label: "Right" },
                      ].map((align) => (
                        <button
                          key={align.id}
                          className={`rpt-inspector-btn${
                            (selectedTile.align || "left") === align.id ? " active" : ""
                          }`}
                          onClick={() => handleUpdateTile(selectedTile.id, { align: align.id })}
                        >
                          {align.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="rpt-inspector-section">
                    <label className="rpt-inspector-label">Style</label>
                    <div className="rpt-inspector-btn-group">
                      <button
                        className={`rpt-inspector-btn${selectedTile.bold ? " active" : ""}`}
                        onClick={() => handleUpdateTile(selectedTile.id, { bold: !selectedTile.bold })}
                      >
                        Bold (B)
                      </button>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ── Page Tabs (Bottom, Power BI-style) ── */}
      <div className="rpt-page-tabs-bar">
        <div className="rpt-page-tabs">
          {pages.map((page, idx) => (
            <div
              key={page.id}
              className={`rpt-page-tab${page.id === activePageId ? " active" : ""}`}
              draggable
              onDragStart={() => handleTabDragStart(idx)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => handleTabDrop(idx)}
              onClick={() => {
                setReportState((prev) => ({ ...prev, activePageId: page.id }));
                setSelectedTileId(null);
              }}
              onDoubleClick={() => handleStartRename(page)}
              title="Double-click to rename · Drag to reorder"
            >
              {renamingPageId === page.id ? (
                <input
                  className="rpt-tab-rename-input"
                  value={renameValue}
                  autoFocus
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) => setRenameValue(e.target.value)}
                  onBlur={handleCommitRename}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleCommitRename();
                    if (e.key === "Escape") setRenamingPageId(null);
                  }}
                />
              ) : (
                <span className="rpt-tab-name">{page.name}</span>
              )}

              {page.id === activePageId && (
                <div className="rpt-tab-actions" onClick={(e) => e.stopPropagation()}>
                  <button
                    className="rpt-tab-action-btn"
                    title="Duplicate page"
                    onClick={() => handleDuplicatePage(page)}
                  >
                    ⧉
                  </button>
                  {pages.length > 1 &&
                    (deleteConfirmId === page.id ? (
                      <>
                        <button
                          className="rpt-tab-action-btn rpt-tab-action-btn--danger"
                          title="Confirm delete"
                          onClick={() => handleDeletePage(page.id)}
                        >
                          ✓
                        </button>
                        <button
                          className="rpt-tab-action-btn"
                          title="Cancel"
                          onClick={() => setDeleteConfirmId(null)}
                        >
                          ✕
                        </button>
                      </>
                    ) : (
                      <button
                        className="rpt-tab-action-btn"
                        title="Delete page"
                        onClick={() => setDeleteConfirmId(page.id)}
                      >
                        🗑
                      </button>
                    ))}
                </div>
              )}
            </div>
          ))}
        </div>

        <button className="rpt-add-page-btn" onClick={handleAddPage} title="Add a new blank page">
          + Add page
        </button>
      </div>

      {/* ── Off-screen PDF Export Render Stage ── */}
      {isExporting && exportStagePage && (
        <div
          ref={exportStageRef}
          className="rpt-export-stage rpt-exporting"
          style={{ width: CANVAS_W, height: CANVAS_H }}
        >
          <div className="rpt-pdf-page-footer">{exportStagePage.name}</div>
          <ReactGridLayout
            className="rpt-grid"
            layout={exportStagePage.tiles.map((t) => ({
              i: t.id,
              x: t.layout?.x ?? 0,
              y: t.layout?.y ?? 0,
              w: t.layout?.w ?? 12,
              h: t.layout?.h ?? 10,
            }))}
            cols={GRID_COLS}
            rowHeight={GRID_ROW_HEIGHT}
            width={CANVAS_W}
            margin={GRID_MARGIN}
            containerPadding={GRID_MARGIN}
            compactType={null}
            isDraggable={false}
            isResizable={false}
          >
            {exportStagePage.tiles.map((tile) => (
              <div key={tile.id} className={`rpt-tile rpt-tile--${tile.kind}`}>
                <div className="rpt-tile-body">
                  {tile.kind === "chart" ? (
                    <ChartTileContent tile={tile} datasetId={datasetId} />
                  ) : (
                    <TextTileContent tile={tile} isSelected={false} onUpdate={() => {}} />
                  )}
                </div>
              </div>
            ))}
          </ReactGridLayout>
        </div>
      )}

      {/* ── Export Progress Modal ── */}
      {isExporting && (
        <div className="rpt-modal-backdrop">
          <div className="rpt-progress-modal">
            <div className="rpt-progress-modal-title">
              <span>📄 Generating Multi-Page PDF</span>
            </div>
            <div className="rpt-progress-modal-status">
              Exporting page {exportProgress.current} of {exportProgress.total}…
            </div>
            <div className="rpt-progress-bar-track">
              <div
                className="rpt-progress-bar-fill"
                style={{
                  width: `${
                    exportProgress.total > 0
                      ? Math.round((exportProgress.current / exportProgress.total) * 100)
                      : 0
                  }%`,
                }}
              />
            </div>
            <div style={{ fontSize: 11, color: "#a1a1aa" }}>
              Capturing 16:9 canvas pages at 2× resolution…
            </div>
          </div>
        </div>
      )}

      {/* ── Export Error Alert ── */}
      {exportError && (
        <div className="rpt-modal-backdrop" onClick={() => setExportError(null)}>
          <div className="rpt-progress-modal" onClick={(e) => e.stopPropagation()}>
            <div className="rpt-progress-modal-title" style={{ color: "#ef4444" }}>
              <span>⚠️ Export Failed</span>
            </div>
            <div className="rpt-progress-modal-status">{exportError}</div>
            <button
              className="rpt-toolbar-btn rpt-toolbar-btn--primary"
              onClick={() => setExportError(null)}
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
