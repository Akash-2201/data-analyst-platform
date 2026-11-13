/**
 * VisualizeTab.jsx — Phase 1
 *
 * Power BI-style multi-page report builder.
 * Phase 1 delivers: report state model, page tabs (add / rename / duplicate / delete / reorder).
 * Each page shows an empty 16:9 canvas (1280×720 logical px).
 *
 * Report state is owned by App.jsx and passed in as props so it survives tab switches.
 * This component does NOT own the state — it only receives and mutates it via callbacks.
 *
 * Dependency: react-grid-layout@1.5.4 (installed; used in Phase 2).
 */

import { useRef, useState } from "react";
import "react-grid-layout/css/styles.css";
import "./VisualizeTab.css";

// ---------------------------------------------------------------------------
// Canvas constants (16:9 at 1280×720 logical px)
// ---------------------------------------------------------------------------
export const CANVAS_W = 1280;
export const CANVAS_H = 720;

// ---------------------------------------------------------------------------
// State factory helpers (exported so App.jsx can call them on reset)
// ---------------------------------------------------------------------------
export function makePageId() {
  return `pg-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
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
// VisualizeTab — main component
// Props:
//   reportState   : { activePageId, pages }  — owned by App.jsx
//   setReportState: state setter from App.jsx
//   datasetId     : string
//   columns       : array of column descriptors
//   datasetFilename: string
// ---------------------------------------------------------------------------
export default function VisualizeTab({
  reportState,
  setReportState,
  datasetId,
  columns,
  datasetFilename,
}) {
  // ---- Page drag-to-reorder local state ----
  const dragTabIdx = useRef(null);
  const [renamingPageId, setRenamingPageId] = useState(null);
  const [renameValue, setRenameValue] = useState("");
  const [deleteConfirmId, setDeleteConfirmId] = useState(null);

  // Derived
  const { activePageId, pages } = reportState;
  const activePage = pages.find((p) => p.id === activePageId) ?? pages[0];

  // ── Mutators ──────────────────────────────────────────────────────────────

  const setPages = (updater) => {
    setReportState((prev) => ({
      ...prev,
      pages: typeof updater === "function" ? updater(prev.pages) : updater,
    }));
  };

  const setActivePageId = (id) => {
    setReportState((prev) => ({ ...prev, activePageId: id }));
  };

  // Add a new blank page
  const handleAddPage = () => {
    const newPage = makeEmptyPage(`Page ${pages.length + 1}`);
    setReportState((prev) => ({
      ...prev,
      pages: [...prev.pages, newPage],
      activePageId: newPage.id,
    }));
  };

  // Rename page — start
  const handleStartRename = (page) => {
    setRenamingPageId(page.id);
    setRenameValue(page.name);
  };

  // Rename page — commit
  const handleCommitRename = () => {
    if (!renamingPageId) return;
    const trimmed = renameValue.trim();
    if (trimmed) {
      setPages((prev) =>
        prev.map((p) => (p.id === renamingPageId ? { ...p, name: trimmed } : p))
      );
    }
    setRenamingPageId(null);
  };

  // Duplicate page
  const handleDuplicatePage = (page) => {
    const copy = {
      ...page,
      id: makePageId(),
      name: `${page.name} (copy)`,
      tiles: page.tiles.map((t) => ({ ...t, id: `tile-${Date.now()}-${Math.random().toString(36).slice(2, 5)}` })),
    };
    setReportState((prev) => {
      const idx = prev.pages.findIndex((p) => p.id === page.id);
      const newPages = [...prev.pages];
      newPages.splice(idx + 1, 0, copy);
      return { ...prev, pages: newPages, activePageId: copy.id };
    });
  };

  // Delete page (with confirmation)
  const handleDeletePage = (pageId) => {
    if (pages.length === 1) return; // can't delete last page
    setReportState((prev) => {
      const idx = prev.pages.findIndex((p) => p.id === pageId);
      const newPages = prev.pages.filter((p) => p.id !== pageId);
      const newActive =
        prev.activePageId === pageId
          ? (newPages[Math.max(0, idx - 1)]?.id ?? newPages[0]?.id)
          : prev.activePageId;
      return { pages: newPages, activePageId: newActive };
    });
    setDeleteConfirmId(null);
  };

  // Drag-to-reorder tabs
  const handleTabDragStart = (idx) => {
    dragTabIdx.current = idx;
  };

  const handleTabDrop = (targetIdx) => {
    const fromIdx = dragTabIdx.current;
    if (fromIdx === null || fromIdx === targetIdx) return;
    setPages((prev) => {
      const arr = [...prev];
      const [moved] = arr.splice(fromIdx, 1);
      arr.splice(targetIdx, 0, moved);
      return arr;
    });
    dragTabIdx.current = null;
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="rpt-root">
      {/* ── Top toolbar ── */}
      <div className="rpt-toolbar">
        <div className="rpt-toolbar-left">
          <span className="rpt-toolbar-title">
            {datasetFilename ? `📊 ${datasetFilename}` : "Report"}
          </span>
        </div>
        <div className="rpt-toolbar-actions">
          {/* Phase 2: + Title / + Chart buttons */}
          <button className="rpt-toolbar-btn" disabled title="Coming in Phase 2">
            + Title
          </button>
          <button className="rpt-toolbar-btn" disabled title="Coming in Phase 2">
            + Chart
          </button>
          <div className="rpt-toolbar-divider" />
          {/* Phase 3: Undo / Redo */}
          <button className="rpt-toolbar-btn" disabled title="Coming in Phase 3">
            ↩ Undo
          </button>
          <button className="rpt-toolbar-btn" disabled title="Coming in Phase 3">
            ↪ Redo
          </button>
          <div className="rpt-toolbar-divider" />
          {/* Phase 4: Download report */}
          <button className="rpt-toolbar-btn rpt-toolbar-btn--primary" disabled title="Coming in Phase 4">
            ⬇ Download report
          </button>
        </div>
      </div>

      {/* ── Canvas area ── */}
      <div className="rpt-canvas-area">
        <div className="rpt-canvas-scaler-wrapper">
          <div
            className="rpt-canvas"
            style={{ width: CANVAS_W, height: CANVAS_H }}
            data-page-id={activePage?.id}
          >
            {/* Grid dots (edit mode indicator) */}
            <div className="rpt-canvas-dots" aria-hidden="true" />

            {/* Empty state */}
            {activePage && activePage.tiles.length === 0 && (
              <div className="rpt-canvas-empty">
                <div className="rpt-canvas-empty-icon">📐</div>
                <div className="rpt-canvas-empty-title">Canvas is empty</div>
                <div className="rpt-canvas-empty-hint">
                  Use <strong>+ Title</strong> or <strong>+ Chart</strong> in the toolbar above to add content to this page.
                  <br />
                  <span style={{ opacity: 0.6 }}>(Available in Phase 2)</span>
                </div>
              </div>
            )}

            {/* Phase 2: tiles rendered here via react-grid-layout */}
          </div>
        </div>
      </div>

      {/* ── Page tabs (bottom, Power BI-style) ── */}
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
              onClick={() => setActivePageId(page.id)}
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

              {/* Per-tab actions (visible on hover / active) */}
              {page.id === activePageId && (
                <div className="rpt-tab-actions" onClick={(e) => e.stopPropagation()}>
                  <button
                    className="rpt-tab-action-btn"
                    title="Duplicate page"
                    onClick={() => handleDuplicatePage(page)}
                  >
                    ⧉
                  </button>
                  {pages.length > 1 && (
                    deleteConfirmId === page.id ? (
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
                    )
                  )}
                </div>
              )}
            </div>
          ))}
        </div>

        <button className="rpt-add-page-btn" onClick={handleAddPage} title="Add a new blank page">
          + Add page
        </button>
      </div>
    </div>
  );
}

