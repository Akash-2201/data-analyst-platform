/**
 * frontend/src/visualize/Canvas.jsx
 * 1280x720 logical canvas with CSS transform scaling and ReactGridLayout.
 */

import React, { useRef, useState, useEffect, useMemo, useCallback } from "react";
import ReactGridLayout from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import { useDashboard } from "./dashboardContext";
import { CANVAS_W, CANVAS_H } from "./constants";
import {
  getGridCell,
  tileToRglLayout,
  rglLayoutToTilePx,
} from "./utils";
import { AlignToolbar } from "./AlignToolbar";
import { exportElementAsPng, exportDataAsCsv } from "./exportService";

export function Canvas({
  datasetId,
  columns = [],
  renderTileContent,
  canvasRef,
}) {
  const { state, dispatch, zoom } = useDashboard();
  const { present } = state;
  const { activePageId, pages, mode, settings, selectedTileIds } = present;
  const { snap, showGrid } = settings;
  const { zoomMode, setZoomMode, scale, setScale, fitScale, setFitScale } = zoom || {};

  const viewportRef = useRef(null);

  const activePage = useMemo(() => {
    return pages.find((p) => p.id === activePageId) || pages[0];
  }, [pages, activePageId]);

  const tiles = activePage?.tiles || [];

  // Compute transform scale to fit container width & height maintaining 16:9
  const updateFitScale = useCallback(() => {
    if (!viewportRef.current || !setFitScale) return;
    const { clientWidth, clientHeight } = viewportRef.current;
    if (clientWidth <= 0 || clientHeight <= 0) return;
    const fitW = (clientWidth - 48) / CANVAS_W;
    const fitH = (clientHeight - 48) / CANVAS_H;
    const computedFit = Math.min(fitW, fitH);
    const clampedFit = Math.min(2.0, Math.max(0.3, computedFit));
    setFitScale(clampedFit);
  }, [setFitScale]);

  useEffect(() => {
    updateFitScale();
    const handleResize = () => updateFitScale();
    window.addEventListener("resize", handleResize);
    let ro;
    if (viewportRef.current && window.ResizeObserver) {
      ro = new ResizeObserver(updateFitScale);
      ro.observe(viewportRef.current);
    }
    return () => {
      window.removeEventListener("resize", handleResize);
      if (ro) ro.disconnect();
    };
  }, [updateFitScale]);

  // Derived effective scale
  const effectiveScale = zoomMode === "fit" ? (fitScale || 1) : (typeof zoomMode === "number" ? zoomMode : 1);

  useEffect(() => {
    if (setScale && effectiveScale) {
      setScale(effectiveScale);
    }
  }, [effectiveScale, setScale]);

  // Ctrl + mousewheel zoom
  useEffect(() => {
    const el = viewportRef.current;
    if (!el || !setZoomMode) return;
    const handleWheel = (e) => {
      if (!e.ctrlKey) return;
      e.preventDefault();
      const delta = e.deltaY < 0 ? 0.08 : -0.08;
      const next = Math.min(2.0, Math.max(0.3, Math.round((effectiveScale + delta) * 100) / 100));
      setZoomMode(next);
    };
    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => el.removeEventListener("wheel", handleWheel);
  }, [effectiveScale, setZoomMode]);

  // Grid columns and cell size based on snap setting
  const cell = getGridCell(snap);
  const cols = Math.round(CANVAS_W / cell);

  // Generate RGL layout items
  const rglLayout = useMemo(() => {
    return tiles.map((t) => tileToRglLayout(t, snap));
  }, [tiles, snap]);

  // Handle Drag / Resize Stop -> dispatch layout update (only one history record per gesture!)
  const handleDragOrResizeStop = (newLayout, oldItem, newItem) => {
    if (!newItem) return;
    const px = rglLayoutToTilePx(newItem, snap);
    dispatch({
      type: "UPDATE_TILE_LAYOUT",
      payload: {
        tileId: newItem.i,
        x: px.x,
        y: px.y,
        w: px.w,
        h: px.h,
      },
    });
  };

  const handleTilePointerDown = (e, tileId) => {
    e.stopPropagation();
    if (mode === "edit") {
      dispatch({
        type: "SELECT_TILE",
        payload: { tileId, multi: e.shiftKey || e.ctrlKey || e.metaKey },
      });
    }
  };

  const handleCanvasClick = (e) => {
    if (mode !== "edit") return;
    const target = e.target;
    if (
      target === e.currentTarget ||
      target.classList?.contains("rpt-canvas-viewport") ||
      target.classList?.contains("rpt-canvas-outer") ||
      target.classList?.contains("rpt-canvas-wrapper") ||
      target.classList?.contains("react-grid-layout")
    ) {
      dispatch({ type: "CLEAR_SELECTION" });
    }
  };

  return (
    <div
      ref={viewportRef}
      className="rpt-canvas-viewport"
      onClick={handleCanvasClick}
    >
      <div
        className="rpt-canvas-outer"
        style={{
          width: Math.round(CANVAS_W * effectiveScale),
          height: Math.round(CANVAS_H * effectiveScale),
          margin: "auto",
          position: "relative",
          flexShrink: 0,
        }}
      >
        <div
          ref={canvasRef}
          className={`rpt-canvas-wrapper ${showGrid && mode === "edit" ? "grid-dots" : ""}`}
          style={{
            width: CANVAS_W,
            height: CANVAS_H,
            transform: `scale(${effectiveScale})`,
            transformOrigin: "top left",
            position: "absolute",
            top: 0,
            left: 0,
          }}
        >
          <AlignToolbar />

        {/* Active Cross Filter Indicator */}
        {activePage?.crossFilter && (
          <div
            className="rpt-cross-filter-badge rpt-no-drag"
            style={{
              position: "absolute",
              top: 10,
              left: 10,
              zIndex: 90,
              background: "rgba(139, 92, 246, 0.9)",
              color: "#ffffff",
              padding: "4px 10px",
              borderRadius: 20,
              fontSize: 11,
              fontWeight: 600,
              display: "flex",
              alignItems: "center",
              gap: 8,
              boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
            }}
          >
            <span>⚡ Filtered by {activePage.crossFilter.col}: {activePage.crossFilter.value}</span>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                dispatch({ type: "CLEAR_CROSS_FILTER" });
              }}
              style={{
                background: "rgba(255,255,255,0.2)",
                border: "none",
                color: "#ffffff",
                borderRadius: "50%",
                width: 16,
                height: 16,
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: "pointer",
                fontSize: 10,
                lineHeight: 1,
              }}
              title="Clear cross-filter"
            >
              ✕
            </button>
          </div>
        )}

        <ReactGridLayout
          className="layout"
          layout={rglLayout}
          cols={cols}
          rowHeight={cell}
          width={CANVAS_W}
          margin={[0, 0]}
          containerPadding={[0, 0]}
          compactType={null}
          allowOverlap={true}
          preventCollision={false}
          isBounded={false}
          isDraggable={mode === "edit"}
          isResizable={mode === "edit"}
          transformScale={effectiveScale}
          draggableCancel=".rpt-no-drag, .rpt-tile-hover-bar, button, input, select, textarea"
          resizeHandles={["se", "sw", "ne", "nw", "e", "w", "n", "s"]}
          onDragStop={handleDragOrResizeStop}
          onResizeStop={handleDragOrResizeStop}
        >
          {tiles.map((tile) => {
            const isSelected = selectedTileIds.includes(tile.id);
            return (
              <div
                key={tile.id}
                id={`tile-${tile.id}`}
                className={`rpt-tile ${isSelected ? "selected" : ""}`}
                style={{
                  backgroundColor: tile.format?.bg || "#18181b",
                  border: tile.format?.border ? `1px solid ${tile.format.borderColor || "#27272a"}` : "none",
                  borderRadius: tile.format?.radius ?? 8,
                  zIndex: tile.z || 1,
                }}
                onPointerDownCapture={(e) => handleTilePointerDown(e, tile.id)}
                onMouseDownCapture={(e) => handleTilePointerDown(e, tile.id)}
                onClick={(e) => e.stopPropagation()}
              >
                {/* Tile Header */}
                {tile.format?.showTitle !== false && (
                  <div className="rpt-tile-header">
                    <span
                      className="rpt-tile-title"
                      style={{
                        textAlign: tile.format?.titleAlign || "left",
                        fontSize: tile.format?.fontSize || 13,
                      }}
                    >
                      {tile.title}
                    </span>
                  </div>
                )}

                {/* Hover Mini Toolbar (in edit mode) */}
                {mode === "edit" && (
                  <div className="rpt-tile-hover-bar rpt-no-drag">
                    <button
                      type="button"
                      className="rpt-hover-icon-btn rpt-no-drag"
                      title="Copy (Ctrl+C)"
                      onClick={(e) => {
                        e.stopPropagation();
                        dispatch({ type: "COPY_TILES", payload: { tileIds: [tile.id] } });
                      }}
                    >
                      📄
                    </button>
                    <button
                      type="button"
                      className="rpt-hover-icon-btn rpt-no-drag"
                      title="Duplicate (Ctrl+D)"
                      onClick={(e) => {
                        e.stopPropagation();
                        dispatch({ type: "DUPLICATE_TILES", payload: { tileIds: [tile.id] } });
                      }}
                    >
                      📋
                    </button>
                    <button
                      type="button"
                      className="rpt-hover-icon-btn rpt-no-drag"
                      title="Export Visual as PNG"
                      onClick={async (e) => {
                        e.stopPropagation();
                        const tileEl = document.getElementById(`tile-${tile.id}`);
                        if (tileEl) {
                          await exportElementAsPng(tileEl, `${tile.title || "visual"}`);
                        }
                      }}
                    >
                      🖼️
                    </button>
                    <button
                      type="button"
                      className="rpt-hover-icon-btn rpt-no-drag"
                      title="Export Visual Data as CSV"
                      onClick={(e) => {
                        e.stopPropagation();
                        exportDataAsCsv(`${tile.title || "visual"}_data.csv`, [
                          { [tile.chartConfig?.xCol || "Category"]: "Sample A", [tile.chartConfig?.yCol || "Value"]: 100 },
                          { [tile.chartConfig?.xCol || "Category"]: "Sample B", [tile.chartConfig?.yCol || "Value"]: 250 },
                        ]);
                      }}
                    >
                      📊
                    </button>
                    <button
                      type="button"
                      className="rpt-hover-icon-btn rpt-no-drag"
                      title="Bring to Front"
                      onClick={(e) => {
                        e.stopPropagation();
                        dispatch({ type: "BRING_TO_FRONT", payload: { tileId: tile.id } });
                      }}
                    >
                      ▲
                    </button>
                    <button
                      type="button"
                      className="rpt-hover-icon-btn rpt-no-drag"
                      title="Send to Back"
                      onClick={(e) => {
                        e.stopPropagation();
                        dispatch({ type: "SEND_TO_BACK", payload: { tileId: tile.id } });
                      }}
                    >
                      ▼
                    </button>
                    <button
                      type="button"
                      className="rpt-hover-icon-btn danger rpt-no-drag"
                      title="Delete (Del)"
                      onClick={(e) => {
                        e.stopPropagation();
                        dispatch({ type: "DELETE_TILES", payload: { tileIds: [tile.id] } });
                      }}
                    >
                      ✕
                    </button>
                  </div>
                )}

                {/* Tile Body */}
                <div className="rpt-tile-body">
                  {/* Transparent overlay in Edit mode so Recharts cannot swallow mouse events */}
                  {mode === "edit" && <div className="rpt-drag-overlay" />}

                  {/* Render content: charts, tables, KPIs, slicers, or text */}
                  {renderTileContent ? (
                    renderTileContent(tile, {
                      crossFilter: activePage?.crossFilter,
                      isInteractive: mode === "view",
                      onPointClick: (pt) => {
                        if (tile.interaction === "none") return;
                        if (activePage?.crossFilter?.value === pt.label) {
                          dispatch({ type: "CLEAR_CROSS_FILTER" });
                        } else {
                          dispatch({
                            type: "SET_CROSS_FILTER",
                            payload: {
                              col: tile.chartConfig?.xCol,
                              value: pt.label,
                              sourceTileId: tile.id,
                            },
                          });
                        }
                      },
                    })
                  ) : (
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#71717a", fontSize: 12 }}>
                      {tile.kind} tile ({tile.w}x{tile.h})
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </ReactGridLayout>
      </div>
    </div>
  </div>
);
}
