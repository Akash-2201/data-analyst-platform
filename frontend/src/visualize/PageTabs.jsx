/**
 * frontend/src/visualize/PageTabs.jsx
 * Bottom page tab bar: Add, Rename (double-click), Duplicate, Delete,
 * Hide/Show toggle, and Reorder.
 */

import React, { useState } from "react";
import { useDashboard } from "./dashboardContext";

export function PageTabs() {
  const { state, dispatch } = useDashboard();
  const { present } = state;
  const { pages, activePageId, mode } = present;

  const [editingPageId, setEditingPageId] = useState(null);
  const [renameText, setRenameText] = useState("");
  const [draggedIdx, setDraggedIdx] = useState(null);

  // In view mode, filter out hidden pages
  const visiblePages = mode === "view" ? pages.filter((p) => !p.hidden) : pages;

  const handleStartRename = (page, e) => {
    e.stopPropagation();
    if (mode === "view") return;
    setEditingPageId(page.id);
    setRenameText(page.name);
  };

  const handleFinishRename = (pageId) => {
    setEditingPageId(null);
    if (renameText.trim()) {
      dispatch({
        type: "RENAME_PAGE",
        payload: { id: pageId, name: renameText.trim() },
      });
    }
  };

  const handleDeletePage = (pageId, pageName, e) => {
    e.stopPropagation();
    if (pages.length <= 1) {
      alert("Dashboard must have at least one page.");
      return;
    }
    const confirmed = window.confirm(`Delete page "${pageName}"? This cannot be undone.`);
    if (confirmed) {
      dispatch({ type: "DELETE_PAGE", payload: { pageId } });
    }
  };

  const handleDuplicatePage = (pageId, e) => {
    e.stopPropagation();
    dispatch({ type: "DUPLICATE_PAGE", payload: { pageId } });
  };

  const handleToggleHide = (pageId, e) => {
    e.stopPropagation();
    dispatch({ type: "TOGGLE_HIDE_PAGE", payload: { pageId } });
  };

  // Drag to reorder
  const handleDragStart = (idx, e) => {
    if (mode === "view") return;
    setDraggedIdx(idx);
    e.dataTransfer.effectAllowed = "move";
  };

  const handleDragOver = (idx, e) => {
    e.preventDefault();
    if (draggedIdx === null || draggedIdx === idx) return;
    dispatch({
      type: "REORDER_PAGES",
      payload: { sourceIndex: draggedIdx, destIndex: idx },
    });
    setDraggedIdx(idx);
  };

  return (
    <footer className="rpt-page-tabs">
      {visiblePages.map((page, idx) => {
        const isActive = page.id === activePageId;
        const isEditing = editingPageId === page.id;

        return (
          <div
            key={page.id}
            className={`rpt-page-tab ${isActive ? "active" : ""} ${page.hidden ? "hidden-page" : ""}`}
            onClick={() => dispatch({ type: "SET_ACTIVE_PAGE", payload: page.id })}
            onDoubleClick={(e) => handleStartRename(page, e)}
            draggable={mode === "edit"}
            onDragStart={(e) => handleDragStart(idx, e)}
            onDragOver={(e) => handleDragOver(idx, e)}
            title={mode === "edit" ? "Double-click to rename, drag to reorder" : page.name}
          >
            {isEditing ? (
              <input
                type="text"
                value={renameText}
                onChange={(e) => setRenameText(e.target.value)}
                onBlur={() => handleFinishRename(page.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleFinishRename(page.id);
                  if (e.key === "Escape") setEditingPageId(null);
                }}
                autoFocus
                style={{
                  background: "#18181b",
                  border: "1px solid #8b5cf6",
                  color: "#f4f4f5",
                  fontSize: 12,
                  padding: "1px 4px",
                  borderRadius: 3,
                  outline: "none",
                }}
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              <span>{page.name}</span>
            )}

            {/* Actions visible only in Edit mode */}
            {mode === "edit" && (
              <div style={{ display: "inline-flex", alignItems: "center", gap: 2, marginLeft: 4 }}>
                {/* Hide / Unhide button */}
                <button
                  type="button"
                  className="rpt-tab-action-btn"
                  onClick={(e) => handleToggleHide(page.id, e)}
                  title={page.hidden ? "Page is hidden (click to unhide)" : "Hide page from view mode"}
                >
                  {page.hidden ? "👁️‍🗨️" : "👁️"}
                </button>

                {/* Duplicate button */}
                <button
                  type="button"
                  className="rpt-tab-action-btn"
                  onClick={(e) => handleDuplicatePage(page.id, e)}
                  title="Duplicate page"
                >
                  📋
                </button>

                {/* Delete button (if more than 1 page) */}
                {pages.length > 1 && (
                  <button
                    type="button"
                    className="rpt-tab-action-btn"
                    onClick={(e) => handleDeletePage(page.id, page.name, e)}
                    title="Delete page"
                  >
                    ✕
                  </button>
                )}
              </div>
            )}
          </div>
        );
      })}

      {/* Add Page Button */}
      {mode === "edit" && (
        <button
          type="button"
          className="rpt-add-tab-btn"
          onClick={() => dispatch({ type: "ADD_PAGE" })}
          title="Add a new empty page"
        >
          + Add Page
        </button>
      )}
    </footer>
  );
}
