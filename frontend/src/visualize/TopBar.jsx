/**
 * frontend/src/visualize/TopBar.jsx
 * Top bar header with dashboard name, save, undo/redo, edit/view toggle,
 * generate dashboard, and export menu.
 */

import React, { useState, useRef, useEffect } from "react";
import { useDashboard } from "./dashboardContext";

export function TopBar({
  onSave,
  saveTime,
  isSaving,
  onGenerateDashboard,
  onExportPdf,
  onExportPng,
  onExportCsv,
  toggleLeftDrawer,
  toggleRightDrawer,
  isFullscreen = false,
  onToggleFullscreen,
  theme = "dark",
  onToggleTheme,
}) {
  const { state, dispatch } = useDashboard();
  const { present, past, future } = state;
  const [isEditingName, setIsEditingName] = useState(false);
  const [nameVal, setNameVal] = useState(present.name);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const exportMenuRef = useRef(null);

  useEffect(() => {
    setNameVal(present.name);
  }, [present.name]);

  useEffect(() => {
    function handleClickOutside(e) {
      if (exportMenuRef.current && !exportMenuRef.current.contains(e.target)) {
        setExportMenuOpen(false);
      }
    }
    if (exportMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [exportMenuOpen]);

  const handleNameBlur = () => {
    setIsEditingName(false);
    if (nameVal.trim() && nameVal !== present.name) {
      dispatch({ type: "SET_DASHBOARD_NAME", payload: nameVal.trim() });
    } else {
      setNameVal(present.name);
    }
  };

  const handleNameKeyDown = (e) => {
    if (e.key === "Enter") {
      handleNameBlur();
    } else if (e.key === "Escape") {
      setNameVal(present.name);
      setIsEditingName(false);
    }
  };

  return (
    <header className="rpt-topbar">
      {/* Left: Toggle left panel + Editable Title + Save + Undo/Redo */}
      <div className="rpt-topbar-left">
        {toggleLeftDrawer && (
          <button
            type="button"
            className="rpt-btn rpt-toggle-panel-btn"
            onClick={toggleLeftDrawer}
            title="Toggle Visualizations & Fields (Left Panel)"
          >
            ☰
          </button>
        )}

        <div className="rpt-dash-name-wrap">
          {isEditingName ? (
            <input
              type="text"
              className="rpt-dash-name-input"
              value={nameVal}
              onChange={(e) => setNameVal(e.target.value)}
              onBlur={handleNameBlur}
              onKeyDown={handleNameKeyDown}
              autoFocus
            />
          ) : (
            <span
              className="rpt-dash-name-input"
              onClick={() => setIsEditingName(true)}
              title="Click to rename dashboard"
              style={{ cursor: "pointer" }}
            >
              {present.name || "Untitled Dashboard"}
            </span>
          )}
        </div>

        <button
          type="button"
          className="rpt-btn"
          onClick={onSave}
          disabled={isSaving}
          title="Save dashboard to local storage"
        >
          <span className="rpt-btn-icon">💾</span>
          <span className="rpt-btn-label"> Save</span>
        </button>
        {saveTime && (
          <span className="rpt-save-status">
            Saved {saveTime}
          </span>
        )}

        <button
          type="button"
          className="rpt-btn"
          disabled={past.length === 0}
          onClick={() => dispatch({ type: "UNDO" })}
          title="Undo (Ctrl+Z)"
        >
          <span className="rpt-btn-icon">↩</span>
          <span className="rpt-btn-label-secondary"> Undo</span>
        </button>
        <button
          type="button"
          className="rpt-btn"
          disabled={future.length === 0}
          onClick={() => dispatch({ type: "REDO" })}
          title="Redo (Ctrl+Y)"
        >
          <span className="rpt-btn-icon">↪</span>
          <span className="rpt-btn-label-secondary"> Redo</span>
        </button>
      </div>

      {/* Center: Edit / View Mode Toggle (+ Paste, Snap, Grid in edit mode) */}
      <div className="rpt-topbar-center">
        <div className="rpt-mode-toggle">
          <button
            type="button"
            className={`rpt-mode-btn ${present.mode === "edit" ? "active edit" : ""}`}
            onClick={() => dispatch({ type: "SET_MODE", payload: "edit" })}
          >
            Edit
          </button>
          <button
            type="button"
            className={`rpt-mode-btn ${present.mode === "view" ? "active" : ""}`}
            onClick={() => dispatch({ type: "SET_MODE", payload: "view" })}
          >
            View
          </button>
        </div>

        {present.mode === "edit" && (
          <>
            <button
              type="button"
              className="rpt-btn"
              disabled={!present.clipboard || present.clipboard.length === 0}
              onClick={() => dispatch({ type: "PASTE_TILES" })}
              title="Paste (Ctrl+V)"
            >
              <span className="rpt-btn-icon">📋</span>
              <span className="rpt-btn-label-secondary"> Paste{present.clipboard?.length ? ` (${present.clipboard.length})` : ""}</span>
            </button>

            <button
              type="button"
              className={`rpt-btn ${present.settings?.snap ? "rpt-btn-primary" : ""}`}
              onClick={() =>
                dispatch({
                  type: "SET_SETTINGS",
                  payload: { snap: !present.settings?.snap },
                })
              }
              title="Toggle Snap to Grid (20px vs 4px)"
            >
              <span className="rpt-btn-icon">🧲</span>
              <span className="rpt-btn-label-secondary"> Snap</span>
            </button>

            <button
              type="button"
              className={`rpt-btn ${present.settings?.showGrid ? "rpt-btn-primary" : ""}`}
              onClick={() =>
                dispatch({
                  type: "SET_SETTINGS",
                  payload: { showGrid: !present.settings?.showGrid },
                })
              }
              title="Toggle Grid Dots"
            >
              <span className="rpt-btn-icon">▦</span>
              <span className="rpt-btn-label-secondary"> Grid</span>
            </button>
          </>
        )}
      </div>

      {/* Right: Generate (renamed from Generate Dashboard) + Export Menu + Right drawer toggle */}
      <div className="rpt-topbar-right">
        <button
          type="button"
          className="rpt-btn rpt-btn-primary"
          onClick={onGenerateDashboard}
          title="Generate Dashboard"
        >
          <span className="rpt-btn-icon">✨</span>
          <span className="rpt-btn-label"> Generate</span>
        </button>

        <div className="rpt-export-wrapper" style={{ position: "relative" }} ref={exportMenuRef}>
          <button
            type="button"
            className="rpt-btn"
            onClick={() => setExportMenuOpen(!exportMenuOpen)}
          >
            Export ▾
          </button>

          {exportMenuOpen && (
            <div
              className="rpt-export-menu"
              style={{
                position: "absolute",
                top: "100%",
                right: 0,
                marginTop: 4,
                backgroundColor: "#18181b",
                border: "1px solid #27272a",
                borderRadius: 6,
                boxShadow: "0 10px 25px rgba(0,0,0,0.5)",
                zIndex: 100,
                minWidth: 160,
                padding: "4px 0",
              }}
            >
              <button
                type="button"
                className="rpt-export-menu-item"
                style={{
                  width: "100%",
                  textAlign: "left",
                  padding: "8px 14px",
                  background: "transparent",
                  border: "none",
                  color: "#e4e4e7",
                  fontSize: 12,
                  cursor: "pointer",
                }}
                onClick={() => {
                  setExportMenuOpen(false);
                  onExportPdf?.();
                }}
              >
                📄 Export PDF (All Pages)
              </button>
              <button
                type="button"
                className="rpt-export-menu-item"
                style={{
                  width: "100%",
                  textAlign: "left",
                  padding: "8px 14px",
                  background: "transparent",
                  border: "none",
                  color: "#e4e4e7",
                  fontSize: 12,
                  cursor: "pointer",
                }}
                onClick={() => {
                  setExportMenuOpen(false);
                  onExportPng?.();
                }}
              >
                🖼️ Export PNG (Current Page)
              </button>
              <button
                type="button"
                className="rpt-export-menu-item"
                style={{
                  width: "100%",
                  textAlign: "left",
                  padding: "8px 14px",
                  background: "transparent",
                  border: "none",
                  color: "#e4e4e7",
                  fontSize: 12,
                  cursor: "pointer",
                }}
                onClick={() => {
                  setExportMenuOpen(false);
                  onExportCsv?.();
                }}
              >
                📊 Export CSV Data
              </button>
            </div>
          )}
        </div>

        {onToggleFullscreen && (
          <button
            type="button"
            className="rpt-btn"
            onClick={onToggleFullscreen}
            title={isFullscreen ? "Exit Fullscreen (Esc)" : "Fullscreen Workspace"}
          >
            <span>{isFullscreen ? "🗗" : "⛶"}</span>
            <span className="rpt-btn-label-secondary">{isFullscreen ? "Exit" : "Full"}</span>
          </button>
        )}

        {toggleRightDrawer && (
          <button
            type="button"
            className="rpt-btn rpt-toggle-panel-btn"
            onClick={toggleRightDrawer}
            title="Toggle Format & Data (Right Panel)"
          >
            ▤
          </button>
        )}
      </div>
    </header>
  );
}
