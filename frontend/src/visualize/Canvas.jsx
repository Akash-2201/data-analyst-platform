/**
 * frontend/src/visualize/Canvas.jsx
 * Custom pointer-events drag and resize canvas engine for the Power BI Dashboard Builder.
 * Replaces react-grid-layout with pixel-accurate 1:1 pointer capture, snap, clamp, and multi-selection.
 */

import React, { useRef, useState, useEffect, useMemo, useCallback } from "react";
import { useDashboard } from "./dashboardContext";
import { AlignToolbar } from "./AlignToolbar";
import { exportElementAsPng, exportDataAsCsv } from "./exportService";
import { clamp, clampTilePx } from "./utils";

const RESIZE_HANDLES = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];

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
  const pageW = activePage?.size?.w || 1920;
  const pageH = activePage?.size?.h || 1080;
  const step = snap ? 20 : 1;

  // Local draft state for smooth 60fps dragging and resizing
  const [draftPositions, setDraftPositions] = useState(null); // Map of tileId -> { x, y, w, h }
  const [liveBadge, setLiveBadge] = useState(null); // { text, x, y }
  const [toastMsg, setToastMsg] = useState("");

  const showToast = useCallback((msg) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(""), 2500);
  }, []);

  // Compute transform scale to fit container width & height maintaining ratio
  const updateFitScale = useCallback(() => {
    if (!viewportRef.current || !setFitScale) return;
    const { clientWidth, clientHeight } = viewportRef.current;
    if (clientWidth <= 0 || clientHeight <= 0) return;
    const fitW = (clientWidth - 16) / pageW;
    const fitH = (clientHeight - 16) / pageH;
    const computedFit = (zoomMode === "fitPage" || zoomMode === "fit") ? Math.min(fitW, fitH) : fitW;
    const clampedFit = Math.min(2.0, Math.max(0.25, computedFit));
    setFitScale(clampedFit);
  }, [pageW, pageH, zoomMode, setFitScale]);

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
  const effectiveScale = (zoomMode === "fitWidth" || zoomMode === "fitPage" || zoomMode === "fit")
    ? (fitScale || 1)
    : (typeof zoomMode === "number" ? zoomMode : 1);

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
      const next = Math.min(2.0, Math.max(0.25, Math.round((effectiveScale + delta) * 100) / 100));
      setZoomMode(next);
    };
    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => el.removeEventListener("wheel", handleWheel);
  }, [effectiveScale, setZoomMode]);

  // Gesture tracking ref
  const gestureRef = useRef({
    active: false,
    type: null, // "drag" | "resize"
    handle: null,
    pointerId: null,
    startClientX: 0,
    startClientY: 0,
    hasMoved: false,
    startPositions: new Map(), // tileId -> { x, y, w, h }
    primaryTileId: null,
    rafId: null,
  });

  // Handle tile pointer down for dragging & selection
  const handleTilePointerDown = (e, tile) => {
    if (e.button !== 0) return; // left click only

    if (mode === "view") {
      showToast("Switch to Edit mode to move charts");
      return;
    }

    const isMulti = e.shiftKey || e.ctrlKey || e.metaKey;
    let nextSelected = [...selectedTileIds];
    if (isMulti) {
      if (nextSelected.includes(tile.id)) {
        nextSelected = nextSelected.filter((id) => id !== tile.id);
      } else {
        nextSelected.push(tile.id);
      }
    } else if (!nextSelected.includes(tile.id)) {
      nextSelected = [tile.id];
    }

    dispatch({
      type: "SELECT_TILE",
      payload: { tileId: tile.id, multi: isMulti },
    });

    // Collect all moving tiles (selected + sharing same groupId)
    const movingSet = new Set(nextSelected);
    const selectedTiles = tiles.filter((t) => nextSelected.includes(t.id));
    selectedTiles.forEach((st) => {
      if (st.groupId) {
        tiles.forEach((t) => {
          if (t.groupId === st.groupId) movingSet.add(t.id);
        });
      }
    });

    const startMap = new Map();
    tiles.forEach((t) => {
      if (movingSet.has(t.id)) {
        startMap.set(t.id, { x: t.x, y: t.y, w: t.w, h: t.h });
      }
    });

    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {}

    gestureRef.current = {
      active: true,
      type: "drag",
      handle: null,
      pointerId: e.pointerId,
      startClientX: e.clientX,
      startClientY: e.clientY,
      hasMoved: false,
      startPositions: startMap,
      primaryTileId: tile.id,
      rafId: null,
    };
  };

  const handleTilePointerMove = (e) => {
    const g = gestureRef.current;
    if (!g.active || g.type !== "drag") return;

    const rawDx = (e.clientX - g.startClientX) / effectiveScale;
    const rawDy = (e.clientY - g.startClientY) / effectiveScale;

    if (!g.hasMoved) {
      if (Math.hypot(rawDx, rawDy) < 3) return;
      g.hasMoved = true;
    }

    const snappedDx = Math.round(rawDx / step) * step;
    const snappedDy = Math.round(rawDy / step) * step;

    const nextDraft = new Map();
    let primaryPos = null;

    g.startPositions.forEach((start, tileId) => {
      const newX = clamp(start.x + snappedDx, 0, Math.max(0, pageW - start.w));
      const newY = clamp(start.y + snappedDy, 0, Math.max(0, pageH - start.h));
      nextDraft.set(tileId, { x: newX, y: newY, w: start.w, h: start.h });
      if (tileId === g.primaryTileId) {
        primaryPos = { x: newX, y: newY, w: start.w, h: start.h };
      }
    });

    // Auto-grow height check
    if (activePage?.autoGrowHeight && primaryPos) {
      if (primaryPos.y + primaryPos.h >= pageH - 40) {
        dispatch({
          type: "GROW_PAGE_HEIGHT",
          payload: { pageId: activePage.id, addH: 120 },
        });
      }
    }

    if (primaryPos) {
      setLiveBadge({
        text: `X: ${Math.round(primaryPos.x)}, Y: ${Math.round(primaryPos.y)}`,
        x: e.clientX,
        y: e.clientY - 28,
      });
    }

    if (g.rafId) cancelAnimationFrame(g.rafId);
    g.rafId = requestAnimationFrame(() => {
      setDraftPositions(nextDraft);
    });
  };

  const handleTilePointerUp = (e) => {
    const g = gestureRef.current;
    if (!g.active || g.type !== "drag") return;

    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {}

    if (g.hasMoved && draftPositions) {
      const updates = [];
      draftPositions.forEach((pos, tileId) => {
        updates.push({ tileId, ...pos });
      });
      if (updates.length > 0) {
        dispatch({
          type: "UPDATE_TILES_LAYOUT",
          payload: updates,
        });
      }
    }

    if (g.rafId) cancelAnimationFrame(g.rafId);
    gestureRef.current.active = false;
    setDraftPositions(null);
    setLiveBadge(null);
  };

  // Handle Resize pointer down
  const handleResizePointerDown = (e, tile, handle) => {
    e.stopPropagation();
    if (e.button !== 0 || mode !== "edit") return;

    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {}

    const startMap = new Map();
    startMap.set(tile.id, { x: tile.x, y: tile.y, w: tile.w, h: tile.h });

    gestureRef.current = {
      active: true,
      type: "resize",
      handle,
      pointerId: e.pointerId,
      startClientX: e.clientX,
      startClientY: e.clientY,
      hasMoved: false,
      startPositions: startMap,
      primaryTileId: tile.id,
      rafId: null,
    };
  };

  const handleResizePointerMove = (e) => {
    const g = gestureRef.current;
    if (!g.active || g.type !== "resize") return;

    const rawDx = (e.clientX - g.startClientX) / effectiveScale;
    const rawDy = (e.clientY - g.startClientY) / effectiveScale;

    if (!g.hasMoved) {
      if (Math.hypot(rawDx, rawDy) < 2) return;
      g.hasMoved = true;
    }

    const snappedDx = Math.round(rawDx / step) * step;
    const snappedDy = Math.round(rawDy / step) * step;

    const start = g.startPositions.get(g.primaryTileId);
    if (!start) return;

    let newX = start.x;
    let newY = start.y;
    let newW = start.w;
    let newH = start.h;

    const handle = g.handle;

    // Horizontal adjustments
    if (handle.includes("e")) {
      newW = clamp(start.w + snappedDx, 120, Math.max(120, pageW - start.x));
    } else if (handle.includes("w")) {
      const maxW = start.x + start.w;
      newW = clamp(start.w - snappedDx, 120, maxW);
      newX = start.x + (start.w - newW);
    }

    // Vertical adjustments
    if (handle.includes("s")) {
      newH = clamp(start.h + snappedDy, 80, Math.max(80, pageH - start.y));
    } else if (handle.includes("n")) {
      const maxH = start.y + start.h;
      newH = clamp(start.h - snappedDy, 80, maxH);
      newY = start.y + (start.h - newH);
    }

    // Auto-grow height check on resize
    if (activePage?.autoGrowHeight && handle.includes("s")) {
      if (newY + newH >= pageH - 40) {
        dispatch({
          type: "GROW_PAGE_HEIGHT",
          payload: { pageId: activePage.id, addH: 120 },
        });
      }
    }

    const nextDraft = new Map();
    nextDraft.set(g.primaryTileId, { x: newX, y: newY, w: newW, h: newH });

    setLiveBadge({
      text: `${Math.round(newW)} × ${Math.round(newH)}`,
      x: e.clientX,
      y: e.clientY - 28,
    });

    if (g.rafId) cancelAnimationFrame(g.rafId);
    g.rafId = requestAnimationFrame(() => {
      setDraftPositions(nextDraft);
    });
  };

  const handleResizePointerUp = (e) => {
    const g = gestureRef.current;
    if (!g.active || g.type !== "resize") return;

    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {}

    if (g.hasMoved && draftPositions) {
      const pos = draftPositions.get(g.primaryTileId);
      if (pos) {
        dispatch({
          type: "UPDATE_TILES_LAYOUT",
          payload: [{ tileId: g.primaryTileId, ...pos }],
        });
      }
    }

    if (g.rafId) cancelAnimationFrame(g.rafId);
    gestureRef.current.active = false;
    setDraftPositions(null);
    setLiveBadge(null);
  };

  // Keyboard navigation: arrow nudge & delete
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (mode !== "edit" || selectedTileIds.length === 0) return;

      // Ignore when typing inside input / textarea / select
      const tag = document.activeElement?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select") return;

      const nudgeStep = e.shiftKey ? step * 10 : step;

      let dx = 0;
      let dy = 0;

      if (e.key === "ArrowLeft") dx = -nudgeStep;
      else if (e.key === "ArrowRight") dx = nudgeStep;
      else if (e.key === "ArrowUp") dy = -nudgeStep;
      else if (e.key === "ArrowDown") dy = nudgeStep;
      else if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        dispatch({ type: "DELETE_TILES", payload: { tileIds: selectedTileIds } });
        return;
      } else {
        return;
      }

      e.preventDefault();

      const updates = [];
      tiles.forEach((t) => {
        if (selectedTileIds.includes(t.id)) {
          const clamped = clampTilePx(t.x + dx, t.y + dy, t.w, t.h, pageW, pageH);
          updates.push({ tileId: t.id, ...clamped });
        }
      });

      if (updates.length > 0) {
        dispatch({ type: "UPDATE_TILES_LAYOUT", payload: updates });
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [mode, selectedTileIds, tiles, step, pageW, pageH, dispatch]);

  const handleCanvasClick = (e) => {
    if (mode !== "edit") return;
    const target = e.target;
    if (
      target === e.currentTarget ||
      target.classList?.contains("rpt-canvas-viewport") ||
      target.classList?.contains("rpt-canvas-outer") ||
      target.classList?.contains("rpt-canvas-wrapper")
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
      {/* Floating Live Measurement Badge while dragging/resizing */}
      {liveBadge && (
        <div
          className="rpt-live-badge"
          style={{ left: liveBadge.x, top: liveBadge.y }}
        >
          {liveBadge.text}
        </div>
      )}

      {/* Floating Guidance Toast */}
      {toastMsg && (
        <div
          className="rpt-toast"
          style={{ position: "fixed", bottom: 36, left: "50%", transform: "translateX(-50%)", zIndex: 9999 }}
        >
          {toastMsg}
        </div>
      )}

      {/* Scaled Layout Container */}
      <div
        className="rpt-canvas-outer"
        style={{
          width: Math.round(pageW * effectiveScale),
          height: Math.round(pageH * effectiveScale),
          margin: "auto",
          position: "relative",
          flexShrink: 0,
        }}
      >
        {/* Logical Inner Canvas */}
        <div
          ref={canvasRef}
          className={`rpt-canvas-wrapper ${showGrid && mode === "edit" ? "grid-dots" : ""}`}
          style={{
            width: pageW,
            height: pageH,
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

          {/* Render Tiles */}
          {tiles.map((tile) => {
            const isSelected = selectedTileIds.includes(tile.id);
            const draft = draftPositions?.get(tile.id);
            const posX = draft ? draft.x : tile.x;
            const posY = draft ? draft.y : tile.y;
            const posW = draft ? draft.w : tile.w;
            const posH = draft ? draft.h : tile.h;

            return (
              <div
                key={tile.id}
                id={`tile-${tile.id}`}
                className={`rpt-tile ${isSelected ? "selected" : ""} ${mode === "edit" ? "edit-mode" : "view-mode"}`}
                style={{
                  position: "absolute",
                  left: posX,
                  top: posY,
                  width: posW,
                  height: posH,
                  backgroundColor: tile.format?.bg || "var(--rpt-tile-bg, #18181b)",
                  border: isSelected
                    ? "2px solid var(--rpt-accent, #8b5cf6)"
                    : tile.format?.border
                    ? `1px solid ${tile.format.borderColor || "var(--rpt-border, #27272a)"}`
                    : "1px solid transparent",
                  borderRadius: tile.format?.radius ?? 8,
                  zIndex: tile.z || 1,
                  boxSizing: "border-box",
                }}
                onPointerDown={(e) => handleTilePointerDown(e, tile)}
                onPointerMove={handleTilePointerMove}
                onPointerUp={handleTilePointerUp}
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
                        color: "var(--rpt-text, #f4f4f5)",
                      }}
                    >
                      {tile.title}
                    </span>
                  </div>
                )}

                {/* Hover Mini Toolbar (in edit mode) */}
                {mode === "edit" && (
                  <div
                    className="rpt-tile-hover-bar"
                    onPointerDown={(e) => e.stopPropagation()}
                  >
                    <button
                      type="button"
                      className="rpt-hover-icon-btn"
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
                      className="rpt-hover-icon-btn"
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
                      className="rpt-hover-icon-btn"
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
                      className="rpt-hover-icon-btn"
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
                      className="rpt-hover-icon-btn"
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
                      className="rpt-hover-icon-btn"
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
                      className="rpt-hover-icon-btn danger"
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

                {/* Tile Body: in edit mode pointer-events is disabled on body so wrapper captures all drag gestures */}
                <div
                  className="rpt-tile-body"
                  style={{
                    pointerEvents: mode === "edit" ? "none" : "auto",
                    width: "100%",
                    height: "100%",
                    overflow: "hidden",
                  }}
                >
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

                {/* 8 Resize Handles (rendered when tile is selected in Edit mode) */}
                {isSelected && mode === "edit" && (
                  <>
                    {RESIZE_HANDLES.map((handle) => (
                      <div
                        key={handle}
                        className={`rpt-resize-handle handle-${handle}`}
                        onPointerDown={(e) => handleResizePointerDown(e, tile, handle)}
                        onPointerMove={handleResizePointerMove}
                        onPointerUp={handleResizePointerUp}
                      />
                    ))}
                  </>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
